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


async def observe(c, scenario="normal"):
    await c.start((ROOT / "docs/assets/cups-example.jpg").read_bytes(), "image/jpeg", scenario)
    await settled(c)


async def run_refill(c):
    await observe(c)
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


async def test_only_detected_and_requested_are_recorded(tmp_path):
    path = tmp_path / "events.jsonl"
    c = make(path)
    try:
        await run_refill(c)
        cups = len(c.scene.objects)
    finally:
        await c.close()
    rows = lines(path)
    assert [r["event"] for r in rows] == ["detected"] * cups + ["requested"]
    for r in rows:
        datetime.fromisoformat(r["ts"])
    assert len({r["session"] for r in rows}) == 1

    detected = rows[:cups]
    assert all(r["level"] in ("low", "high", "unknown") for r in detected)
    assert any(r["level"] == "low" for r in detected)
    water = next(r for r in detected if r["object_id"] == "cup-water")
    assert water["item"] == "water" and water["level"] == "low" and water["fill_ratio"] == 0.15

    requested = rows[-1]
    assert requested["item"] == "water" and requested["portion"] == "small"
    assert requested["object_id"] == "cup-water" and requested["revision"] == 1


async def test_full_cups_are_recorded_as_high(tmp_path):
    path = tmp_path / "events.jsonl"
    c = make(path)
    try:
        await observe(c, "enough")
        assert c.phase == "skipped"
    finally:
        await c.close()
    rows = lines(path)
    assert rows and all(r["event"] == "detected" and r["level"] == "high" for r in rows)


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


def test_spoken_request_keeps_transcript_and_read_skips_bad_lines(tmp_path):
    state = {
        "session_id": "s",
        "phase": "card",
        "scene": None,
        "transcript": "Just a little coffee, please.",
        "card": {"object_id": "cup-a", "item": "coffee", "portion": "small", "revision": 2},
    }
    log = EventLog(tmp_path / "e.jsonl")
    log.record(state)
    with (tmp_path / "e.jsonl").open("a") as file:
        file.write("not json\n")
    log.record({**state, "phase": "loading"})  # other phases add nothing
    rows = log.read()
    assert len(rows) == 1
    assert rows[0]["transcript"] == "Just a little coffee, please."
    assert rows[0]["item"] == "coffee" and rows[0]["revision"] == 2


@pytest.mark.parametrize(
    ("fill", "level"),
    [(0.0, "low"), (0.3, "low"), (0.31, "high"), (1.0, "high"), (None, "unknown")],
)
def test_level_uses_threshold(fill, level):
    assert EventLog(None, low_fill_threshold=0.3).level(fill) == level


def test_relative_path_resolves_against_repo_root():
    assert EventLog("logs/events.jsonl").path == ROOT / "logs/events.jsonl"


@pytest.mark.parametrize("value", ["", None])
def test_empty_path_disables(value):
    assert EventLog(value).path is None
