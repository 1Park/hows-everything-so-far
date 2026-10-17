import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.language import generation, parse_interpretation
from common.api import ApiError
from common.config import Settings
from common.contracts import CurrentRequest
from services.qwen.board_llm import BoardLLMBackend
from services.qwen.server import create_app

# board_llm.sh 와 같은 출력 규칙: 답은 stdout, 속도는 stderr, 메모리 부족은 exit 4
FAKE = """#!/usr/bin/env bash
case "$1" in
  status) echo "selected : auto  → would run: gemma4"
          echo "  gemma3  ctx 5000  peak ~1400 MB  ok (1.1G)"
          echo "  gemma4  ctx 2000  peak ~2200 MB  {gemma4}";;
  ask) shift; sys=""; while [ "$1" != "--" ]; do [ "$1" = -s ] && sys="$2"; shift; done; shift
       [ -n "{hang}" ] && {{ sleep 30 & echo $! > "{pidfile}"; wait; }}
       [ -n "{oom}" ] && exit 4
       echo "$1" > "{seen}"; printf '%s' "$sys" > "{seen}.sys"
       echo '{answer}'
       echo "[gemma4] load 6.7s | prompt 565 tok @ 846 tok/s | gen 14 tok @ 17.3 tok/s" >&2;;
esac
"""


def fake(
    tmp_path,
    gemma4="ok (2.8G)",
    hang="",
    oom="",
    answer='{"intent":"refill","item":"coffee","portion":"small"}',
):
    script = tmp_path / "board_llm.sh"
    script.write_text(
        FAKE.format(
            gemma4=gemma4,
            hang=hang,
            oom=oom,
            answer=answer,
            seen=tmp_path / "seen",
            pidfile=tmp_path / "pid",
        )
    )
    return script


def body(utterance="Just a little coffee please"):
    return generation("board-gemma", CurrentRequest(item="coke", portion="regular"), utterance)


async def test_generate_passes_system_and_user_and_parses(tmp_path):
    backend = BoardLLMBackend(fake(tmp_path))
    assert await backend.ready()
    result = await backend.generate(body())
    assert parse_interpretation(result["choices"][0]["message"]["content"]).item == "coffee"
    assert result["runner"] == {
        "llm": "gemma4",
        "stats": "load 6.7s | prompt 565 tok @ 846 tok/s | gen 14 tok @ 17.3 tok/s",
    }
    assert json.loads((tmp_path / "seen").read_text())["utterance"] == "Just a little coffee please"
    assert (
        (tmp_path / "seen.sys")
        .read_text()
        .startswith("You interpret English drink refill requests")
    )


async def test_not_ready_when_selected_model_missing(tmp_path):
    assert not await BoardLLMBackend(fake(tmp_path, gemma4="MISSING")).ready()
    assert await BoardLLMBackend(fake(tmp_path, gemma4="MISSING"), model="gemma3").ready()
    assert not await BoardLLMBackend(tmp_path / "nope.sh").ready()


async def test_memory_shortage_is_retryable_503(tmp_path):
    with pytest.raises(ApiError) as exc:
        await BoardLLMBackend(fake(tmp_path, oom="1")).generate(body())
    assert exc.value.status == 503 and exc.value.code == "model_memory"


async def test_timeout_kills_runner_child(tmp_path):
    backend = BoardLLMBackend(fake(tmp_path, hang="1"))
    task = asyncio.create_task(backend.generate(body()))
    pidfile = tmp_path / "pid"
    for _ in range(100):
        if pidfile.exists() and pidfile.read_text().strip():
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    pid = int(pidfile.read_text())
    await asyncio.sleep(0.1)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_qwen_service_uses_board_backend(tmp_path):
    settings = Settings(qwen_model_backend="executorch", qwen_model="board-gemma")
    with TestClient(create_app(settings, backend=BoardLLMBackend(fake(tmp_path)))) as c:
        ready = c.get("/ready").json()
        assert ready["ready"] is True and ready["source"] == "executorch"
        r = c.post("/v1/chat/completions", json=body().model_dump())
        assert r.status_code == 200 and r.json()["source"] == "executorch"
