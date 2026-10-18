import asyncio
import io
import wave

import pytest
from fastapi.testclient import TestClient

from app.clients import ModelClients
from app.controller import Controller
from app.server import create_app
from common.api import ApiError
from common.config import ROOT, Settings
from common.contracts import ListenInput


def settings(**kwargs):
    return Settings(qwen_backend="fixture", audio_input="fixture", **kwargs)


async def offer(c):
    await c.start((ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg", "normal")
    while c.phase == "observing":
        await asyncio.sleep(0.005)
    return ListenInput(
        session_id=c.session_id,
        sequence=c.sequence,
        scene_id=c.scene.scene_id,
        object_id=c.target.object_id,
    )


async def test_voice_waits_for_playback_ack_and_creates_card():
    s = settings()
    c = Controller(s, ModelClients(s))
    try:
        ack = await offer(c)
        await asyncio.sleep(0.1)
        assert c.phase == "offered"  # no browser playback ack -> no recording
        await c.listen(ack)
        assert c.phase == "listening"
        with pytest.raises(ApiError) as duplicate:
            await c.listen(ack)
        assert duplicate.value.status == 409
        for _ in range(100):
            if c.phase == "card":
                break
            await asyncio.sleep(0.01)
        assert c.phase == "card"
        assert c.transcript == "A little water, please" and c.stt_source == "fixture"
        assert not c.hardware.commands  # speech cannot approve movement
    finally:
        await c.close()


async def test_automatic_observation_cannot_replace_an_active_offer():
    s = settings()
    c = Controller(s, ModelClients(s))
    try:
        await offer(c)
        session = c.session_id
        await c.start(b"another frame", "image/jpeg", "normal", automatic=True)
        assert c.session_id == session and c.phase == "offered"
    finally:
        await c.close()


async def test_cancel_kills_capture_and_rejects_late_prompt():
    s = settings()
    c = Controller(s, ModelClients(s))
    stopped = asyncio.Event()

    async def capture():
        try:
            await asyncio.sleep(60)
        finally:
            stopped.set()

    c.microphone.capture = capture
    try:
        ack = await offer(c)
        await c.listen(ack)
        await asyncio.sleep(0)
        await c.cancel(c.session_id)
        await asyncio.wait_for(stopped.wait(), 0.5)
        assert c.phase == "cancelled" and c.card is None
        with pytest.raises(ApiError):
            await c.listen(ack)
        await offer(c)
        with pytest.raises(ApiError):
            await c.listen(ack)
    finally:
        await c.close()


async def test_cancel_discards_late_stt():
    s = settings()
    clients = ModelClients(s)
    entered, release = asyncio.Event(), asyncio.Event()
    original = clients.stt

    async def stt(*args):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            pass  # even a backend that swallows cancellation cannot restore this request
        return await original(*args)

    clients.stt = stt
    c = Controller(s, clients)
    try:
        await c.listen(await offer(c))
        await asyncio.wait_for(entered.wait(), 1)
        await c.cancel(c.session_id)
        release.set()
        await asyncio.sleep(0.05)
        assert c.phase == "cancelled" and c.card is None
    finally:
        await c.close()


def test_automatic_observation_updates_ui_state_without_click():
    with TestClient(create_app(settings(observe_interval_seconds=0.2,
                                        auto_capture_stable_seconds=0.2))) as client:
        import time

        for _ in range(100):
            state = client.get("/api/state").json()
            if state["phase"] == "offered":
                break
            time.sleep(0.01)
        assert state["phase"] == "offered"
        assert state["audio_input"] == "fixture"


async def test_microphone_fixture_is_valid_wav():
    from app.audio import BoardMicrophone

    data = await BoardMicrophone(settings()).capture()
    with wave.open(io.BytesIO(data)) as audio:
        assert audio.getnframes() > 0


async def test_cancel_reaps_real_capture_child(monkeypatch):
    import sys
    from app.audio import BoardMicrophone

    original = asyncio.create_subprocess_exec
    children = []

    async def launch(*args, **kwargs):
        process = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    monkeypatch.setattr("shutil.which", lambda name: sys.executable)
    microphone = BoardMicrophone(Settings(audio_input="alsa", audio_device="test-device"))
    task = asyncio.create_task(microphone.capture())
    while not children:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None


async def test_existing_whisper_http_contract_and_empty_result(monkeypatch):
    import httpx
    from services.stt.whisper_http import WhisperHTTP

    received = []

    def respond(request):
        received.append(request)
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"text": "Coffee instead, please"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    backend = WhisperHTTP(settings())
    assert await backend.ready()
    result = await backend.infer(b"original-audio", "audio/wav")
    assert result.source == "external" and result.text == "Coffee instead, please"
    assert received[-1].url.path == "/inference"
    assert b"original-audio" in received[-1].content

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            **kwargs,
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"text": " "})),
        ),
    )
    with pytest.raises(ApiError) as error:
        await backend.infer(b"original-audio", "audio/wav")
    assert error.value.code == "no_speech"


def test_stt_takes_survive_a_reload(tmp_path, monkeypatch):
    # Measurements cost real speaking, so a refresh must not discard them.
    from fastapi.testclient import TestClient

    import app.server as server

    monkeypatch.setenv("STT_TAKES_FILE", str(tmp_path / "takes.json"))
    with TestClient(server.create_app()) as client:
        assert client.get("/api/stt/results").json() == {"takes": []}
        take = {
            "expected": "a little water",
            "heard": "a little water",
            "wer": 0.0,
            "seconds": 4,
            "source": "external",
            "at": "2026-10-18T01:00:00Z",
        }
        assert client.post("/api/stt/results", json=take).status_code == 200
        assert client.post("/api/stt/results", json={**take, "heard": "a little otter",
                                                     "wer": 0.25}).status_code == 200

    # A new app instance stands in for a reloaded page or a second device.
    with TestClient(server.create_app()) as client:
        assert len(client.get("/api/stt/results").json()["takes"]) == 2
        assert len(client.request("DELETE", "/api/stt/results?index=0").json()["takes"]) == 1
        assert client.request("DELETE", "/api/stt/results").json() == {"takes": []}
    assert (tmp_path / "takes.json").exists()  # the repo copy was never touched


async def test_voice_retries_stop_after_two_attempts():
    # The tablet records again the moment the phase reaches not_understood, so a
    # microphone that hears nothing would loop until the request expired.
    from app.clients import ModelClients
    from app.controller import Controller
    from common.config import load_settings

    settings = load_settings(None)
    controller = Controller(settings, ModelClients(settings))
    controller.token = 7

    for attempt in (1, 2):
        await controller.retry_voice(7, "say again")
        assert controller.phase == "not_understood", f"attempt {attempt} should ask again"

    await controller.retry_voice(7, "say again")
    assert controller.phase == "error", "a third failure should stop asking"
    assert "type it" in controller.message

    # A fresh observation starts over rather than inheriting the spent budget.
    from common.contracts import VisionResult

    controller.voice_retries = 9
    controller.apply_observation(VisionResult(scene_id="s1", objects=[], source="fixture"))
    assert controller.voice_retries == 0
