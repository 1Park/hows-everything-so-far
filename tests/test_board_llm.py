"""Real JSONL child processes test persistence, switches, isolation and cleanup.

The fake child is NOT a model or evidence of board inference accuracy.
"""
import asyncio
import json
import sys

import pytest
from fastapi.testclient import TestClient

from app.language import generation, parse_interpretation
from common.api import ApiError
from common.config import Settings
from common.contracts import CurrentRequest
from services.qwen.board_llm import BoardLLMBackend, render_prompt
from services.qwen.server import create_app


def body(utterance="Just a little coffee please"):
    return generation("board-gemma", CurrentRequest(item="water"), utterance)


@pytest.fixture
def worker(tmp_path, monkeypatch):
    worker = tmp_path / "worker.py"
    worker.write_text('''import json,sys,time,os
from pathlib import Path
root=Path(__file__).parent
with (root/"starts").open("a") as f: f.write(str(os.getpid())+"\\n")
print(json.dumps({"ready": True}),flush=True)
for line in sys.stdin:
    req=json.loads(line)
    with (root/"requests").open("a") as f: f.write(json.dumps(req)+"\\n")
    if "HANG" in req["prompt"]: time.sleep(30)
    if "CRASH" in req["prompt"]: sys.exit(1)
    if "BAD_PROTOCOL" in req["prompt"]:
        print("not json",flush=True); continue
    result={"intent":"refill","item":"coffee"}
    print(json.dumps({"token":json.dumps(result)}),flush=True)
    print(json.dumps({"done":True,"finish_reason":"stop","session_reset_reason":"new"}),flush=True)
''', encoding="utf-8")
    script = tmp_path / "config.py"
    script.write_text('''import json,sys,os
from pathlib import Path
root=Path(__file__).parent
sel=os.environ.get("LLM_SELECTION") or (root/"selection").read_text()
name=sys.argv[2] if len(sys.argv)>2 else ("gemma4" if sel=="auto" else sel)
print(json.dumps(dict(selection=sel,name=name,worker=str(root/"worker.py"),
 model_path=str(root/(name+".pte")),tokenizer_path=str(root/"tokenizer.json"),
 ld_library_path="",adsp_library_path="")))
''', encoding="utf-8")
    for name in ("gemma3.pte", "gemma4.pte", "tokenizer.json"):
        (tmp_path / name).touch()
    (tmp_path / "selection").write_text("gemma4")
    real_exec = asyncio.create_subprocess_exec

    async def launch(*args, **kwargs):
        if args[0] == "bash":
            args = (sys.executable, *args[1:])
        elif args[0] == str(worker):
            args = (sys.executable, *args)
        return await real_exec(*args, **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    return script


async def test_reuse_same_pid_isolated_requests_and_switch(worker):
    backend = BoardLLMBackend(worker)
    try:
        assert not await backend.ready()
        assert not backend.status["resident"]
        first = await backend.generate(body())
        second = await backend.generate(body("Coffee instead"))
        assert first["runner"]["cold_start"] and not second["runner"]["cold_start"]
        assert first["runner"]["pid"] == second["runner"]["pid"]
        assert parse_interpretation(second["choices"][0]["message"]["content"]).item == "coffee"
        requests = [json.loads(s) for s in (worker.parent / "requests").read_text().splitlines()]
        assert all("session_id" not in req for req in requests)
        assert all(req["temperature"] == 0 and req["max_new_tokens"] == 192 for req in requests)
        assert "Coffee instead" in requests[1]["prompt"]
        assert "Just a little coffee" not in requests[1]["prompt"]
        (worker.parent / "selection").write_text("auto")
        third = await backend.generate(body())
        assert third["runner"]["pid"] == first["runner"]["pid"]
        (worker.parent / "selection").write_text("gemma3")
        fourth = await backend.generate(body())
        assert fourth["runner"]["pid"] != first["runner"]["pid"]
        assert fourth["runner"]["cold_start"] and fourth["runner"]["llm"] == "gemma3"
        assert len((worker.parent / "starts").read_text().splitlines()) == 2
    finally:
        await backend.close()
    assert not backend.status["resident"]


@pytest.mark.parametrize("utterance", ["CRASH", "BAD_PROTOCOL"])
async def test_worker_failure_reloads_without_fixture(worker, utterance):
    backend = BoardLLMBackend(worker)
    try:
        with pytest.raises(ApiError) as error:
            await backend.generate(body(utterance))
        assert error.value.code == "model_unavailable"
        assert not backend.status["resident"]
        assert (await backend.generate(body()))["runner"]["cold_start"]
    finally:
        await backend.close()


async def test_timeout_kills_worker_and_restarts(worker):
    backend = BoardLLMBackend(worker)
    task = asyncio.create_task(backend.generate(body("HANG")))
    try:
        for _ in range(200):
            if (worker.parent / "requests").exists():
                break
            await asyncio.sleep(0.02)
        process = backend.process
        assert process is not None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.returncode is not None
        assert not backend.status["resident"]
        result = await backend.generate(body())
        assert result["runner"]["cold_start"] and result["runner"]["pid"] != process.pid
    finally:
        task.cancel()
        await backend.close()


async def test_missing_model_not_ready(worker):
    (worker.parent / "gemma4.pte").unlink()
    assert not await BoardLLMBackend(worker).ready()
    backend = BoardLLMBackend(worker)
    with pytest.raises(ApiError):
        await backend.startup()
    assert not backend.status["resident"]


async def test_concurrent_calls_serialized(worker):
    backend = BoardLLMBackend(worker)
    try:
        results = await asyncio.gather(*(backend.generate(body()) for _ in range(3)))
        assert len({r["runner"]["pid"] for r in results}) == 1
        assert sum(r["runner"]["cold_start"] for r in results) == 1
    finally:
        await backend.close()


def test_templates():
    assert render_prompt(body(), "gemma4").startswith("<bos><|turn>system\n")
    assert render_prompt(body(), "gemma3").startswith("<start_of_turn>user\nYou interpret")


def test_api_shutdown_reaps_resident_worker(worker):
    backend = BoardLLMBackend(worker)
    with TestClient(create_app(Settings(qwen_model_backend="executorch", qwen_model="board-gemma"),
                               backend=backend)) as client:
        assert client.get("/ready").json()["ready"]
        initial = client.get("/ready").json()["runner"]
        assert initial["resident"] and initial["llm"] == "gemma4"
        assert not (worker.parent / "requests").exists()
        result = client.post("/v1/chat/completions", json=body().model_dump())
        assert result.status_code == 200 and result.json()["source"] == "executorch"
        assert not result.json()["runner"]["cold_start"]
        assert result.json()["runner"]["pid"] == initial["pid"]
        assert client.get("/ready").json()["runner"]["resident"]
        request = body().model_dump()
        request["model"] = "gemma3"
        switched = client.post("/v1/chat/completions", json=request)
        assert switched.status_code == 200 and switched.json()["runner"]["llm"] == "gemma3"
        assert switched.json()["runner"]["cold_start"]
        reused = client.post("/v1/chat/completions", json=request)
        assert reused.json()["runner"]["pid"] == switched.json()["runner"]["pid"]
        assert not reused.json()["runner"]["cold_start"]
        assert "gemma4" in [m["id"] for m in client.get("/v1/models").json()["data"]]
        proc = backend.process
    assert proc.returncode is not None


async def test_startup_pins_gemma4_and_sends_no_generation(worker):
    (worker.parent / "selection").write_text("gemma3")
    backend = BoardLLMBackend(worker)
    try:
        await backend.startup()
        assert await backend.ready()
        assert backend.status["llm"] == "gemma4"
        assert not (worker.parent / "requests").exists()
        pid = backend.status["pid"]
        await backend.startup()
        assert backend.status["pid"] == pid
    finally:
        await backend.close()


async def test_startup_timeout_reaps_child(worker):
    child = worker.parent / "worker.py"
    child.write_text(child.read_text().replace(
        'print(json.dumps({"ready": True}),flush=True)',
        'time.sleep(30); print(json.dumps({"ready": True}),flush=True)',
    ))
    backend = BoardLLMBackend(worker, startup_timeout=1)
    spawned = []
    original = backend._event

    async def capture_process():
        spawned.append(backend.process)
        return await original()

    backend._event = capture_process
    with pytest.raises(TimeoutError):
        await backend.startup()
    assert spawned and spawned[0].returncode is not None
    assert not await backend.ready()


def test_api_startup_failure_does_not_accept_requests(worker):
    (worker.parent / "gemma4.pte").unlink()
    backend = BoardLLMBackend(worker)
    with pytest.raises(ApiError):
        with TestClient(create_app(Settings(qwen_model_backend="executorch"), backend=backend)):
            pytest.fail("Server must not start without the Gemma4 model")
    assert not backend.status["resident"]


def test_executorch_backend_preloads_gemma4(worker, monkeypatch):
    backend = BoardLLMBackend(worker)
    monkeypatch.setattr("services.qwen.server.BoardLLMBackend", lambda: backend)
    with TestClient(create_app(Settings(qwen_model_backend="executorch", qwen_model="gemma4"))) as client:
        ready = client.get("/ready").json()
        assert ready["ready"] and ready["runner"]["llm"] == "gemma4"
        assert not (worker.parent / "requests").exists()
    assert not backend.status["resident"]
