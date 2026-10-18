"""Multi-cup product decisions using an explicit fixture LLM, not model accuracy."""
import pytest

from app.clients import ModelClients
from app.controller import Controller
from common.api import ApiError
from common.config import Settings
from common.contracts import Interpretation, RefillSelection, VisionResult
from tests.test_controller import observe, say, confirmation, settled


@pytest.mark.parametrize(("utterance", "items"), [
    ("Yes please", ["water", "coke"]),
    ("Water please", ["water"]),
    ("Just coffee please", ["coffee"]),
    ("Water and coke please", ["water", "coke"]),
    ("No thanks", []),
])
async def test_multi_cup_reply_selects_all_subset_or_none(utterance, items):
    settings = Settings(qwen_backend="fixture", require_confirmation=True, mock_step_seconds=.01)
    clients = ModelClients(settings)

    async def vision(data, mime, scene_id, scenario):
        return VisionResult(scene_id=scene_id, source="fixture", objects=[
            dict(object_id="a", item="water", bbox=dict(x1=.1, y1=.1, x2=.3, y2=.7), fill_ratio=.1, confidence=.95),
            dict(object_id="b", item="coke", bbox=dict(x1=.6, y1=.1, x2=.8, y2=.7), fill_ratio=.15, confidence=.95),
        ])

    clients.vision = vision
    c = Controller(settings, clients)
    try:
        await observe(c)
        assert "water and coke" in c.state()["speech"] and len(c.state()["targets"]) == 2
        await say(c, utterance)
        if not items:
            assert c.phase == "declined" and c.card is None and not c.hardware.commands
        else:
            assert [s.item for s in c.card.selections] == items
            if items == ["coffee"]:
                assert c.card.selections[0].object_id == "b"
            await c.confirm(confirmation(c))
            await settled(c)
            assert c.phase == "done" and len(c.hardware.commands) == 1  # One batch simulation.
    finally:
        await c.close()


async def test_two_identical_cups_keep_both_ids_and_reject_unknown_model_target():
    settings = Settings(qwen_backend="fixture", require_confirmation=True)
    clients = ModelClients(settings)
    async def vision(data, mime, scene_id, scenario):
        return VisionResult(scene_id=scene_id, source="fixture", objects=[
            dict(object_id=identity, item="water", bbox=dict(x1=x, y1=.1, x2=x+.2, y2=.7), fill_ratio=.1, confidence=.95)
            for identity, x in (("a", .1), ("b", .6))
        ])
    clients.vision = vision
    c = Controller(settings, clients)
    try:
        await observe(c)
        assert "2 glasses of water" in c.state()["speech"]
        await say(c, "Yes please")
        assert [s.object_id for s in c.card.selections] == ["a", "b"]
        old = confirmation(c)
        async def invalid(current, utterance):
            return Interpretation(intent="refill", selections=[RefillSelection(object_id="missing", item="water")]), "fixture"
        c.clients.language = invalid
        await say(c, "Yes please")
        assert c.phase == "not_understood"
        with pytest.raises(ApiError):
            await c.confirm(old)
        assert not c.hardware.commands
    finally:
        await c.close()
