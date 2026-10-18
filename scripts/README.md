# Running and diagnostics

Run from the repo root/venv. [Full setup](../README.md).

| Tool | Role |
| --- | --- |
| dev.py | direct/fixture/offline/proxy/integration/board modes, port and lock checks, child cleanup on startup failure, logs |
| dev.py --stop | Returns after waiting until the matching mode/port supervisor has finished stopping; use the same options for --mode board |
| start-board.sh / stop-board.sh | Linux native background supervisor, PID and duplicate checks, waits for failure/stop |
| diagnose.py | OS/arch/Python, explicit runner/model/library, read-only camera/Bridge/router diagnostics |
| runner_smoke.py -- <actual runner and flags> | Runs a single input and records time/output/error logs; does not guess the CLI |
| smoke.py | Verifies refill/edit/stale/duplicate/completion/STT/skip through the real Controller HTTP |
| browser_auto_capture.cjs | On the local app, checks the 3-second auto start, mode switching, snapshot/bbox and mobile screen (fixture validation) |
| browser_restart_audio.cjs | On an offline + AUDIO_INPUT=fixture + TTS_BACKEND=http server, verifies audio recovery after restart and the playback-finished ACK. Only the WAV responses are mocked in the browser |
| evaluate_qwen.py --proxy | Real local proxy→Mac drink evaluation, temperature 0, new timestamped results |
| evaluate_gemma.py | Board HTTP Gemma evaluation: 20 original + 20 synthetic STT-distorted, same product prompt, records per-case input/output/time in new JSON and Markdown |
| build_vision_worker.py | Builds the resident DINO/YOLO native worker in a separate output path without modifying the organizers' SDK |
| benchmark_vision_residency.py | With the same image and bundle, compares CLI/resident invoke time, initial load and output equivalence; writes new JSON/Markdown |
| browser_check.cjs | Real Chromium recording/fixture STT/fixed audio/card/confirm/cancel/responsive/reconnect |
| browser_board_voice.cjs | Auto recognition → tablet prompt playback finished → board fixture recording → STT → card, without using the browser microphone |

logs/{service}.log and tmp/lock are excluded from Git. Ctrl+C or --stop. This supervisor does not start or stop the external Mac server, the host arduino-router, MCU firmware or Tailscale Serve. board --stop only targets the same managed supervisor as the shell stop tools.

fixture pins only Vision/STT/Hardware, and Qwen uses the real HTTP API at QWEN_BASE_URL (Mac by default). offline also pins Qwen to a fixture and runs without any external model connection. These two modes start only the Controller/UI. Real API failures are not automatically switched to fixtures.

`--mode direct --with-stt` manages only the Controller and our STT API; Qwen stays on the configured remote API. An existing whisper-server is kept as a separate process and is not stopped. For board microphone settings, see the [tablet demo](../docs/TABLET_DEMO.md).
