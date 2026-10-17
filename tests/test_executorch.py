"""Runner integration with a real child-process double; no claim of NPU inference."""

import asyncio
import sys

import pytest
from fastapi.testclient import TestClient

from app.language import generation
from common.api import ApiError
from common.backends import ExecuTorchBackend
from common.config import Settings
from common.executorch import DinoRunner, execute
from common.contracts import CurrentRequest
from services.qwen.server import create_app


@pytest.fixture
def runner(tmp_path, monkeypatch):
    script = tmp_path / "runner.py"
    script.write_text(
        """
import sys
from pathlib import Path
a = sys.argv[1:]
def flag(name): return a[a.index(name) + 1]
assert Path(flag('--model_path')).read_bytes() == b'pte'
if '--prompt' in a:
    assert flag('--decoder_model_version') == 'qwen3'
    assert flag('--temperature') == '0.0'
    assert '<|im_start|>system' in flag('--prompt')
    Path(flag('--output_path')).write_text('{"intent":"refill","item":"water"}')
else:
    names = Path(flag('--input_list_path')).read_text().split()
    assert [Path(n).read_bytes() for n in names] == [b'prepared']
    p = Path(flag('--output_folder_path')) / 'Result_0'
    p.mkdir()
    (p / 'output_0.raw').write_bytes(b'raw-output')
""",
        encoding="utf-8",
    )
    original = asyncio.create_subprocess_exec

    async def launch(*command, **kwargs):
        return await original(sys.executable, str(script), *command[1:], **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    model = tmp_path / "model.pte"
    model.write_bytes(b"pte")
    tokenizer = tmp_path / "tokenizer.bin"
    tokenizer.write_bytes(b"tokenizer")
    return Settings(
        qwen_model_backend="executorch",
        qwen_seq_len=512,
        qnn_llama_runner=sys.executable,
        qwen_model_path=str(model),
        qwen_tokenizer_path=str(tokenizer),
    )


def test_qwen_http_to_native_process(runner):
    with TestClient(create_app(runner)) as client:
        assert client.get("/ready").json()["source"] == "executorch"
        payload = generation(
            runner.qwen_model, CurrentRequest(item="water"), "small please"
        )
        response = client.post("/v1/chat/completions", json=payload.model_dump())
        assert response.status_code == 200
        assert '"item":"water"' in response.json()["choices"][0]["message"]["content"]
        assert response.json()["runner_limits"]["completion_token_limit_enforced"] is False


async def test_dino_prepared_tensor_to_raw_output(runner):
    backend = DinoRunner(sys.executable, runner.qwen_model_path)
    assert await backend.infer([b"prepared"]) == {"Result_0/output_0.raw": b"raw-output"}
    with pytest.raises(ApiError):
        await backend.infer([])


async def test_missing_bundle_no_fallback():
    backend = ExecuTorchBackend(Settings(qwen_model_backend="executorch"))
    assert not await backend.ready()
    with pytest.raises(ApiError) as error:
        await backend.generate(
            generation("test", CurrentRequest(item="water"), "yes")
        )
    assert error.value.status == 503


async def test_process_timeout_and_cancellation(tmp_path, monkeypatch):
    original = asyncio.create_subprocess_exec
    children = []

    async def launch(*args, **kwargs):
        process = await original(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    command = [sys.executable, "-c", "import time; time.sleep(60)"]
    with pytest.raises(ApiError) as error:
        await execute(command, tmp_path, 0.1)
    assert error.value.status == 504 and children[-1].returncode is not None
    task = asyncio.create_task(execute(command, tmp_path, 60))
    while len(children) < 2:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[-1].returncode is not None


async def test_nonzero_and_missing_output(runner, monkeypatch, tmp_path):
    async def fail(*args):
        raise ApiError("runner_failed", "Native model runner failed", 502)

    monkeypatch.setattr("common.executorch.execute", fail)
    with pytest.raises(ApiError) as error:
        await ExecuTorchBackend(runner).generate(
            generation(runner.qwen_model, CurrentRequest(item="water"), "yes")
        )
    assert error.value.code == "runner_failed"

    async def empty(*args):
        pass

    monkeypatch.setattr("common.executorch.execute", empty)
    with pytest.raises(ApiError) as error:
        await DinoRunner(sys.executable, runner.qwen_model_path).infer([b"prepared"])
    assert error.value.code == "invalid_backend_output"
