import importlib.util
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
    assert set(counts) == {"detected/low", "detected/high", "requested"}
    assert all(r["mock"] is True for r in rows)
    assert {r["item"] for r in rows} <= {"coke", "coffee", "beer", "water", "cocktail"}
    assert [r["ts"] for r in rows] == sorted(r["ts"] for r in rows)


def test_times_are_bar_hours():
    for r in mock.generate():
        local = datetime.fromisoformat(r["ts"]).astimezone(LOCAL)
        # Requests trail a detection by up to 45 s, so allow them just past 23:00.
        assert 16 <= local.hour < 23 or (r["event"] == "requested" and local.hour == 23)


def test_each_request_follows_a_low_cup_by_about_30_seconds():
    rows = mock.generate()
    lows = {(r["session"], r["object_id"]): r for r in rows if r.get("level") == "low"}
    requested = [r for r in rows if r["event"] == "requested"]
    assert len({r["session"] for r in requested}) == len(requested)
    for r in requested:
        low = lows[(r["session"], r["object_id"])]
        delay = datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(low["ts"])
        assert 20 <= delay.total_seconds() <= 45
        assert r["transcript"]


def test_levels_match_fill_ratio_and_one_low_per_scene():
    rows = [r for r in mock.generate() if r["event"] == "detected"]
    for r in rows:
        assert (r["fill_ratio"] <= 0.3) == (r["level"] == "low")
    lows = Counter(r["session"] for r in rows if r["level"] == "low")
    assert set(lows.values()) == {1}
