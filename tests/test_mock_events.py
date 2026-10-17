import importlib.util
import json
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from common.config import ROOT

spec = importlib.util.spec_from_file_location("mock", ROOT / "scripts/make_mock_events.py")
mock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mock)
LOCAL = ZoneInfo("America/Los_Angeles")


def test_counts_and_shape():
    rows = mock.generate()
    counts = Counter(
        r["event"] if r["event"] == "requested" else f"detected/{r['level']}" for r in rows
    )
    assert counts == {"detected/low": 50, "detected/high": 50, "requested": 40}
    assert all(r["mock"] is True for r in rows)
    assert {r["item"] for r in rows} <= {"coke", "coffee", "beer", "water", "cocktail"}
    assert [r["ts"] for r in rows] == sorted(r["ts"] for r in rows)


def test_times_are_bar_hours_in_the_week():
    for r in mock.generate():
        local = datetime.fromisoformat(r["ts"]).astimezone(LOCAL)
        assert "2026-10-11" <= local.date().isoformat() <= "2026-10-17"
        # Requests trail a detection by up to 45 s, so allow them just past 23:00.
        assert 16 <= local.hour < 23 or (r["event"] == "requested" and local.hour == 23)


def test_each_request_follows_a_low_cup_by_about_30_seconds():
    rows = mock.generate()
    lows = {(r["session"], r["object_id"]): r for r in rows if r.get("level") == "low"}
    requested = [r for r in rows if r["event"] == "requested"]
    assert len({r["session"] for r in requested}) == 40
    for r in requested:
        low = lows[(r["session"], r["object_id"])]
        delay = datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(low["ts"])
        assert 20 <= delay.total_seconds() <= 45
        assert r["portion"] in ("small", "regular") and r["transcript"]


def test_levels_match_fill_ratio_and_one_low_per_scene():
    rows = [r for r in mock.generate() if r["event"] == "detected"]
    for r in rows:
        assert (r["fill_ratio"] <= 0.3) == (r["level"] == "low")
    lows = Counter(r["session"] for r in rows if r["level"] == "low")
    assert set(lows.values()) == {1}


def test_deterministic_and_checked_in_file_is_current():
    assert mock.generate() == mock.generate()
    checked_in = ROOT / "fixtures/mock_events.jsonl"
    lines = [json.loads(x) for x in checked_in.read_text(encoding="utf-8").splitlines()]
    assert lines == mock.generate()
