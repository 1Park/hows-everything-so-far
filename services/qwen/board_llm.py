"""보드 Gemma(QCS8275 .pte, NPU)를 Qwen 서비스 backend로 쓴다. QWEN_MODEL_BACKEND=executorch.

scripts/board_llm.sh ask 를 요청마다 1회 실행한다(qnn_llama_runner 일회성 CLI).
모델은 상주하지 않는다: 요청마다 load 4~7초 + 생성. 2026-10-17 보드 실측, Controller 프롬프트 1건:
gemma4 8.8초(정답), gemma3 5.4초(오답). 모델 선택은 board_llm.sh use gemma3|gemma4|auto 를 따른다.
"""

import asyncio
import os
import re
import signal
from pathlib import Path

from common.api import ApiError
from common.contracts import Generation

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "board_llm.sh"
STATS = re.compile(r"^\[(gemma\w*)\] (load .*)$", re.M)


class BoardLLMBackend:
    source = "executorch"

    def __init__(self, script=SCRIPT, model=None):
        self.script, self.model = Path(script), model

    async def _run(self, *args):
        process = await asyncio.create_subprocess_exec(
            "bash",
            str(self.script),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=ROOT,
            start_new_session=True,
        )
        try:
            out, err = await process.communicate()
        except asyncio.CancelledError:
            # InferenceGate timeout → bash 아래 runner까지 끝낸다 (남으면 NPU를 계속 잡고 있음)
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
            raise
        return process.returncode, out.decode(errors="replace"), err.decode(errors="replace")

    async def ready(self):
        if not self.script.exists():
            return False
        code, out, _ = await self._run("status")
        chosen = re.search(r"would run: (\w+)", out)
        if code != 0 or not chosen:
            return False
        name = self.model or chosen.group(1)
        return any(line.split()[:1] == [name] and " ok " in line for line in out.splitlines())

    async def generate(self, body: Generation):
        system = "\n\n".join(m.content for m in body.messages if m.role == "system")
        prompt = "\n\n".join(m.content for m in body.messages if m.role != "system")
        args = (
            ["ask"]
            + (["-m", self.model] if self.model else [])
            + (["-s", system] if system else [])
        )
        code, out, err = await self._run(*args, "--", prompt)
        if code == 4:
            raise ApiError("model_memory", "Not enough memory to load the board LLM", 503, True)
        if code != 0 or not out.strip():
            raise ApiError("model_unavailable", "The board LLM runner failed", 502, True)
        stats = STATS.search(err)
        return {
            "model": body.model,
            "runner": {"llm": stats.group(1), "stats": stats.group(2)} if stats else None,
            "choices": [
                {"message": {"role": "assistant", "content": out.strip()}, "finish_reason": "stop"}
            ],
        }
