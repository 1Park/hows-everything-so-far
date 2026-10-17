"""ExecuTorchBackend drives qnn_llama_runner; a fake runner stands in for the board binary."""

import asyncio
import json
import os
import stat
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.language import generation, parse_interpretation
from common.api import ApiError
from common.backends import ExecuTorchBackend
from common.config import Settings
from common.contracts import CurrentRequest

FAKE_RUNNER = """#!{python}
import json, os, sys, time
args = sys.argv[1:]
opts = {{args[i][2:]: args[i + 1] for i in range(0, len(args) - 1, 2)}}
opts["_env"] = {{k: os.environ.get(k) for k in ("LD_LIBRARY_PATH", "ADSP_LIBRARY_PATH")}}
with open(os.environ["FAKE_RUNNER_ARGS"], "w") as f:
    json.dump(opts, f)
mode = os.environ.get("FAKE_RUNNER_MODE", "ok")
if mode == "fail":
    sys.stderr.write("QNN init failed")
    sys.exit(3)
if mode == "slow":
    time.sleep(30)
answer = os.environ.get("FAKE_RUNNER_ANSWER", "")
with open(opts["output_path"], "w") as f:
    f.write("<bos><|turn>system\\n" + opts.get("system_prompt", "") + "<turn|>\\n"
            "<|turn>user\\n" + opts["prompt"] + "<turn|>\\n<|turn>model\\n" + answer + "<turn|>")
with open(opts["performance_output_path"], "w") as f:
    f.write("5.1")
"""


@pytest.fixture
def board(tmp_path, monkeypatch):
    runner = tmp_path / "qnn_llama_runner"
    runner.write_text(FAKE_RUNNER.format(python=sys.executable))
    runner.chmod(runner.stat().st_mode | stat.S_IXUSR)
    model, tokenizer = tmp_path / "gemma.pte", tmp_path / "tokenizer.json"
    model.write_bytes(b"pte")
    tokenizer.write_text("{}")
    args_file = tmp_path / "args.json"
    monkeypatch.setenv("FAKE_RUNNER_ARGS", str(args_file))
    monkeypatch.setenv(
        "FAKE_RUNNER_ANSWER", '{"intent":"refill","item":"coffee","portion":"small"}'
    )
    settings = Settings(
        qwen_backend="fixture",
        qwen_model_backend="executorch",
        qwen_model="gemma4-e2b",
        qwen_runner_bin=str(runner),
        qwen_model_path=str(model),
        qwen_tokenizer_path=str(tokenizer),
    )
    return settings, args_file


def request(settings):
    current = CurrentRequest(item="coke", portion="regular")
    return generation(settings.qwen_model, current, "Just a little coffee please")


async def test_not_configured_is_not_ready():
    backend = ExecuTorchBackend(Settings(qwen_backend="fixture"))
    assert not await backend.ready()
    with pytest.raises(ApiError) as error:
        await backend.generate(request(Settings(qwen_backend="fixture")))
    assert error.value.code == "backend_not_configured" and error.value.status == 503


async def test_missing_model_file_is_not_ready(board, tmp_path):
    settings, _ = board
    settings = settings.model_copy(update={"qwen_model_path": str(tmp_path / "missing.pte")})
    assert not await ExecuTorchBackend(settings).ready()


async def test_generate_passes_prompts_and_returns_final_turn(board):
    settings, args_file = board
    backend = ExecuTorchBackend(settings)
    assert await backend.ready()
    body = request(settings)
    result = await backend.generate(body)
    content = result["choices"][0]["message"]["content"]
    assert result["source"] == "executorch"
    assert parse_interpretation(content).model_dump() == {
        "intent": "refill",
        "item": "coffee",
        "portion": "small",
    }
    opts = json.loads(args_file.read_text())
    assert opts["decoder_model_version"] == "gemma4"
    assert opts["system_prompt"] == body.messages[0].content
    assert json.loads(opts["prompt"])["utterance"] == "Just a little coffee please"
    assert float(opts["temperature"]) == 0 and opts["seq_len"] == "1024"
    assert "eval_mode" not in opts


async def test_eval_mode_and_decoder_are_configurable(board):
    settings, args_file = board
    settings = settings.model_copy(update={"qwen_decoder_version": "gemma3", "qwen_eval_mode": "1"})
    await ExecuTorchBackend(settings).generate(request(settings))
    opts = json.loads(args_file.read_text())
    assert opts["decoder_model_version"] == "gemma3" and opts["eval_mode"] == "1"


async def test_runner_failure_is_retryable_502(board, monkeypatch):
    settings, _ = board
    monkeypatch.setenv("FAKE_RUNNER_MODE", "fail")
    with pytest.raises(ApiError) as error:
        await ExecuTorchBackend(settings).generate(request(settings))
    assert error.value.code == "model_unavailable" and error.value.retryable


async def test_empty_answer_is_502(board, monkeypatch):
    settings, _ = board
    monkeypatch.setenv("FAKE_RUNNER_ANSWER", "  ")
    with pytest.raises(ApiError) as error:
        await ExecuTorchBackend(settings).generate(request(settings))
    assert error.value.code == "model_unavailable"


async def test_timeout_kills_runner(board, monkeypatch):
    settings, _ = board
    monkeypatch.setenv("FAKE_RUNNER_MODE", "slow")
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(1):
            await ExecuTorchBackend(settings).generate(request(settings))
    assert time.monotonic() - started < 10


def test_extra_turns_are_rejected(board):
    settings, _ = board
    body = request(settings)
    body = body.model_copy(update={"messages": [*body.messages, body.messages[-1]]})
    with pytest.raises(ApiError) as error:
        asyncio.run(ExecuTorchBackend(settings).generate(body))
    assert error.value.code == "unsupported_messages"


@pytest.mark.parametrize(
    ("transcript", "answer"),
    [
        (
            "<bos><|turn>system\nYou are a concise assistant.<turn|>\n<|turn>user\n"
            "Reply with one word: what color is the sky?<turn|>\n<|turn>model\nBlue<turn|>",
            "Blue",
        ),
        (
            "<start_of_turn>user\nReply with one word: what color is the sky?<end_of_turn>\n"
            "<start_of_turn>model\nBlue.<end_of_turn>",
            "Blue.",
        ),
        (
            '<|turn>model\n```json\n{"intent":"cancel"}\n```<turn|>',
            '```json\n{"intent":"cancel"}\n```',
        ),
        ("no markers here", "no markers here"),
    ],
)
def test_final_turn(transcript, answer):
    assert ExecuTorchBackend.final_turn(transcript) == answer


def test_qwen_server_reports_executorch_source(board):
    from services.qwen.server import create_app

    settings, _ = board
    with TestClient(create_app(settings)) as client:
        assert client.get("/ready").json()["ready"] is True
        body = request(settings).model_dump()
        response = client.post("/v1/chat/completions", json=body)
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "executorch"


@pytest.mark.skipif(os.name != "posix", reason="POSIX exec bit")
def test_non_executable_runner_is_not_ready(board):
    settings, _ = board
    runner = settings.qwen_runner_bin
    os.chmod(runner, 0o644)
    assert not asyncio.run(ExecuTorchBackend(settings).ready())


async def test_runner_library_paths_are_set(board, monkeypatch):
    settings, args_file = board
    monkeypatch.setenv("LD_LIBRARY_PATH", "/existing")
    settings = settings.model_copy(
        update={
            "qwen_runner_library_path": "/et/qualcomm:/usr/lib",
            "qwen_adsp_library_path": "/usr/lib/dsp/cdsp",
        }
    )
    await ExecuTorchBackend(settings).generate(request(settings))
    env = json.loads(args_file.read_text())["_env"]
    assert env["LD_LIBRARY_PATH"] == "/et/qualcomm:/usr/lib:/existing"
    assert env["ADSP_LIBRARY_PATH"] == "/usr/lib/dsp/cdsp"
