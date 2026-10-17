"""Execute an organizer-specified runner command once; no guessed CLI or input preprocessing."""

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument(
        "command", nargs=argparse.REMAINDER, help="Use -- then the exact runner and its flags"
    )
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("Supply the actual runner command after --")
    started = time.monotonic()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=args.timeout)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code = 124
        stdout = error.stdout or ""
        stderr = "Runner timed out"
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
    except OSError as error:
        code, stdout, stderr = 127, "", str(error)
    report = {
        "command": command,
        "returncode": code,
        "elapsed_seconds": time.monotonic() - started,
        "stdout": stdout,
        "stderr": stderr,
        "scope": "One runner invocation only. Does not prove product accuracy, persistent loading, or NPU delegation.",
    }
    folder = Path("logs")
    folder.mkdir(exist_ok=True)
    path = folder / (datetime.now(timezone.utc).strftime("runner-%Y%m%dT%H%M%S%fZ.json"))
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(path)
    raise SystemExit(code)
