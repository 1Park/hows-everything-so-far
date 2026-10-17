"""Append-only JSON Lines record of Controller phase changes, for the history dashboard.

One line per emitted state: when it happened, which session, the phase, and the facts known at
that moment (target cup and fill level, transcript, request card, error). A session's lines
together describe one customer interaction. Recording is best effort: a write failure is logged
once and never interrupts the demo. EVENT_LOG_PATH empty disables recording.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from common.api import log


class EventLog:
    def __init__(self, path: str | Path | None):
        from common.config import ROOT

        if not path:
            self.path = None
        else:
            path = Path(path)
            self.path = path if path.is_absolute() else ROOT / path
        self.failed = False

    @staticmethod
    def row(state: dict, now: datetime | None = None) -> dict:
        now = now or datetime.now(timezone.utc)
        row = {
            "ts": now.isoformat(timespec="milliseconds"),
            "instance": state["instance_id"],
            "session": state["session_id"],
            "sequence": state["sequence"],
            "phase": state["phase"],
        }
        scene = state.get("scene")
        if scene:
            row["scene_id"] = scene["scene_id"]
            row["vision_source"] = scene["source"]
            row["objects"] = len(scene["objects"])
        target = state.get("target")
        if target:
            row["object_id"] = target["object_id"]
            row["item"] = target["item"]
            row["fill_ratio"] = target["fill_ratio"]
            row["confidence"] = target["confidence"]
        if state.get("transcript"):
            row["transcript"] = state["transcript"]
            row["stt_source"] = state.get("stt_source")
        card = state.get("card")
        if card:
            row["request_id"] = card["request_id"]
            row["req_item"] = card["item"]
            row["portion"] = card["portion"]
            row["revision"] = card["revision"]
        if state.get("qwen_source"):
            row["qwen_source"] = state["qwen_source"]
        error = state.get("last_error")
        if error and state["phase"] == "error":
            row["error_code"] = error["code"]
        return row

    def record(self, state: dict) -> None:
        if self.path is None:
            return
        try:
            line = json.dumps(self.row(state), ensure_ascii=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")
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
