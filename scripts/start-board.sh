#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p logs tmp
if [[ -e tmp/board.lock ]]; then
  echo 'Board supervisor already running or stale lock exists. Inspect tmp/board.lock and process before retrying.' >&2
  exit 1
fi
PYTHON="${REFILL_PYTHON:-.venv/bin/python}"
[[ -x "$PYTHON" ]] || { echo 'Create the board Python virtualenv first.' >&2; exit 1; }
# arduino-router and MCU firmware are independently installed/managed.
nohup "$PYTHON" scripts/dev.py --mode board --env-file .env.board >> logs/supervisor.log 2>&1 &
pid=$!
for ((attempt=0;attempt<100;attempt++)); do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo 'Startup failed. See logs/supervisor.log and per-service logs.' >&2
    exit 1
  fi
  if [[ -e tmp/board.ready ]] && [[ "$(cat tmp/board.ready)" == "$pid" ]]; then
    echo "Supervisor PID $pid. Check Controller /ready before demo. Stop with bash scripts/stop-board.sh"
    exit 0
  fi
  sleep 0.5
done
kill -TERM "$pid" 2>/dev/null || true
echo 'Startup timed out; supervisor was asked to stop.' >&2
exit 1
