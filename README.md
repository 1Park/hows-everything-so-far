# Refill Assist

Observes cup type and remaining level on an Arduino VENTUNO Q and interprets the customer's English request. When the customer taps **Confirm** on the confirmation card, a mock loading and return sequence starts. The menu is water/coke/coffee; real driving and grasping are not implemented.

The code is the source of truth for behavior and settings. The docs explain how to run things and where the code lives; evaluation records are the results at the time they were run.

## Running locally

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

`--mode direct --with-stt` also manages the STT API. If model servers are already running separately on the board, follow the [board runbook](docs/BOARD_RUNBOOK.md). Model failures are not automatically replaced with fixtures.

Settings precedence is explicit overrides in code > process environment variables > selected dotenv (`--env-file`/`REFILL_ENV_FILE`, default `.env`) > [`Settings`](common/config.py) defaults. `.env.board` alone does not select real Vision; bundle settings are also required.

## Layout

| Code | Responsibility |
| --- | --- |
| [app/](app/README.md) | State machine, refill policy, prompts, single camera, board recording |
| [app/ui/](app/ui/README.md) | Tablet UI, fixed WAV prompts, confirmation, dashboard |
| [services/qwen/](services/qwen/README.md) | Board-resident Gemma4 / dev Mac HTTP generation API |
| [services/vision/](services/vision/README.md) | YOLO → DINOv2 → head, models resident on the board |
| [services/stt/](services/stt/README.md) | whisper.cpp HTTP connection, transcript normalization |
| [app/hardware/](app/hardware/README.md) | mock or arduino-router RPC |
| [common/](common/README.md) | Schemas, settings, errors, inference queue |
| [ml/](ml/README.md) | Training, evaluation, export; separate from the app runtime |
| [scripts/](scripts/README.md) | Supervisor, diagnostics, build and evaluation tools |

The Controller owns the camera and microphone; the browser owns the UI and speaker. For optional video/USB input, install `.[camera]` and set `CAMERA_SOURCE`. An empty value means the explicit sample image.
The board starts in Automatic by default and captures after a 3-second stability check. The dev `.env.example` uses Manual. [Auto capture](docs/AUTO_CAPTURE.md).

## Docs and validation

- [Structure and execution paths](docs/ARCHITECTURE.md), [API boundaries](docs/CONTRACTS.md)
- [Board deployment and operation](docs/BOARD_RUNBOOK.md), [Tablet and voice flow](docs/TABLET_DEMO.md), [Model files](models/README.md)
- [Validation commands and scope](docs/VALIDATION.md)
- Past measurements: [Gemma](docs/gemma_evaluation/README.md), [Qwen](docs/qwen_evaluation/README.md), [Vision](docs/vision_evaluation/README.md), [STT](docs/stt_evaluation/README.md)
