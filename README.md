# Refill Assist

Observes cup type and remaining level on an Arduino VENTUNO Q and interprets the customer's English request. When the customer taps **Confirm** on the confirmation card, a mock loading and return sequence starts. The menu is water/coke/coffee; real driving and grasping are not implemented.

The code is the source of truth for behavior and settings. The docs explain how to run things and where the code lives; evaluation records are the results at the time they were run.

## Deploy and run on Arduino VENTUNO Q

**For the real-board demonstration, start with the [board deployment and operation runbook](docs/BOARD_RUNBOOK.md).** It covers SDK/model installation, real Vision configuration, Gemma4, Whisper STT, TTS, systemd startup, and recovery.

1. Prepare the board dependencies, model bundles, camera, microphone, and Arduino Bridge using the runbook.
2. Configure the real Vision service with `VISION_MODEL_BACKEND=external`, its adapter, bundle, and worker paths. In the recommended systemd setup, these are recorded in `~/.config/refill-assist/vision.env`. **Selecting `.env.board` alone does not enable real Vision.**
3. Install and start the systemd services described in the runbook. For an already provisioned board:

   ```sh
   systemctl --user start refill-llm refill-vision refill-tts refill-whisper-tiny refill-whisper-base refill-controller
   curl -fsS http://127.0.0.1:8080/ready
   ```

4. Open `http://<board-address>:8080/` on the tablet.

The current board layout runs model servers separately; Controller/STT uses `dev.py --mode direct --with-stt --env-file .env.board` through systemd. Do not additionally run `--mode board` or `start-board.sh` alongside these services: they would compete for the same ports.

Before presenting, inspect the contents of `/ready`, not just its HTTP status: Vision and STT must report `source: external`, video must not be `fixture-image`, and hardware must be `bridge` and ready. Check the LLM service at `http://127.0.0.1:8000/ready` for the real Gemma4 resident runner, and verify that changing the cups and spoken request changes the results. Fixtures can also report ready. Model failures are not automatically replaced with fixtures.

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

## Tech Stack

### Architecture

<img width="1728" height="864" alt="image" src="https://github.com/user-attachments/assets/32cdc81e-978e-4d86-93f5-7a907f5c4e8b" />

Details: https://github.com/1Park/hows-everything-so-far/blob/main/docs/ARCHITECTURE.md


## Docs and validation

- [Structure and execution paths](docs/ARCHITECTURE.md), [API boundaries](docs/CONTRACTS.md)
- [Board deployment and operation](docs/BOARD_RUNBOOK.md), [Tablet and voice flow](docs/TABLET_DEMO.md), [whisper.cpp server](docs/WHISPER_SERVER.md), [Model files](models/README.md)
- [Validation commands and scope](docs/VALIDATION.md)
- Past measurements: [Gemma](docs/gemma_evaluation/README.md), [Qwen](docs/qwen_evaluation/README.md), [Vision](docs/vision_evaluation/README.md), [STT](docs/stt_evaluation/README.md)

## Developer reference

- [Local development without a board and supervisor modes](docs/LOCAL_DEVELOPMENT.md) — simulated inputs for UI/flow testing.
