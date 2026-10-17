#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -f tmp/board.lock ]] || { echo 'No managed board supervisor found.'; exit 0; }
pid=$(cat tmp/board.lock)
[[ "$pid" =~ ^[0-9]+$ ]] || { echo 'Invalid supervisor PID.' >&2; exit 1; }
if [[ ! -r "/proc/$pid/cmdline" ]] || ! tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'scripts/dev.py --mode board'; then
  echo 'PID is not our board supervisor. Inspect and remove the stale lock manually.' >&2
  exit 1
fi
kill -TERM "$pid"
# dev.py --stop waits for the lock to clear, escalates to the recorded PID if the
# supervisor ignores it, and only reports success once the ports are free again.
PYTHON="${REFILL_PYTHON:-.venv/bin/python}"
[[ -x "$PYTHON" ]] || { echo 'Create the board Python virtualenv first.' >&2; exit 1; }
if "$PYTHON" scripts/dev.py --stop --mode board --env-file .env.board; then
  echo 'Managed app processes stopped. arduino-router was not touched.'
  exit 0
fi
echo 'Shutdown still pending. Inspect supervisor and child processes; arduino-router was not touched.' >&2
exit 1
