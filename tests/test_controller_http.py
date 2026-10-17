import time

from fastapi.testclient import TestClient

from app.server import create_app
from common.config import Settings


def test_real_routes_ws_and_confirm_identity():
    settings = Settings(qwen_backend="fixture", mock_step_seconds=0.02)
    with TestClient(create_app(settings)) as c:
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["state"]["phase"] == "idle"
            assert c.post("/api/observe").status_code == 202
            assert ws.receive_json()["state"]["phase"] == "observing"
            s = ws.receive_json()["state"]
            assert s["phase"] == "offered"
            assert c.get(s["snapshot_url"]).headers["content-type"] == "image/jpeg"
            body = {
                "scene_id": s["scene"]["scene_id"],
                "object_id": s["target"]["object_id"],
                "utterance": "A little water please",
            }
            c.post("/api/utterance", json=body).raise_for_status()
            assert ws.receive_json()["state"]["phase"] == "interpreting"
            card = ws.receive_json()["state"]["card"]
            identity = {k: v for k, v in card.items() if k not in ("item", "portion")}
            assert (
                c.post("/api/confirm", json={**identity, "object_id": "different-cup"}).status_code
                == 409
            )
            assert c.post("/api/confirm", json=identity).status_code == 202
            assert c.post("/api/confirm", json=identity).status_code == 409
            time.sleep(0.1)
            assert c.get("/api/state").json()["phase"] == "done"
            assert c.get("/missing").json()["error"]["code"] == "http_error"


def test_raw_body_transport_limit():
    settings = Settings(qwen_backend="fixture")
    with TestClient(create_app(settings)) as c:
        r = c.post(
            "/api/observe",
            content=b"x" * 26_000_001,
            headers={"content-type": "application/octet-stream"},
        )
        assert r.status_code == 413 and r.json()["error"]["code"] == "invalid_size"
