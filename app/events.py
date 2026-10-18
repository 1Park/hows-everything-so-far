"""Append-only JSON Lines history for the dashboard: what was detected and what was requested.

Only two kinds of line are written:

- ``detected``: one line per cup each time scene analysis finishes (phase offered or skipped),
  with the drink, its fill level (``low`` / ``high`` against LOW_FILL_THRESHOLD) and the time.
- ``requested``: one line each time a customer request becomes a refill card,
  with the requested drink, the customer's words when spoken, and the time.

Recording is best effort: a write failure is logged once and never interrupts the demo.
EVENT_LOG_PATH empty disables recording.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from common.api import log


class EventLog:
    def __init__(self, path: str | Path | None, low_fill_threshold: float = 0.3):
        from common.config import ROOT

        if not path:
            self.path = None
        else:
            path = Path(path)
            self.path = path if path.is_absolute() else ROOT / path
        self.low_fill_threshold = low_fill_threshold
        self.failed = False
        self.last_request = None

    def level(self, fill_ratio: float | None) -> str:
        if fill_ratio is None:
            return "unknown"
        return "low" if fill_ratio <= self.low_fill_threshold else "high"

    def rows(self, state: dict, now: datetime | None = None) -> list[dict]:
        """History lines for one emitted state; most phases produce none."""
        ts = (now or datetime.now(timezone.utc)).isoformat(timespec="milliseconds")
        phase, session = state["phase"], state["session_id"]
        if phase in ("offered", "skipped") and state.get("scene"):
            return [
                {
                    "ts": ts,
                    "event": "detected",
                    "session": session,
                    "object_id": o["object_id"],
                    "item": o["item"],
                    "level": self.level(o["fill_ratio"]),
                    "fill_ratio": o["fill_ratio"],
                    "confidence": o["confidence"],
                }
                for o in state["scene"]["objects"]
            ]
        if phase in ("card", "loading") and state.get("card"):
            card = state["card"]
            identity = (session, card.get("request_id", card["object_id"]), card["revision"])
            if identity == self.last_request:
                return []
            self.last_request = identity
            row = {
                "ts": ts,
                "event": "requested",
                "session": session,
                "object_id": card["object_id"],
                "item": card["item"],
                "revision": card["revision"],
            }
            if state.get("transcript"):
                row["transcript"] = state["transcript"]
            selected = card.get("selections") or [{"object_id":card["object_id"], "item":card["item"]}]
            return [{**row, **entry} for entry in selected]
        return []

    def record(self, state: dict) -> None:
        if self.path is None:
            return
        try:
            rows = self.rows(state)
            if not rows:
                return
            text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(text)
        except (OSError, TypeError, ValueError, KeyError) as error:
            if not self.failed:
                self.failed = True
                log.warning({"event": "event_log_failed", "error": type(error).__name__})

    def read(self, limit: int = 5000) -> list[dict]:
        """Most recent `limit` rows, oldest first. Malformed lines are skipped."""
        if self.path is None or not self.path.is_file():
            return []
        rows = []
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
        return rows[-limit:]
