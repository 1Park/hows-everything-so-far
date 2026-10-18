# Local development without a board

This is a UI and flow simulation for development, not the real-board demonstration. Vision/STT return predetermined fixture results; offline mode also simulates the LLM. For real model inference and hardware, follow the [board deployment runbook](BOARD_RUNBOOK.md).

## Setup and modes

Python 3.11–3.13. From the repo root:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -c requirements.lock -e '.[dev]'
Copy-Item .env.example .env
.venv/Scripts/python.exe scripts/dev.py --mode offline
```

On macOS/Linux, use `.venv/bin/python` and `cp .env.example .env`.
`http://127.0.0.1:8080` → Start demo → text request → Send → Confirm refill.
Stop with Ctrl+C, or with `python scripts/dev.py --stop` using the same settings.

| Mode | Services started | Model connection |
| --- | --- | --- |
| `direct` (default) | Controller/UI | Configured API/fixture. Default is Vision/STT fixture + Mac Qwen HTTP |
| `fixture` | Controller/UI | Vision/STT fixture, Hardware mock, LLM over real HTTP |
| `offline` | Controller/UI | Everything including the LLM is a fixture, Hardware mock |
| `proxy` | Controller + Qwen API | The Qwen server calls the configured backend |
| `integration`, `board` | Controller + Qwen + Vision + STT | Uses the backends from the selected env |

`--mode direct --with-stt` also manages the STT API. If model servers are already running separately on the board, follow the [board runbook](BOARD_RUNBOOK.md). Model failures are not automatically replaced with fixtures.

Settings precedence is explicit overrides in code > process environment variables > selected dotenv (`--env-file`/`REFILL_ENV_FILE`, default `.env`) > [`Settings`](../common/config.py) defaults. `.env.board` alone does not select real Vision; bundle settings are also required.


