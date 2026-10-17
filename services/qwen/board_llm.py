"""Resident QNN JSONL worker; one model at a time, fresh KV state per request.

Uses the organizer's qnn_llm_runner_host without rebuilding the SDK. Same-model
requests keep weights/QNN contexts warm. No automatic fixture/CLI fallback.
"""

import asyncio
import json
import logging
import os
import signal
import time
from pathlib import Path

from common.api import ApiError
from common.contracts import Generation

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "board_llm.sh"
log = logging.getLogger("qwen.board")


def render_prompt(body: Generation, model: str) -> str:
    """Match supplied CLI templates, including the existing Gemma3 system fix."""
    system = "\n\n".join(m.content for m in body.messages if m.role == "system")
    prompt = "\n\n".join(m.content for m in body.messages if m.role != "system")
    if model == "gemma3":
        prompt = f"{system}\n\n{prompt}" if system else prompt
        return f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
    if model == "gemma4":
        prefix = f"<|turn>system\n{system}<turn|>\n" if system else ""
        return f"<bos>{prefix}<|turn>user\n{prompt}<turn|>\n<|turn>model\n"
    raise ApiError("unknown_model", "Unsupported board LLM family", 422)


class BoardLLMBackend:
    source = "executorch"
    model_ids = ("gemma3", "gemma4")

    def __init__(self, script=SCRIPT, model=None, startup_timeout=120):
        self.script, self.model = Path(script), model
        self.startup_timeout = startup_timeout
        self.process = None
        self.config = None
        self.stderr_task = None
        self.lock = asyncio.Lock()
        self.load_seconds = 0.0

    async def _config(self, pinned=True, requested=None):
        # Auto must not oscillate because its own resident weights use memory.
        explicit = requested or self.model
        override = explicit or (self.config["name"] if pinned and self.config else None)
        env = dict(os.environ)
        if explicit:
            env["LLM_SELECTION"] = explicit
        proc = await asyncio.create_subprocess_exec(
            "bash", str(self.script), "config", *([override] if override else []),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        try:
            async with asyncio.timeout(3):
                out, _ = await proc.communicate()
        except BaseException:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()
            raise
        if proc.returncode:
            raise ApiError("model_not_ready", "Board LLM configuration failed", 503, True)
        config = json.loads(out)
        if pinned and self.config and config["selection"] != self.config["selection"]:
            return await self._config(pinned=False, requested=requested)
        for key in ("worker", "model_path", "tokenizer_path"):
            if not Path(config[key]).is_file():
                raise ApiError("model_not_ready", "Board LLM worker or model file is missing", 503, True)
        return config

    @property
    def status(self):
        alive = self.process is not None and self.process.returncode is None and self.config is not None
        return {"resident": alive, "llm": self.config["name"] if alive else None,
                "pid": self.process.pid if alive else None}

    async def ready(self):
        # Health polls never load or switch models. Require a live, loaded worker.
        return self.status["resident"]

    async def startup(self):
        """Load Gemma4 before accepting HTTP requests; do not run generation."""
        async with self.lock:
            try:
                async with asyncio.timeout(self.startup_timeout):
                    config = await self._config(pinned=False, requested="gemma4")
                    await self._ensure(config)
            except BaseException:
                await self._stop()
                raise

    async def _drain_stderr(self, proc):
        while chunk := await proc.stderr.read(8192):
            log.debug("QNN worker: %s", chunk.decode(errors="replace").rstrip())

    async def _stop(self):
        proc, self.process = self.process, None
        if proc is not None:
            if proc.returncode is None:
                if os.name == "posix":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    proc.kill()
            await proc.wait()
        if self.stderr_task:
            await self.stderr_task
            self.stderr_task = None
        self.config = None

    async def _event(self):
        line = await self.process.stdout.readline()
        if not line:
            raise ApiError("model_unavailable", "The board LLM worker exited", 502, True)
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("Invalid worker event")
        return event

    async def _ensure(self, config):
        def identity(c):
            return {k: v for k, v in c.items() if k != "selection"}
        if (self.process is not None and self.process.returncode is None
                and self.config is not None and identity(self.config) == identity(config)):
            self.config = config
            return False
        await self._stop()
        env = dict(os.environ, LD_LIBRARY_PATH=config["ld_library_path"],
                   ADSP_LIBRARY_PATH=config["adsp_library_path"])
        started = time.monotonic()
        self.process = await asyncio.create_subprocess_exec(
            config["worker"], "--model_path", config["model_path"],
            "--tokenizer_path", config["tokenizer_path"],
            "--decoder_model_version", config["name"], "--eval_mode", "1",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE, env=env, start_new_session=True,
            limit=1024 * 1024,
        )
        self.stderr_task = asyncio.create_task(self._drain_stderr(self.process))
        event = await self._event()
        if event.get("ready") is not True:
            raise ApiError("model_unavailable", "The board LLM worker failed to load", 502, True)
        self.config = config
        self.load_seconds = time.monotonic() - started
        log.info("Board LLM loaded: %s pid=%s in %.3fs", config["name"],
                 self.process.pid, self.load_seconds)
        return True

    async def generate(self, body: Generation):
        async with self.lock:
            try:
                requested = body.model if body.model in self.model_ids else None
                config = await self._config(requested=requested)
                cold = await self._ensure(config)
                request = {"prompt": render_prompt(body, config["name"]),
                           "temperature": body.temperature,
                           "max_new_tokens": body.max_completion_tokens,
                           "stop": ["<end_of_turn>", "<turn|>", "<eos>"]}
                self.process.stdin.write((json.dumps(request) + "\n").encode())
                await self.process.stdin.drain()
                chunks = []
                size = 0
                while True:
                    event = await self._event()
                    if "error" in event:
                        raise ApiError("model_unavailable", "The board LLM rejected the request", 502, True)
                    if "token" in event:
                        size += len(event["token"])
                        if size > 100_000:
                            raise ValueError("Worker output too large")
                        chunks.append(event["token"])
                    if event.get("done") is True:
                        break
                text = "".join(chunks).strip()
                if not text:
                    raise ApiError("model_unavailable", "The board LLM returned no text", 502, True)
                return {"model": body.model,
                        "runner": {**self.status, "cold_start": cold,
                                   "load_seconds": round(self.load_seconds, 3) if cold else 0,
                                   "stats": event},
                        "choices": [{"message": {"role": "assistant", "content": text},
                                     "finish_reason": event.get("finish_reason", "stop")}]}
            except BaseException as exc:
                # Cancellation/timeout/crash invalidates partial protocol and
                # KV state. Reap the worker; next request loads a clean model.
                await self._stop()
                if isinstance(exc, (asyncio.CancelledError, ApiError)):
                    raise
                if not isinstance(exc, Exception):
                    raise
                log.exception("Board LLM worker failure")
                raise ApiError("model_unavailable", "The board LLM worker failed", 502, True) from exc

    async def close(self):
        async with self.lock:
            await self._stop()
