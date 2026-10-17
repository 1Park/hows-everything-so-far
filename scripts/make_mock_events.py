"""Generate a week of mock dashboard history in the same JSON Lines shape as logs/events.jsonl.

Scenario: an evening bar, 16:00-23:00 local time, 2026-10-11 (Sun) .. 2026-10-17 (Sat).
- 100 ``detected`` lines: 50 low, 50 high. Each scene (session) has one low cup, or only high cups.
- 40 ``requested`` lines, each ~30 s (20-45 s) after a low detection in the same session.
- Busier on Friday/Saturday and from 19:00 to 22:00; coffee early, beer/cocktail late.
- Every line carries ``"mock": true`` so it can be merged with real records and still be told apart.

Deterministic (fixed seed). Usage:
    python scripts/make_mock_events.py [--out fixtures/mock_events.jsonl] [--seed 1029]
"""

import argparse
import json
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")
DAYS = [date(2026, 10, 11) + timedelta(days=i) for i in range(7)]
DAY_WEIGHT = {6: 1.0, 0: 0.8, 1: 0.8, 2: 0.9, 3: 1.0, 4: 1.5, 5: 1.7}  # weekday(): Mon=0, Sun=6
HOUR_WEIGHT = {16: 1.0, 17: 1.5, 18: 2.5, 19: 3.0, 20: 3.5, 21: 3.5, 22: 2.5}
DRINKS = ["coke", "coffee", "beer", "water", "cocktail"]
# Drink mix by hour: coffee early, beer/cocktail late, coke and water all evening.
DRINK_WEIGHT = {
    16: [3, 4, 1, 3, 0.5],
    17: [3, 3, 2, 3, 1],
    18: [3, 2, 3, 3, 2],
    19: [2, 1, 4, 2, 3],
    20: [2, 0.5, 5, 2, 4],
    21: [2, 0.5, 5, 2, 5],
    22: [2, 0.5, 4, 3, 5],
}
LOW_RANGE, HIGH_RANGE = (0.02, 0.30), (0.35, 0.95)
N_LOW, N_HIGH, N_REQUESTED = 50, 50, 40

PHRASES = {
    ("same", "regular"): [
        "Another {d}, please.",
        "Yes, one more {d}.",
        "Can I get another {d}?",
        "Same again, please.",
        "Yes please, a refill.",
    ],
    ("same", "small"): [
        "Just a little more {d}, please.",
        "A small {d}, please.",
        "Half a glass of {d}.",
    ],
    ("switch", "regular"): [
        "Can I get a {d} instead?",
        "Let me switch to a {d}.",
        "Actually, a {d} please.",
    ],
    ("switch", "small"): [
        "Just a small {d} instead.",
        "A little {d} this time, please.",
    ],
}


def pick_time(rng: random.Random) -> datetime:
    day = rng.choices(DAYS, weights=[DAY_WEIGHT[d.weekday()] for d in DAYS])[0]
    hour = rng.choices(list(HOUR_WEIGHT), weights=list(HOUR_WEIGHT.values()))[0]
    local = datetime(day.year, day.month, day.day, hour, tzinfo=LOCAL)
    return local + timedelta(seconds=rng.randrange(3600), milliseconds=rng.randrange(1000))


def drink_at(rng: random.Random, when: datetime) -> str:
    return rng.choices(DRINKS, weights=DRINK_WEIGHT[when.hour])[0]


def iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="milliseconds")


def cup(rng, when, session, index, level):
    lo, hi = LOW_RANGE if level == "low" else HIGH_RANGE
    return {
        "ts": iso(when),
        "event": "detected",
        "session": session,
        "object_id": f"cup-{index}",
        "item": drink_at(rng, when),
        "level": level,
        "fill_ratio": round(rng.uniform(lo, hi), 4),
        "confidence": round(rng.uniform(0.72, 0.97), 4),
        "mock": True,
    }


def request(rng, low_row, when):
    drink = low_row["item"]
    mode = "same" if rng.random() < 0.75 else "switch"
    if mode == "switch":
        drink = rng.choice([d for d in DRINKS if d != low_row["item"]])
    portion = "regular" if rng.random() < 0.65 else "small"
    return {
        "ts": iso(when),
        "event": "requested",
        "session": low_row["session"],
        "object_id": low_row["object_id"],
        "item": drink,
        "portion": portion,
        "revision": 1,
        "transcript": rng.choice(PHRASES[(mode, portion)]).format(d=drink),
        "mock": True,
    }


def generate(seed: int = 1029) -> list[dict]:
    rng = random.Random(seed)
    uid = lambda: str(uuid.UUID(int=rng.getrandbits(128), version=4))  # noqa: E731
    rows, low_rows, highs_left = [], [], N_HIGH

    # 50 scenes with exactly one low cup (the refill target) plus 0-2 high cups.
    for _ in range(N_LOW):
        when, session = pick_time(rng), uid()
        extra = min(highs_left, rng.choice([0, 0, 1, 1, 2]))
        highs_left -= extra
        cups = ["low"] + ["high"] * extra
        rng.shuffle(cups)
        for index, level in enumerate(cups):
            row = cup(rng, when, session, index, level)
            rows.append(row)
            if level == "low":
                low_rows.append((row, when))

    # Remaining high cups in scenes where nothing needs a refill.
    while highs_left:
        when, session = pick_time(rng), uid()
        n = min(highs_left, rng.choice([1, 2, 3]))
        highs_left -= n
        rows += [cup(rng, when, session, i, "high") for i in range(n)]

    # 40 of the 50 offers get a customer request ~30 s later.
    for row, when in rng.sample(low_rows, N_REQUESTED):
        delay = timedelta(seconds=rng.uniform(20, 45))
        rows.append(request(rng, row, when + delay))

    return sorted(rows, key=lambda r: (r["ts"], r["event"] != "detected", r["object_id"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="fixtures/mock_events.jsonl")
    parser.add_argument("--seed", type=int, default=1029)
    args = parser.parse_args()
    out = Path(args.out)
    out = out if out.is_absolute() else ROOT / out
    rows = generate(args.seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    counts = {}
    for r in rows:
        key = r["event"] if r["event"] == "requested" else f"detected/{r['level']}"
        counts[key] = counts.get(key, 0) + 1
    print(out, counts)


if __name__ == "__main__":
    main()
