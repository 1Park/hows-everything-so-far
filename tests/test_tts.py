import io
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.clients import ModelClients
from app.server import create_app as create_controller
from app.speech import speech_for
from common.config import Settings
from common.contracts import ObservedObject, RequestCard
from services.tts.backend import HOP, PiperTTS, to_wav
from services.tts.server import create_app


def obj(item, item_confidence=0.95):
    return ObservedObject(object_id="cup-0", bbox={"x1": 0.1, "y1": 0.1, "x2": 0.3, "y2": 0.5}, item=item,
                          fill_ratio=0.2, confidence=0.9, item_confidence=None if item == "unknown" else item_confidence)


def card(item):
    return RequestCard(request_id="r", revision=1, scene_id="s", object_id="cup-0", item=item)


def test_speech_lines_name_the_drink_and_cover_each_outcome():
    assert speech_for("offered", obj("water"), None, 0.8) == "How is everything? Can I get you some more water?"
    assert speech_for("offered", obj("coke", 0.6), None, 0.8) == "How is everything? Can I get you some more coke?"
    assert speech_for("offered", obj("unknown"), None, 0.8) == "How is everything? Can I get you a refill?"
    assert speech_for("card", obj("water"), card("coffee"), 0.8).startswith("One more coffee")
    assert "call me if you need anything" in speech_for("declined", None, None, 0.8)
    assert "didn't catch that" in speech_for("not_understood", None, None, 0.8)
    assert speech_for("done", obj("water"), card("coke"), 0.8) == "Your coke refill is on its way."
    assert speech_for("offered", obj("orange_juice"), None, 0.8) == "How is everything? Can I get you some more orange juice?"
    assert speech_for("card", None, card("orange_juice"), 0.8).startswith("One more orange juice")
    assert speech_for("observing", None, None, 0.8) is None and speech_for("skipped", None, None, 0.8) is None


class FakeTTS:
    status = {"decoder": "npu", "npu_frames": [128, 256]}
    last = {"total_ms": 1}

    def synthesize(self, text):
        return to_wav(np.zeros(2205, np.float32), 22050)


def test_tts_service_speaks_wav_and_validates_text():
    with TestClient(create_app(Settings(), backend=FakeTTS())) as c:
        assert c.get("/ready").json()["tts"]["decoder"] == "npu"
        r = c.post("/v1/speak", json={"text": "Hello"})
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        with wave.open(io.BytesIO(r.content)) as w:
            assert w.getframerate() == 22050 and w.getnframes() == 2205
        assert c.post("/v1/speak", json={"text": ""}).status_code == 422
        assert c.post("/v1/speak", json={"text": "x" * 401}).status_code == 422


def test_tts_service_reports_not_ready_without_a_voice(tmp_path):
    with TestClient(create_app(Settings(tts_voice_path=str(tmp_path / "missing.onnx")))) as c:
        r = c.get("/ready")
        assert r.status_code == 503 and r.json()["error"]
        assert c.post("/v1/speak", json={"text": "Hello"}).status_code == 503


class FakeRunner:
    def __init__(self, frames):
        self.frames, self.calls = frames, []

    def run(self, xs):
        self.calls.append(xs[0].shape)
        return [np.arange(self.frames * HOP, dtype=np.float32).reshape(1, 1, 1, -1)]


class FakeDec:
    def run(self, _, feeds):
        z = next(iter(feeds.values()))
        return [np.full((1, 1, 1, z.shape[2] * HOP), -1.0, np.float32)]


def test_decoder_picks_smallest_npu_length_and_falls_back_to_cpu():
    tts = object.__new__(PiperTTS)
    tts.npu = {128: FakeRunner(128), 256: FakeRunner(256)}
    tts.dec, tts.z_name = FakeDec(), "z"
    audio, how = tts.decode(np.ones((1, 192, 100), np.float32))
    assert how == "npu128" and tts.npu[128].calls == [(1, 192, 128)] and audio.size == 100 * HOP
    assert tts.decode(np.ones((1, 192, 200), np.float32))[1] == "npu256"
    audio, how = tts.decode(np.ones((1, 192, 300), np.float32))
    assert how == "cpu" and audio.size == 300 * HOP and audio[0] == -1.0


def test_controller_serves_the_current_state_line(monkeypatch):
    spoken = []

    async def fake_speech(self, text):
        spoken.append(text)
        return to_wav(np.zeros(100, np.float32), 22050)

    monkeypatch.setattr(ModelClients, "speech", fake_speech)
    settings = Settings(qwen_backend="fixture", mock_step_seconds=0.02)
    with TestClient(create_controller(settings)) as c:
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            c.post("/api/observe").raise_for_status()
            ws.receive_json()
            s = ws.receive_json()["state"]
        assert s["phase"] == "offered" and s["speech"] == "How is everything? Can I get you some more water?"
        r = c.get(f"/api/speech/{s['session_id']}/{s['sequence']}")
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
        assert spoken == [s["speech"]]
        assert c.get("/api/speech-preview").status_code == 200
        assert spoken[-1] == "Hello. How is everything so far? Would you like a refill?"
        assert c.get(f"/api/speech/{s['session_id']}/{s['sequence'] - 1}").status_code == 409
        assert c.get("/ready").json()["tts"]["source"] == "disabled"


def test_controller_speech_is_disabled_by_default():
    settings = Settings(qwen_backend="fixture")
    with TestClient(create_controller(settings)) as c:
        with c.websocket_connect("/ws") as ws:
            ws.receive_json()
            c.post("/api/observe").raise_for_status()
            ws.receive_json()
            s = ws.receive_json()["state"]
        r = c.get(f"/api/speech/{s['session_id']}/{s['sequence']}")
        assert r.status_code == 404 and r.json()["error"]["code"] == "tts_disabled"
        assert c.get("/api/speech-preview").json()["error"]["code"] == "tts_disabled"


@pytest.mark.parametrize("phase", ["idle", "observing", "listening", "skipped"])
def test_silent_phases(phase):
    assert speech_for(phase, None, None, 0.8) is None


async def test_fixture_language_backend_understands_orange_juice():
    import json

    from common.backends import FixtureTextBackend
    from common.contracts import Generation, Message

    def ask(utterance):
        content = json.dumps({"current_request": {"item": "water"}, "utterance": utterance})
        return Generation(model="m", messages=[Message(role="user", content=content)])

    out = await FixtureTextBackend().generate(ask("An orange juice please"))
    assert json.loads(out["choices"][0]["message"]["content"]) == {"intent": "refill", "item": "orange_juice"}
    out = await FixtureTextBackend().generate(ask("Apple juice please"))
    assert json.loads(out["choices"][0]["message"]["content"])["intent"] == "not_understood"
