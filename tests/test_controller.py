import asyncio

import pytest

from app.clients import ModelClients
from app.controller import Controller
from common.api import ApiError
from common.config import ROOT, Settings
from common.contracts import ConfirmInput, UtteranceInput


async def settled(c):
    for _ in range(300):
        if c.phase not in ("observing", "interpreting", "loading", "returning"):
            return c.state()
        await asyncio.sleep(0.005)
    raise AssertionError(c.state())


@pytest.fixture
async def controller():
    settings = Settings(require_confirmation=True, qwen_backend="fixture", mock_step_seconds=0.01, response_timeout=1)
    c = Controller(settings, ModelClients(settings))
    yield c
    await c.close()


async def observe(c, scenario="normal"):
    await c.start((ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg", scenario)
    await settled(c)


async def say(c, text):
    await c.utterance(
        UtteranceInput(scene_id=c.scene.scene_id, object_id=c.target.object_id, utterance=text)
    )
    await settled(c)


def confirmation(c):
    return ConfirmInput(**c.card.model_dump(exclude={"item"}))


async def test_full_refill_and_edit(controller):
    c = controller
    await observe(c)
    assert c.phase == "offered" and not c.hardware.commands
    await say(c, "A little water, please")
    old = confirmation(c)
    assert c.card.item == "water" and not c.hardware.commands
    await say(c, "Coffee instead, regular please")
    assert c.card.item == "coffee"
    with pytest.raises(ApiError, match="changed"):
        await c.confirm(old)
    confirm = confirmation(c)
    await c.confirm(confirm)
    with pytest.raises(ApiError):
        await c.confirm(confirm)
    await settled(c)
    assert c.phase == "done" and len(c.hardware.commands) == 1
    assert c.qwen_source == "fixture"


@pytest.mark.parametrize("scenario", ["enough", "uncertain"])
async def test_skip(controller, scenario):
    await observe(controller, scenario)
    assert controller.phase == "skipped" and controller.card is None


@pytest.mark.parametrize(
    ("text", "phase"),
    [("No thanks", "declined"), ("Cancel that", "cancelled"), ("Maybe tea", "not_understood")],
)
async def test_non_refill(controller, text, phase):
    await observe(controller)
    await say(controller, text)
    assert controller.phase == phase and not controller.hardware.commands


async def test_not_understood_blocks_confirmation_and_allows_retry(controller):
    c = controller
    await observe(c)
    await say(c, "A little water, please")
    assert "portion" not in c.card.model_dump()
    old = confirmation(c)
    await say(c, "Maybe, I'm not sure")
    assert c.phase == "not_understood" and "understand" in c.message
    with pytest.raises(ApiError):
        await c.confirm(old)
    assert not c.hardware.commands
    await say(c, "Coffee instead")
    assert c.phase == "card" and c.card.item == "coffee"
    with pytest.raises(ApiError):
        await c.confirm(old)


async def test_stale_scene_and_cancel(controller):
    c = controller
    await observe(c)
    await say(c, "yes please")
    old = confirmation(c)
    await c.cancel(c.session_id)
    with pytest.raises(ApiError):
        await c.confirm(old)
    await observe(c)
    with pytest.raises(ApiError):
        await c.confirm(old)
    assert not c.hardware.commands


async def test_late_inference_after_cancel(controller):
    c = controller
    await observe(c)
    started, release = asyncio.Event(), asyncio.Event()
    original = c.clients.language

    async def delayed(*args):
        started.set()
        await release.wait()
        return await original(*args)

    c.clients.language = delayed
    await c.utterance(
        UtteranceInput(scene_id=c.scene.scene_id, object_id=c.target.object_id, utterance="yes")
    )
    await started.wait()
    await c.cancel(c.session_id)
    release.set()
    await asyncio.sleep(0.1)
    assert c.phase == "cancelled" and c.card is None and not c.hardware.commands


async def test_confirmation_cancel_race(controller):
    c = controller
    await observe(c)
    await say(c, "yes")
    await c.confirm(confirmation(c))
    await c.cancel(c.session_id)  # hardware task hasn't run yet
    await asyncio.sleep(0.05)
    assert not c.hardware.commands and c.phase == "cancelled"


async def test_timeout_error_retry(controller):
    c = controller
    await observe(c)
    original = c.clients.language

    async def broken(*args):
        raise ApiError("invalid_model_output", "Invalid response", 502, True)

    c.clients.language = broken
    await say(c, "yes")
    assert c.phase == "error"
    c.clients.language = original
    await say(c, "yes")
    assert c.phase == "card"


async def test_no_response_expiry(controller):
    c = controller
    c.settings.response_timeout = 0.05
    await observe(c)
    await asyncio.sleep(0.07)
    assert c.phase == "expired" and not c.hardware.commands


async def test_language_timeout_and_state_responsive(controller):
    c = controller
    await observe(c)
    c.settings.inference_timeout = 0.05

    async def stuck(*args):
        await asyncio.sleep(1)

    c.clients.language = stuck
    await c.utterance(
        UtteranceInput(scene_id=c.scene.scene_id, object_id=c.target.object_id, utterance="yes")
    )
    assert c.state()["phase"] == "interpreting"
    await settled(c)
    assert c.phase == "error" and c.last_error["code"] == "qwen_timeout"


def scene(item, item_confidence, fill=0.15):
    from common.contracts import VisionResult

    async def fake(data, content_type, scene_id, scenario):
        return VisionResult.model_validate({
            "scene_id": scene_id, "source": "external",
            "objects": [{"object_id": "cup-0", "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.3, "y2": 0.7},
                         "item": item, "fill_ratio": fill, "confidence": 0.9,
                         "item_confidence": item_confidence}],
        })
    return fake


@pytest.mark.parametrize(
    ("item", "item_confidence", "category"),
    [("coke", 0.6, "coke"), ("coffee", 0.79, "coke"), ("coke", 0.95, "coke"),
     ("coke", None, "coke"), ("water", 0.5, "water")],
)
async def test_offer_names_category_and_reply_selects_drink(controller, item, item_confidence, category):
    c = controller
    c.clients.vision = scene(item, item_confidence)
    await observe(c)
    assert c.phase == "offered"
    message = c.state()["message"]
    assert message == f"How is everything? Can I get you some more {category}?"
    assert c.state()["speech"] == message
    await say(c, "Coffee, please")
    if item == "water":
        assert c.phase == "not_understood" and c.card is None
    else:
        assert c.phase == "card" and c.card.item == "coffee"


async def test_llm_cannot_select_outside_observed_groups(controller):
    from common.contracts import Interpretation
    c = controller
    c.clients.vision = scene("coke", 1.0)
    await observe(c)
    assert c.state()["allowed_items"] == ["coke", "coffee"]
    await say(c, "Coffee, please")
    assert c.card.item == "coffee"
    old = confirmation(c)

    async def ignoring_menu(current, utterance):
        assert current.allowed_items == ["coke", "coffee"]
        return Interpretation(intent="refill", item="water"), "fixture"

    c.clients.language = ignoring_menu
    await say(c, "Water please")
    assert c.phase == "not_understood" and c.card.item == "coffee"
    assert "choose coke, coffee" in c.message
    with pytest.raises(ApiError):
        await c.confirm(old)
    assert not c.hardware.commands


async def test_an_understood_request_starts_without_a_press():
    # Understanding the request is the approval, so no card should sit waiting.
    settings = Settings(
        qwen_backend="fixture",
        mock_step_seconds=0.01,
        response_timeout=1,
        require_confirmation=False,
    )
    c = Controller(settings, ModelClients(settings))
    try:
        await observe(c)
        assert c.phase == "offered"
        await say(c, "a little water please")
        assert c.phase == "done", c.state()
        assert c.state()["requires_confirmation"] is False
    finally:
        await c.close()


async def test_the_confirm_step_can_be_put_back():
    settings = Settings(
        qwen_backend="fixture",
        mock_step_seconds=0.01,
        response_timeout=1,
        require_confirmation=True,
    )
    c = Controller(settings, ModelClients(settings))
    try:
        await observe(c)
        await say(c, "a little water please")
        assert c.phase == "card"
        assert c.state()["requires_confirmation"] is True
    finally:
        await c.close()
