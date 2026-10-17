import asyncio
import importlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

import httpx

from common.api import ApiError, log, request_id
from common.contracts import Generation, uid


class TextBackend(Protocol):
    source: str

    async def ready(self) -> bool: ...
    async def generate(self, body: Generation) -> dict: ...


class MLXBackend:
    source = "mlx"

    def __init__(self, url: str, model: str, timeout: float):
        self.url, self.model = url.rstrip("/"), model
        self.client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def ready(self) -> bool:
        try:
            response = await self.client.get(f"{self.url}/v1/models", timeout=4)
            response.raise_for_status()
            data = response.json()["data"]
            return isinstance(data, list) and any(
                isinstance(row, dict) and row.get("id") == self.model for row in data
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False

    async def generate(self, body: Generation) -> dict:
        payload = body.model_dump()
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            response = await self.client.post(
                f"{self.url}/v1/chat/completions",
                json=payload,
                headers={"x-request-id": request_id.get() if request_id.get() != "-" else uid()},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result["choices"][0]["message"]["content"], str):
                raise ValueError()
            return result
        except httpx.TimeoutException:
            raise ApiError("model_timeout", "The model endpoint timed out", 504, True) from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise ApiError(
                "model_unavailable",
                "The model endpoint returned an invalid response or is unavailable",
                502,
                True,
            ) from None

    async def close(self):
        await self.client.aclose()


class FixtureTextBackend:
    """Deterministic simulator. Explicit mode, never used as a fallback for MLX errors."""

    source = "fixture"

    async def ready(self):
        return True

    async def generate(self, body: Generation):
        await asyncio.sleep(0.04)
        try:
            data = json.loads(body.messages[-1].content)
            utterance = data["utterance"].lower().strip()
            current = data["current_request"]
        except (ValueError, KeyError, TypeError):
            raise ApiError(
                "fixture_input", "Fixture expects a current_request and utterance", 422
            ) from None
        intent, item, portion = "refill", current["item"], current["portion"]
        if re.search(r"\b(cancel|stop|never mind)\b", utterance):
            intent = "cancel"
        elif re.search(r"\b(no|nope|fine|don't need)\b", utterance):
            intent = "decline"
        else:
            drinks = [d for d in ("water", "coke", "coffee") if re.search(rf"\b{d}\b", utterance)]
            if len(drinks) > 1 or re.search(
                r"\b(juice|tea|time|maybe|whatever|not sure|ignore)\b", utterance
            ):
                intent = "clarify"
            elif drinks:
                item = drinks[0]
            elif not re.search(
                r"yes|please|same|small|little|less|half|regular|normal|full", utterance
            ):
                intent = "clarify"
            if re.search(r"small|little|less|half", utterance):
                portion = "small"
            elif re.search(r"regular|normal|full", utterance):
                portion = "regular"
        result = {
            "intent": intent,
            "item": item if intent == "refill" else None,
            "portion": portion if intent == "refill" else None,
        }
        return {
            "model": body.model,
            "source": "fixture",
            "choices": [
                {
                    "message": {"role": "assistant", "content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            ],
        }


class ExecuTorchBackend:
    """Board LLM through the Qualcomm qnn_llama_runner CLI, one runner process per request.

    The runner applies the chat template selected by --decoder_model_version and writes the
    whole transcript to --output_path; only the final model turn is returned. The process is
    killed when the request times out or is cancelled. Not configured means not ready (503);
    there is no fixture or remote fallback.
    """

    source = "executorch"
    TURN_MARKERS = (
        "<|turn>model",
        "<start_of_turn>model",
        "<|im_start|>assistant",
        "<|start_header_id|>assistant<|end_header_id|>",
    )
    END_MARKERS = ("<turn|>", "<end_of_turn>", "<eos>", "<|im_end|>", "<|eot_id|>", "</s>")

    def __init__(self, settings=None):
        self.settings = settings

    def _paths(self):
        s = self.settings
        if s is None or not (s.qwen_runner_bin and s.qwen_model_path and s.qwen_tokenizer_path):
            return None
        from common.config import ROOT

        paths = [
            Path(v) if Path(v).is_absolute() else ROOT / v
            for v in (s.qwen_runner_bin, s.qwen_model_path, s.qwen_tokenizer_path)
        ]
        runner, model, tokenizer = paths
        if not (runner.is_file() and os.access(runner, os.X_OK)):
            return None
        if not (model.is_file() and tokenizer.is_file()):
            return None
        return paths

    async def ready(self):
        return self._paths() is not None

    @classmethod
    def final_turn(cls, transcript: str) -> str:
        cut, marker = max((transcript.rfind(m), m) for m in cls.TURN_MARKERS)
        text = transcript[cut + len(marker) :] if cut >= 0 else transcript
        for end in cls.END_MARKERS:
            text = text.split(end, 1)[0]
        return text.strip()

    def environment(self) -> dict[str, str]:
        s, env = self.settings, os.environ.copy()
        if s.qwen_runner_library_path:
            current = env.get("LD_LIBRARY_PATH")
            env["LD_LIBRARY_PATH"] = s.qwen_runner_library_path + (f":{current}" if current else "")
        if s.qwen_adsp_library_path:
            env["ADSP_LIBRARY_PATH"] = s.qwen_adsp_library_path
        return env

    def command(self, paths, body: Generation, output: Path, perf: Path) -> list[str]:
        s = self.settings
        system = "\n\n".join(m.content for m in body.messages if m.role == "system")
        turns = [m for m in body.messages if m.role != "system"]
        if len(turns) != 1 or turns[0].role != "user":
            raise ApiError(
                "unsupported_messages",
                "The board runner accepts one optional system message and one user message",
                422,
            )
        runner, model, tokenizer = paths
        cmd = [
            str(runner),
            "--model_path", str(model),
            "--tokenizer_path", str(tokenizer),
            "--decoder_model_version", s.qwen_decoder_version,
            "--prompt", turns[0].content,
            "--seq_len", str(s.qwen_seq_len),
            "--temperature", str(body.temperature),
            "--output_path", str(output),
            "--performance_output_path", str(perf),
        ]  # fmt: skip
        if system:
            cmd += ["--system_prompt", system]
        if s.qwen_eval_mode:
            cmd += ["--eval_mode", s.qwen_eval_mode]
        return cmd

    async def generate(self, body: Generation):
        paths = self._paths()
        if paths is None:
            raise ApiError(
                "backend_not_configured",
                "ExecuTorch needs QWEN_RUNNER_BIN, QWEN_MODEL_PATH and QWEN_TOKENIZER_PATH",
                503,
            )
        with tempfile.TemporaryDirectory(prefix="refill-llm-") as directory:
            output, perf = Path(directory) / "out.txt", Path(directory) / "perf.txt"
            cmd = self.command(paths, body, output, perf)
            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=directory,
                    env=self.environment(),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
            except OSError:
                raise ApiError(
                    "model_unavailable", "The board LLM runner could not start", 502, True
                ) from None
            try:
                _, stderr = await process.communicate()
            except asyncio.CancelledError:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                await process.wait()
                raise
            if process.returncode:
                log.warning(
                    {
                        "event": "llm_runner_failed",
                        "returncode": process.returncode,
                        "stderr": stderr.decode(errors="replace")[-2000:],
                    }
                )
                raise ApiError("model_unavailable", "The board LLM runner failed", 502, True)
            transcript = output.read_text(errors="replace") if output.is_file() else ""
            speed = perf.read_text(errors="replace").strip() if perf.is_file() else ""
        content = self.final_turn(transcript)
        if not content:
            raise ApiError("model_unavailable", "The board LLM returned no text", 502, True)
        log.info({"event": "llm_runner_done", "tokens_per_second": speed})
        return {
            "model": body.model,
            "source": "executorch",
            "choices": [
                {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
            ],
        }


def external_adapter(path: str):
    """Explicit trusted module:factory, invoked once. Factory returns an async backend."""
    module, factory = path.split(":", 1)
    return getattr(importlib.import_module(module), factory)()
