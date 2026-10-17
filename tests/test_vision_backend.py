"""services.vision.backend (DINOv2 external backend) — 가짜 runner로 계약·오류 경로 검증. 모델 파일 불필요."""

import json

import pytest

np = pytest.importorskip("numpy")

from fastapi.testclient import TestClient  # noqa: E402

from common.config import ROOT, Settings  # noqa: E402
from common.contracts import VisionResult  # noqa: E402
from services.sensory import create_sensory_app  # noqa: E402
from services.vision.backend import DinoVisionBackend  # noqa: E402
from services.vision.labels import to_observation  # noqa: E402

CLASSES = ["coke__low", "water__full"]
IMAGE = ROOT / "docs/assets/cups-example.jpg"


class FakeDino:
    """특징 [1, 0] → head가 coke__low 로 분류하도록 고정."""

    def run(self, xs):
        assert all(x.shape == (1, 3, 224, 224) and x.flags["C_CONTIGUOUS"] for x in xs)
        return [np.array([[1.0, 0.0]], np.float32) for _ in xs]


class FakeDetector:
    """640 입력 기준 박스 2개 (cup, vase) + 겹치는 이중 박스 1개 → agnostic NMS 후 2개."""

    def run(self, xs):
        out = np.zeros((1, 84, 8400), np.float32)
        for i, (cx, cy, w, h, cls, s) in enumerate(
            [(200, 320, 120, 200, 41, 0.9), (205, 322, 118, 196, 75, 0.5), (450, 320, 120, 200, 75, 0.8)]
        ):
            out[0, :4, i] = (cx, cy, w, h)
            out[0, 4 + cls, i] = s
        return [out]


def make_bundle(tmp_path, boxes):
    head = dict(classes=CLASSES, mean=[0.0, 0.0], scale=[1.0, 1.0], W=[[4.0, 0.0], [-4.0, 0.0]], b=[0.0, 0.0])
    (tmp_path / "head.json").write_text(json.dumps(head))
    cfg = {"version": 1, "boxes": boxes, "dino": {"pte": "dino.pte", "runner": "py", "out_shape": [1, 2]},
           "head": "head.json"}
    (tmp_path / "bundle.json").write_text(json.dumps(cfg))
    return tmp_path


def analyze(backend):
    settings = Settings(vision_model_backend="external", vision_adapter="services.vision.backend:create_backend")
    app = create_sensory_app("vision", settings, backend)
    with TestClient(app) as c:
        ready = c.get("/ready")
        r = c.post("/v1/analyze", data={"scene_id": "scene-1"},
                   files={"file": ("a.jpg", IMAGE.read_bytes(), "image/jpeg")})
    return ready, r


def test_yolo_bundle_returns_contract_objects(tmp_path):
    bundle = make_bundle(tmp_path, {"mode": "yolo", "pte": "detector.pte", "runner": "py", "crop_scale": 1.35})
    ready, r = analyze(DinoVisionBackend(bundle, runners={"dino": FakeDino(), "detector": FakeDetector()}))
    assert ready.status_code == 200 and ready.json()["ready"] is True
    assert r.status_code == 200, r.text
    result = VisionResult.model_validate(r.json())
    assert result.scene_id == "scene-1" and result.source == "external"
    assert [o.object_id for o in result.objects] == ["cup-0", "cup-1"]  # 이중 박스 제거, 왼쪽부터
    first = result.objects[0]
    assert first.item == "coke" and first.fill_ratio < 0.3 and first.confidence > 0.9
    assert first.bbox.x1 < first.bbox.x2 <= 1 and first.bbox.y1 < first.bbox.y2 <= 1


def test_rois_bundle(tmp_path):
    bundle = make_bundle(tmp_path, {"mode": "rois", "rois": [[0.1, 0.2, 0.2, 0.5], [0.6, 0.2, 0.2, 0.5]]})
    _, r = analyze(DinoVisionBackend(bundle, runners={"dino": FakeDino()}))
    objs = VisionResult.model_validate(r.json()).objects
    assert len(objs) == 2 and objs[0].bbox.x1 == pytest.approx(0.1) and objs[1].bbox.x2 == pytest.approx(0.8)


def test_missing_bundle_is_not_ready_without_fallback(tmp_path):
    ready, r = analyze(DinoVisionBackend(tmp_path / "missing"))
    assert ready.status_code == 503 and ready.json()["ready"] is False
    assert r.status_code == 503 and "fixture" not in r.text


def test_label_conversion():
    obs = to_observation([0.05, 0.05, 0.9], ["water__full", "coke__mid", "empty"])
    assert obs["item"] == "unknown" and obs["fill_ratio"] < 0.1 and obs["confidence"] == pytest.approx(0.9)
    obs = to_observation([0.5, 0.5], ["coffee__low", "coffee__full"])
    assert obs["item"] == "coffee" and obs["confidence"] == pytest.approx(0.5)
    assert obs["fill_ratio"] == pytest.approx((0.18 + 0.85) / 2)
