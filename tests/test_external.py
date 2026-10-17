import asyncio

import pytest
from fastapi.testclient import TestClient

from common.config import ROOT, Settings
from services.sensory import create_sensory_app
from tests.test_services import wav


class External:
    def __init__(self, kind, behavior):
        self.kind, self.behavior = kind, behavior

    async def ready(self):
        return self.behavior != "not-ready"

    async def infer(self, *args):
        if self.behavior == "timeout":
            await asyncio.sleep(1)
        if self.behavior == "crash":
            raise RuntimeError("model failure")
        if self.behavior == "invalid":
            return {"output": "wrong schema"}
        if self.kind == "stt":
            return {"text": "Coffee please", "language": "en", "source": "external"}
        return {"scene_id": args[2], "source": "external", "objects": []}


@pytest.mark.parametrize("kind", ["vision", "stt"])
@pytest.mark.parametrize(
    ("behavior", "status"), [("ok", 200), ("invalid", 502), ("crash", 502), ("timeout", 504)]
)
def test_external_transport_and_errors(kind, behavior, status):
    settings = Settings(
        **{f"{kind}_model_backend": "external", f"{kind}_adapter": "test:factory"},
        inference_timeout=0.05,
    )
    app = create_sensory_app(kind, settings, External(kind, behavior))
    with TestClient(app) as c:
        if kind == "vision":
            r = c.post(
                "/v1/analyze",
                data={"scene_id": "input-scene"},
                files={
                    "file": (
                        "a.jpg",
                        (ROOT / "docs/assets/cups-example.jpg").read_bytes(),
                        "image/jpeg",
                    )
                },
            )
        else:
            r = c.post("/v1/transcribe", files={"file": ("a.wav", wav(), "audio/wav")})
        assert r.status_code == status, r.text
        if status == 200:
            assert r.json()["source"] == "external"
        else:
            assert "error" in r.json() and "fixture" not in r.text


def test_external_readiness_and_missing_configuration():
    settings = Settings(vision_model_backend="external", vision_adapter="test:factory")
    with TestClient(create_sensory_app("vision", settings, External("vision", "not-ready"))) as c:
        assert c.get("/ready").status_code == 503
    with pytest.raises(ValueError):
        Settings(vision_model_backend="external")
