# Board deployment and operation

Code and settings changes follow **local edit → verify → commit/push → deploy to board**. Do not edit the board repo directly. Run experiments and builds in a separate path such as `/tmp`, and restore any temporary source changes. Models, the SDK, and the external Whisper server are managed separately from the app deployment.

## Runtime layout

| Port | Service | Run by |
| --- | --- | --- |
| 8080 | Controller/UI | `dev.py --mode direct --with-stt` |
| 8000 (localhost) | Qwen API → resident Gemma4 | separate Uvicorn |
| 8001 (localhost) | Vision → resident YOLO + DINOv2 | separate Uvicorn |
| 8002 (localhost) | STT API → whisper.cpp HTTP | the supervisor above |
| 8003 (localhost) | TTS → Piper, decoder resident on NPU | separate Uvicorn |
| 8178 | external whisper.cpp | managed outside the repo |

In this layout, also running `integration`/`board` mode or `start-board.sh` causes model server port conflicts. Use those tools only when they manage all four services from scratch.

## Preparation

From the repo root, set up `.venv` and the dependencies (`pip install -c requirements.lock -e '.[dev,camera]'`). Install the provided SDK, QNN libraries, and model bundles separately. Do not use the [past installation record](board-installation-20261017.md) as the reference for reinstall commands.

- Gemma: `QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4` in `.env.board`. Pin the default selection with `bash scripts/board_llm.sh use gemma4`. Paths and process lifetime follow the [LLM service](../services/qwen/README.md).
- Vision: the default internal backend in `.env.board` is fixture. The real model requires explicitly setting the external factory, bundle, and worker as shown below. A bundle is a directory and needs `bundle.json`, `.pte`, and a head.
- TTS: `TTS_*` in `.env.board`. Put the voice and the NPU decoder (`<voice>.dec_f384.pte`) in `models/board/tts/` and install the `.[tts]` dependencies into `.venv`. With `TTS_BACKEND=http`, missing TTS shows `/ready=503` and a playback error, and it does not fall back to the old WAVs. [TTS service](../services/tts/README.md).
- STT: the Whisper adapter in `.env.board` connects to `127.0.0.1:8178`. Prepare the external server first.
- Check the camera and ALSA devices in `.env.board` against the on-site device list. Run `python scripts/diagnose.py` for read-only diagnostics.

Build the Vision worker in a separate path without modifying the provided SDK:

```sh
python scripts/build_vision_worker.py --sdk "$HOME/git/executorch" \
  --build-dir "$HOME/git/executorch/build-x86" --output-dir /tmp/vision-worker-build
```

Place the generated binary at `models/board/bin/qnn_vision_worker` for deployment. This file and the model weights are not in Git. [Vision settings in detail](../services/vision/README.md).

## Start

### Running independently of USB disconnects (recommended)

Processes started from an ADB shell may be killed when USB is disconnected. Run the Controller/STT and each model server
by installing `scripts/systemd/*.service` into user systemd. These units assume the current board path
`~/project/hows-everything-so-far`; for a different path, edit the units too.

```sh
loginctl enable-linger arduino
mkdir -p ~/.config/systemd/user ~/.config/refill-assist
# Record the existing real Vision environment in ~/.config/refill-assist/vision.env:
# VISION_MODEL_BACKEND=external
# VISION_ADAPTER=services.vision.backend:create_backend
# VISION_MODEL_PATH=<absolute path of the real bundle>
# VISION_WORKER_BIN=<absolute path of the real worker>
# LD_LIBRARY_PATH=<current SDK library path>
# ADSP_LIBRARY_PATH=<current DSP library path>
# Record the TTS worker/library environment in ~/.config/refill-assist/tts.env the same way.
# Also check ~/whisper.cpp and the model paths in the Whisper units against the install location.
cp scripts/systemd/refill-*.service ~/.config/systemd/user/
systemctl --user daemon-reload
# After checking for and stopping the existing Controller/STT supervisor and Vision listener:
systemctl --user enable --now refill-llm refill-vision refill-tts refill-whisper-tiny refill-whisper-base refill-controller
systemctl --user status refill-controller refill-llm refill-vision refill-tts refill-whisper-tiny refill-whisper-base
```

After deploying, restart the app with `systemctl --user restart refill-controller`.
To switch the Vision bundle, edit `VISION_MODEL_PATH` in `~/.config/refill-assist/vision.env` (keep a backup of the old line) and run `systemctl --user restart refill-vision`; a process started by hand is not restarted on reboot.
If the Vision code changed, also run `systemctl --user restart refill-vision`.
Stop with `systemctl --user stop refill-controller refill-vision`; do not run systemd and a separate supervisor
at the same time. Logs are in the existing `logs/controller.log`, `logs/stt.log`, and
`journalctl --user -u refill-controller -u refill-vision`.
The Controller unit links each model unit with Wants/After. With linger and the six units above enabled,
everything starts automatically on reboot without a login or laptop USB. `prepare_board_start.py` checks occupied ports and running
supervisors, then cleans up only the lock/ready/stop files of exited processes. Before the models are ready,
`/ready` may return 503. arduino-router is a separate system service; check that it is enabled.
Verify: without USB, check that `/ready` reports the real models, TTS, microphone, and Bridge as ready, and that the tablet can connect.

Below is an example layout with the provided SDK at `~/git/executorch` and the bundle at `dinov2-qnn-v6` (LDA head with augmentation; includes orange juice and the snack bag at the demo spot; `-v5e` is the previous logistic-regression head). Check the actual paths and start **only services that have no existing listener**. Set the selected env explicitly for each process.

```sh
mkdir -p logs tmp
export REFILL_ENV_FILE="$PWD/.env.board"
export LD_LIBRARY_PATH="$HOME/git/executorch/build-x86/backends/qualcomm:/usr/lib"
export ADSP_LIBRARY_PATH=/usr/lib

VISION_MODEL_BACKEND=external VISION_ADAPTER=services.vision.backend:create_backend \
VISION_MODEL_PATH=models/board/vision/dinov2-qnn-v6 \
VISION_WORKER_BIN="$PWD/models/board/bin/qnn_vision_worker" \
nohup .venv/bin/python -m uvicorn services.vision.server:create_app --factory \
  --host 127.0.0.1 --port 8001 > logs/vision-8001.log 2>&1 < /dev/null &
echo $! > tmp/vision-8001.pid

nohup .venv/bin/python -m uvicorn services.qwen.server:create_app --factory \
  --host 127.0.0.1 --port 8000 > logs/qwen-8000.log 2>&1 < /dev/null &
echo $! > tmp/qwen-8000.pid

VISION_WORKER_BIN="$PWD/models/board/bin/qnn_vision_worker" \
nohup .venv/bin/python -m uvicorn services.tts.server:create_app --factory \
  --host 127.0.0.1 --port 8003 > logs/tts-8003.log 2>&1 < /dev/null &
echo $! > tmp/tts-8003.pid

.venv/bin/python scripts/dev.py --mode direct --with-stt --env-file .env.board
```

Gemma4 and Vision load their models at server start, so `/ready` becomes ready without any generate/invoke call. Check Gemma's `runner.resident/llm/pid` and Vision's `runners`. The Controller `/ready` also shows the state of dependent services.

```sh
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8001/ready
curl -fsS http://127.0.0.1:8003/ready
curl -fsS http://127.0.0.1:8080/ready
```

The tablet connects to `http://<board-address>:8080/`. [Board microphone/speaker flow](TABLET_DEMO.md). Before the demo, check real images, utterances, card edits, Confirm, and Cancel. Keep fixture results distinct from real model output.

## Shutdown and recovery

Stop the Controller/STT with Ctrl+C or `dev.py --mode direct --stop` with the same env. A separate Vision/Gemma does not stop automatically. Check the PID files above against `/proc/<pid>/cmdline`, then send TERM to that Uvicorn PID. Do not use broad kills that target all Python processes or runners. Leave the external Whisper, router, MCU, and Tailscale running.

If the Vision worker fails, `/ready=false`; restart the Vision service. A Gemma worker error can be recovered by reloading on the next generation request. For readiness failures, check the logs, files, and library paths; do not work around them with fixtures.

Hardware defaults to mock. `bridge` communicates through `/var/run/arduino-router.sock` in [`RouterClient`](../app/hardware/router.py). Only arduino-router owns the UART. MCU build, LED polarity, sensor, and watchdog verification follow the [firmware guide](../firmware/README.md).
