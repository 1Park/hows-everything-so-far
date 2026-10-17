import asyncio
import io
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from app.language import generation
from common.api import ApiError, InferenceGate
from common.backends import MLXBackend
from common.config import ROOT, Settings
from common.contracts import CurrentRequest
from services.qwen.server import create_app
from services.sensory import create_sensory_app


def wav():
    b = io.BytesIO()
    with wave.open(b, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 1600)
    return b.getvalue()


def test_sensory_validation_and_fixtures():
    settings = Settings(max_image_bytes=300000)
    with TestClient(create_sensory_app("vision", settings)) as c:
        assert c.get("/ready").json()["source"] == "fixture"
        image = (ROOT / "docs/assets/cups-example.jpg").read_bytes()
        r = c.post(
            "/v1/analyze",
            files={"file": ("cups.jpg", image, "image/jpeg")},
            data={"scene_id": "s1"},
        )
        assert r.status_code == 200 and r.json()["scene_id"] == "s1"
        assert (
            c.post(
                "/v1/analyze", files={"file": ("x", b"bad", "image/jpeg")}, data={"scene_id": "s"}
            ).status_code
            == 422
        )
        assert (
            c.post(
                "/v1/analyze",
                files={"file": ("x", b"x" * 300001, "image/jpeg")},
                data={"scene_id": "s"},
            ).status_code
            == 413
        )
    with TestClient(create_sensory_app("stt", settings)) as c:
        r = c.post("/v1/transcribe", files={"file": ("a.wav", wav(), "audio/wav")})
        assert r.json()["source"] == "fixture" and r.json()["text"] == "A little water, please"
        assert (
            c.post(
                "/v1/transcribe", files={"file": ("a.wav", b"not audio", "audio/wav")}
            ).status_code
            == 415
        )


def test_qwen_validation_and_request_ids():
    settings = Settings(qwen_model_backend="fixture")
    with TestClient(create_app(settings)) as c:
        r = c.get("/ready", headers={"x-request-id": "demo-123"})
        assert r.status_code == 200 and r.headers["x-request-id"] == "demo-123"
        payload = generation(
            settings.qwen_model, CurrentRequest(item="water"), "yes"
        ).model_dump()
        assert c.post("/v1/chat/completions", json=payload).json()["source"] == "fixture"
        payload["temperature"] = 9
        r = c.post("/v1/chat/completions", json=payload)
        assert r.status_code == 422 and set(r.json()["error"]) == {
            "code",
            "message",
            "request_id",
            "retryable",
        }


async def test_queue_capacity_and_timeout():
    gate = InferenceGate(1, 0.03)
    entered = asyncio.Event()

    async def first():
        with pytest.raises(ApiError) as exc:
            async with gate.slot():
                entered.set()
                await asyncio.sleep(1)
        assert exc.value.status == 504

    task = asyncio.create_task(first())
    await entered.wait()
    with pytest.raises(ApiError) as exc:
        async with gate.slot():
            pass
    assert exc.value.status == 503
    await task
    assert gate.pending == 0


@pytest.mark.parametrize("kind", ["timeout", "bad", "down"])
async def test_mlx_errors_do_not_fallback(kind):
    backend = MLXBackend("http://test", "test", 1)
    await backend.client.aclose()

    async def handle(request):
        if kind == "timeout":
            raise httpx.ReadTimeout("slow")
        if kind == "down":
            return httpx.Response(503)
        return httpx.Response(200, json={"wrong": "schema"})

    backend.client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    with pytest.raises(ApiError) as exc:
        await backend.generate(
            generation("test", CurrentRequest(item="water"), "yes")
        )
    assert exc.value.status == (504 if kind == "timeout" else 502)
    await backend.close()
