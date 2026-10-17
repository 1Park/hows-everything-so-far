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
for ((attempt=0;attempt<60;attempt++)); do
  [[ -e tmp/board.lock ]] || { echo 'Managed app processes stopped.'; exit 0; }
  sleep 0.5
done
echo 'Shutdown still pending. Inspect supervisor and child processes; arduino-router was not touched.' >&2
exit 1
