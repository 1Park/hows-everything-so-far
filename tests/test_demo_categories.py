"""Opt-in customer variants: no new visual model labels or automatic approval."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.clients import ModelClients
from app.controller import Controller
from app.language import parse_interpretation
from app.server import create_app
from common.api import ApiError
from common.config import Settings
from common.contracts import Interpretation, ObservedObject
from common.vision_categories import available_drinks
from tests.test_controller import observe, say, scene, confirmation


@pytest.fixture
async def controller():
    settings = Settings(qwen_backend="fixture", response_timeout=30)
    c = Controller(settings, ModelClients(settings))
    yield c
    await c.close()


@pytest.mark.parametrize(("group", "variants"), [
    ("water", ["water", "sparkling_water", "soda"]),
    ("coke", ["coke", "coke_zero", "coffee"]),
])
async def test_opt_in_menu_and_disable_invalidates_card(controller, group, variants):
    c = controller
    c.clients.vision = scene(group, 1.0)
    await observe(c)
    assert not c.state()["untrained_categories"]
    phrase = variants[1].replace("_", " ") + ", please"
    await say(c, phrase)
    assert c.phase == "not_understood" and c.card is None
    await c.set_demo_features(True)
    assert c.allowed_items() == variants
    assert c.state()["speech"] == c.message  # New board TTS names the same choices as the screen.
    await say(c, phrase)
    assert c.phase == "card" and c.card.item == variants[1]
    old = confirmation(c)
    await c.set_demo_features(False)
    assert c.card is None and c.phase == "offered"
    assert variants[1] not in c.allowed_items()
    with pytest.raises(ApiError):
        await c.confirm(old)
    assert not c.hardware.commands


async def test_controller_blocks_bad_llm_variant_even_when_schema_accepts(controller):
    c = controller
    c.clients.vision = scene("water", 1.0)
    await observe(c)

    async def bad_model(current, utterance):
        return Interpretation(intent="refill", item="soda"), "fixture"

    c.clients.language = bad_model
    await say(c, "soda please")
    assert c.phase == "not_understood" and c.card is None
    await c.set_demo_features(True)
    await say(c, "soda please")
    assert c.phase == "card" and c.card.item == "soda"


async def test_toggle_rejected_during_inference(controller):
    c = controller
    c.phase = "interpreting"
    with pytest.raises(ApiError):
        await c.set_demo_features(True)
    assert not c.untrained_categories


def test_feature_api_default_off_and_strict_input():
    with TestClient(create_app(Settings(qwen_backend="fixture"))) as client:
        assert client.get("/api/state").json()["untrained_categories"] is False
        assert client.post("/api/demo-features", json={"untrained_categories":"false"}).status_code == 422
        assert client.post("/api/demo-features", json={"untrained_categories":True}).json()["untrained_categories"] is True
        assert client.get("/api/state").json()["untrained_categories"] is True
    with TestClient(create_app(Settings(qwen_backend="fixture"))) as client:
        assert client.get("/api/state").json()["untrained_categories"] is False


def test_demo_does_not_expand_visual_schema():
    assert available_drinks(["water"], demo=True) == ["water", "sparkling_water", "soda"]
    with pytest.raises(ValidationError):
        ObservedObject(object_id="cup", bbox=dict(x1=0, y1=0, x2=1, y2=1), item="soda", confidence=1)
    assert parse_interpretation('{"intent":"refill","item":"coke_zero"}').item == "coke_zero"


async def test_orange_juice_stays_available_in_both_modes(controller):
    from services.vision.labels import to_observation
    assert to_observation([1.0], ["orange_juice__low"])["item"] == "orange_juice"
    c = controller
    c.clients.vision = scene("orange_juice", 1.0)
    await observe(c)
    assert c.allowed_items() == ["orange_juice"]
    await say(c, "OJ please")
    assert c.card.item == "orange_juice"
    await c.set_demo_features(True)
    assert c.allowed_items() == ["orange_juice"]
    await say(c, "Orange juice please")
    assert c.card.item == "orange_juice"
