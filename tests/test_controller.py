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
    settings = Settings(qwen_backend="fixture", mock_step_seconds=0.01, response_timeout=1)
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
    return ConfirmInput(**c.card.model_dump(exclude={"item", "portion"}))


async def test_full_refill_and_edit(controller):
    c = controller
    await observe(c)
    assert c.phase == "offered" and not c.hardware.commands
    await say(c, "A little water, please")
    old = confirmation(c)
    assert c.card.portion == "small" and not c.hardware.commands
    await say(c, "Coffee instead, regular please")
    assert c.card.item == "coffee" and c.card.portion == "regular"
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
    [("No thanks", "declined"), ("Cancel that", "cancelled"), ("Maybe tea", "clarify")],
)
async def test_non_refill(controller, text, phase):
    await observe(controller)
    await say(controller, text)
    assert controller.phase == phase and not controller.hardware.commands


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
