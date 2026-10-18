import json

import pytest
from pydantic import ValidationError

from app.language import generation, parse_interpretation
from common.api import ApiError
from common.config import load_settings
from common.contracts import BBox, CurrentRequest, Interpretation, VisionResult


def test_env_priority_and_validation(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("CONTROLLER_PORT=8123\nVISION_BACKEND=fixture\n")
    monkeypatch.setenv("CONTROLLER_PORT", "8124")
    assert load_settings(env).controller_port == 8124
    monkeypatch.setenv("CONTROLLER_PORT", "99999")
    with pytest.raises(ValidationError):
        load_settings(env)


def test_bbox_and_duplicate_ids():
    with pytest.raises(ValidationError):
        BBox(x1=0.6, y1=0, x2=0.5, y2=1)
    with pytest.raises(ValidationError):
        BBox(x1=0, y1=0, x2=float("nan"), y2=1)
    from common.config import ROOT

    value = json.loads((ROOT / "fixtures/vision.json").read_text())
    value["objects"].append(value["objects"][0])
    with pytest.raises(ValidationError):
        VisionResult.model_validate(value)


@pytest.mark.parametrize(
    "raw",
    [
        'Here is your request: {"intent":"cancel","item":null}',
        '{"intent":"refill","item":"tea"}',
        '{"intent":"refill","item":"water","portion":"huge"}',
        '{"intent":"refill","item":"water","portion":"small"}',
        '{"intent":"refill","item":null}',
        '{"intent":"refill"}',
        '{"intent":"cancel","item":"water"}',
        '{"intent":"not_understood","item":"water"}',
        '{"intent":"clarify","item":null}',
        '{"intent":"cancel","intent":"refill","item":"water"}',
        '{"intent":"refill","item":"water","confirm":true}',
    ],
)
def test_model_output_is_strict(raw):
    with pytest.raises(ApiError):
        parse_interpretation(raw)


def test_single_fence_allowed():
    result = parse_interpretation(
        '```json\n{"intent":"refill","item":"water"}\n```'
    )
    assert result == Interpretation(intent="refill", item="water")


def test_not_understood_output():
    assert parse_interpretation('{"intent":"not_understood","item":null}') == Interpretation(
        intent="not_understood", item=None
    )


def test_generation_uses_item_only_context():
    body = generation("test", CurrentRequest(item="coffee"), "Same again please")
    assert json.loads(body.messages[1].content) == {
        "current_request": {"item": "coffee"}, "utterance": "Same again please",
        "allowed_items": ["water", "coke", "coffee", "orange_juice"],
    }


def test_generation_supplies_observed_group_menu():
    body = generation("test", CurrentRequest(item="coke", allowed_items=["coke", "coffee"]), "Coffee please")
    payload = json.loads(body.messages[1].content)
    assert payload["allowed_items"] == ["coke", "coffee"]
    assert "MUST belong to allowed_items" in body.messages[0].content


def test_scene_category_expansion():
    from common.vision_categories import available_drinks
    assert available_drinks(["unknown"]) == []
    assert available_drinks(["water"]) == ["water"]
    assert available_drinks(["coke", "coffee", "coke"]) == ["coke", "coffee"]
    assert available_drinks(["coke", "water"]) == ["water", "coke", "coffee"]


def test_item_confidence_is_optional_and_bounded():
    import pytest
    from pydantic import ValidationError

    from common.contracts import ObservedObject

    base = {"object_id": "c", "bbox": {"x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2},
            "item": "coke", "fill_ratio": 0.2, "confidence": 0.9}
    assert ObservedObject.model_validate(base).item_confidence is None
    assert ObservedObject.model_validate({**base, "item_confidence": 0.75}).item_confidence == 0.75
    with pytest.raises(ValidationError):
        ObservedObject.model_validate({**base, "item_confidence": 1.2})
