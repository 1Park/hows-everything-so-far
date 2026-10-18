"""services.vision.backend (DINOv2 external backend) — checks the contract and error paths with fake runners. No model files needed."""

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
    """Pin the head so features [1, 0] classify as coke__low."""

    def run(self, xs):
        assert all(x.shape == (1, 3, 224, 224) and x.flags["C_CONTIGUOUS"] for x in xs)
        return [np.array([[1.0, 0.0]], np.float32) for _ in xs]


class FakeDetector:
    """Two boxes (cup, vase) at 640 input + one overlapping duplicate → 2 after agnostic NMS."""

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
    assert [o.object_id for o in result.objects] == ["cup-0", "cup-1"]  # duplicate box removed, left to right
    first = result.objects[0]
    assert first.item == "coke" and first.fill_ratio < 0.3 and first.confidence > 0.9
    assert first.bbox.x1 < first.bbox.x2 <= 1 and first.bbox.y1 < first.bbox.y2 <= 1


def test_rois_bundle(tmp_path):
    bundle = make_bundle(tmp_path, {"mode": "rois", "rois": [[0.1, 0.2, 0.2, 0.5], [0.6, 0.2, 0.2, 0.5]]})
    _, r = analyze(DinoVisionBackend(bundle, runners={"dino": FakeDino()}))
    objs = VisionResult.model_validate(r.json()).objects
    assert len(objs) == 2 and objs[0].bbox.x1 == pytest.approx(0.1) and objs[1].bbox.x2 == pytest.approx(0.8)


def test_missing_bundle_is_not_ready_without_fallback(tmp_path):
    from common.api import ApiError

    with pytest.raises(ApiError, match="Vision startup failed"):
        analyze(DinoVisionBackend(tmp_path / "missing"))


def test_bundle_path_from_settings(tmp_path):
    """The backend also reads VISION_MODEL_PATH set only in an env file like .env.board
    (not os.environ)."""
    bundle = make_bundle(tmp_path, {"mode": "center"})
    settings = Settings(vision_model_path=str(bundle), vision_runner_bin="/opt/runner")
    backend = DinoVisionBackend(runners={"dino": FakeDino()}, settings=settings)
    assert backend.path == bundle and backend.runner_bin == "/opt/runner"
    _, r = analyze(backend)
    assert r.status_code == 200 and len(r.json()["objects"]) == 1


def test_label_conversion():
    obs = to_observation([0.05, 0.05, 0.9], ["water__full", "coke__mid", "empty"])
    assert obs["item"] == "unknown" and obs["fill_ratio"] < 0.1 and obs["confidence"] == pytest.approx(0.9)
    obs = to_observation([0.5, 0.5], ["coffee__low", "coffee__full"])
    assert obs["item"] == "coke" and obs["confidence"] == pytest.approx(0.5)
    assert obs["fill_ratio"] == pytest.approx((0.18 + 0.85) / 2)
    assert obs["item_confidence"] == pytest.approx(1.0)  # drink is certain, only the level is ambiguous
    obs = to_observation([0.6, 0.3, 0.1], ["coke__low", "coffee__low", "empty"])
    assert obs["item"] == "coke" and obs["item_confidence"] == pytest.approx(1.0)
    assert to_observation([0.1, 0.9], ["coke__low", "empty"])["item_confidence"] is None


def test_category_merge_preserves_fill_and_combines_probability_mass():
    classes = ["coffee__full", "coke__low", "water__mid"]
    obs = to_observation([0.3, 0.3, 0.4], classes)
    assert obs["item"] == "coke"  # The merged .6 beats water's .4.
    assert obs["item_confidence"] == pytest.approx(.6)
    assert obs["fill_ratio"] == pytest.approx(.3 * .85 + .3 * .18 + .4 * .5)
    assert obs["confidence"] == pytest.approx(.4)  # Levels remain uncertain.
    assert to_observation([1.0], ["coffee__low"])["item"] == "coke"


def test_category_mapping_is_read_only():
    from app.server import create_app
    with TestClient(create_app(Settings(qwen_backend="fixture"))) as client:
        mapping = client.get("/api/vision-categories").json()
        assert mapping["groups"] == {"water": ["water"], "coke": ["coke", "coffee"], "orange_juice": ["orange_juice"]}
        assert mapping["editable"] is False
        assert client.post("/api/vision-categories", json={"groups": {}}).status_code == 405


def test_confidence_treats_low_and_empty_as_one_refill_level():
    # Seen on the board: a glass with a little water left split between water__low and empty,
    # giving confidence ~0.5 → no suggestion
    obs = to_observation([0.5, 0.4, 0.1], ["water__low", "empty", "water__mid"])
    assert obs["item"] == "water" and obs["confidence"] == pytest.approx(0.9)  # before: min(0.6, 0.5) = 0.5
    obs = to_observation([0.5, 0.4, 0.1], ["empty", "water__low", "water__full"])
    assert obs["item"] == "unknown" and obs["confidence"] == pytest.approx(0.9)  # same rule on the empty-cup side
    # low↔full is still uncertain, but coke↔coffee are in the same group.
    assert to_observation([0.5, 0.5], ["coffee__low", "coffee__full"])["confidence"] == pytest.approx(0.5)
    obs = to_observation([0.45, 0.45, 0.1], ["coke__low", "coffee__low", "empty"])
    assert obs["confidence"] == pytest.approx(1.0)
    # full↔mid are not merged
    assert to_observation([0.5, 0.5], ["water__full", "water__mid"])["confidence"] == pytest.approx(0.5)


class FakeDinoByPosition:
    """Left crop gets cup features [1,0,0], right gets can features [0,0,1] (told apart by call
    order, not by mean crop brightness)."""

    def run(self, xs):
        return [np.array([[1.0, 0.0, 0.0]] if i == 0 else [[0.0, 0.0, 1.0]], np.float32) for i in range(len(xs))]


def test_other_class_is_dropped(tmp_path):
    head = dict(classes=["coke__low", "water__full", "other"], mean=[0.0] * 3, scale=[1.0] * 3,
                W=[[4.0, 0.0, 0.0], [0.0, 4.0, 0.0], [0.0, 0.0, 4.0]], b=[0.0] * 3)
    (tmp_path / "head.json").write_text(json.dumps(head))
    cfg = {"version": 1, "boxes": {"mode": "rois", "rois": [[0.1, 0.2, 0.2, 0.5], [0.6, 0.2, 0.2, 0.5]]},
           "dino": {"pte": "dino.pte", "runner": "py", "out_shape": [1, 3]}, "head": "head.json"}
    (tmp_path / "bundle.json").write_text(json.dumps(cfg))
    _, r = analyze(DinoVisionBackend(tmp_path, runners={"dino": FakeDinoByPosition()}))
    objs = VisionResult.model_validate(r.json()).objects
    assert [o.object_id for o in objs] == ["cup-0"] and objs[0].item == "coke"
    assert objs[0].confidence > 0.9  # renormalized without the other probability


def test_split_other():
    from services.vision.labels import split_other

    drop, p, cls = split_other([0.2, 0.2, 0.6], ["coke__low", "empty", "other"])
    assert drop and cls == ["coke__low", "empty"] and p == pytest.approx([0.5, 0.5])
    drop, p, cls = split_other([0.7, 0.3], ["coke__low", "empty"])
    assert not drop and cls == ["coke__low", "empty"]
    # drop when other is the top class even below 0.5 (board: snack bag overlapping an orange
    # juice glass, 0.47 vs 0.38)
    assert split_other([0.38, 0.15, 0.47], ["orange_juice__low", "coke__low", "other"])[0]
    assert not split_other([0.45, 0.15, 0.40], ["orange_juice__low", "coke__low", "other"])[0]
