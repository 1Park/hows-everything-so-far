import asyncio
import json
from datetime import datetime

import pytest

from app.clients import ModelClients
from app.controller import Controller
from app.events import EventLog
from common.config import ROOT, Settings
from common.contracts import ConfirmInput, UtteranceInput


async def settled(c):
    for _ in range(300):
        if c.phase not in ("observing", "interpreting", "loading", "returning"):
            return
        await asyncio.sleep(0.005)
    raise AssertionError(c.state())


def make(path):
    settings = Settings(
        qwen_backend="fixture",
        mock_step_seconds=0.01,
        response_timeout=1,
        event_log_path=str(path) if path else "",
    )
    return Controller(settings, ModelClients(settings))


async def run_refill(c):
    await c.start((ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg", "normal")
    await settled(c)
    await c.utterance(
        UtteranceInput(
            scene_id=c.scene.scene_id,
            object_id=c.target.object_id,
            utterance="A little water, please",
        )
    )
    await settled(c)
    await c.confirm(ConfirmInput(**c.card.model_dump(exclude={"item", "portion"})))
    await settled(c)


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


async def test_refill_session_is_recorded(tmp_path):
    path = tmp_path / "events.jsonl"
    c = make(path)
    try:
        await run_refill(c)
    finally:
        await c.close()
    rows = lines(path)
    phases = [r["phase"] for r in rows]
    for phase in ("observing", "offered", "interpreting", "card", "loading", "done"):
        assert phase in phases
    assert phases.index("offered") < phases.index("card") < phases.index("done")
    assert len({r["session"] for r in rows if r["phase"] != "idle"}) == 1
    assert [r["sequence"] for r in rows] == sorted(r["sequence"] for r in rows)
    for r in rows:
        datetime.fromisoformat(r["ts"])

    offered = next(r for r in rows if r["phase"] == "offered")
    assert offered["item"] in ("water", "coke", "coffee", "unknown")
    assert 0 <= offered["fill_ratio"] <= 1 and "confidence" in offered
    card = next(r for r in rows if r["phase"] == "card")
    assert card["req_item"] == "water" and card["portion"] == "small"
    assert card["request_id"] and card["revision"] == 1


async def test_disabled_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = make(None)
    try:
        await run_refill(c)
    finally:
        await c.close()
    assert c.event_log.path is None
    assert not list(tmp_path.rglob("*.jsonl"))


async def test_unwritable_path_never_breaks_the_demo(tmp_path):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("file, not directory")
    c = make(blocker / "events.jsonl")
    try:
        await run_refill(c)
        assert c.phase == "done" and c.event_log.failed
    finally:
        await c.close()


def test_row_and_read_round_trip(tmp_path):
    state = {
        "instance_id": "i",
        "session_id": "s",
        "sequence": 7,
        "phase": "error",
        "scene": None,
        "target": None,
        "card": None,
        "transcript": "No thanks",
        "stt_source": "external",
        "qwen_source": "executorch",
        "last_error": {"code": "model_unavailable", "message": "x", "retryable": True},
    }
    log = EventLog(tmp_path / "e.jsonl")
    log.record(state)
    (tmp_path / "e.jsonl").open("a").write("not json\n")
    log.record({**state, "sequence": 8, "phase": "idle"})
    rows = log.read()
    assert [r["sequence"] for r in rows] == [7, 8]
    assert rows[0]["error_code"] == "model_unavailable" and "error_code" not in rows[1]
    assert rows[0]["transcript"] == "No thanks" and rows[0]["qwen_source"] == "executorch"
    assert log.read(limit=1)[0]["sequence"] == 8


def test_relative_path_resolves_against_repo_root():
    assert EventLog("logs/events.jsonl").path == ROOT / "logs/events.jsonl"


@pytest.mark.parametrize("value", ["", None])
def test_empty_path_disables(value):
    assert EventLog(value).path is None
