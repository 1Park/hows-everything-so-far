# whisper.cpp speech recognition server (board)

Speech-to-text for the board microphone runs in **whisper.cpp**, a separate C++ server outside this repo.
The app never loads a Whisper model itself: the STT API forwards each recording to this server over HTTP.
This page records how the server was built on the board, how it is run, how it was measured, and how to
check it. Adapter settings live in [services/stt](../services/stt/README.md); the model choice is recorded
in [STT evaluation](stt_evaluation/README.md).

## Where it fits

```text
Brio 101 mic ──arecord──► Controller (app/audio.py, 6 s WAV)
                              │ POST /v1/transcribe
                              ▼
                     STT API :8002 (services/stt, WhisperHTTP adapter)
                              │ POST /inference (multipart WAV)
                              ▼
            whisper-server :8179  ggml-tiny.en   ← used by the app (STT_WHISPER_URL)
            whisper-server :8178  ggml-base.en   ← kept for comparison and as the fallback
                              │ {"text": "..."}
                              ▼
            services/stt/normalize.py (drink-name fixes) → Controller → Gemma4
```

- Runs on the board **CPU** (aarch64). It does not use the NPU.
- Lives in `~/whisper.cpp` on the board, outside the repo and outside the app deployment.
- Listens on `0.0.0.0` so a laptop on the same network can also send test audio.
- The microphone is opened only by the Controller. whisper-server only receives files.

## Install (once per board)

Ubuntu 24.04 on the board has no compiler by default.

```sh
sudo apt update
sudo apt install -y build-essential cmake ffmpeg alsa-utils

cd ~
git clone https://github.com/ggml-org/whisper.cpp
cd ~/whisper.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"
ls build/bin | grep whisper          # whisper-cli, whisper-server, ...

./models/download-ggml-model.sh tiny.en
./models/download-ggml-model.sh base.en
```

Model files are `~/whisper.cpp/models/ggml-tiny.en.bin` (~75 MB) and `ggml-base.en.bin` (~148 MB).
Record the whisper.cpp commit (`git -C ~/whisper.cpp log --oneline -1`) when reinstalling, so a later
build can be compared against the same code.

Quick check with the bundled 11-second sample:

```sh
cd ~/whisper.cpp
time ./build/bin/whisper-cli -m models/ggml-tiny.en.bin -f samples/jfk.wav -t 4
```

## Run

### systemd (recommended)

Both servers have user units in [`scripts/systemd/`](../scripts/systemd/), installed together with the
other services as described in [BOARD_RUNBOOK](BOARD_RUNBOOK.md#start):

| Unit | Model | Port | Used by the app |
| --- | --- | --- | --- |
| `refill-whisper-tiny` | `ggml-tiny.en` | 8179 | yes (`STT_WHISPER_URL` in `.env.board`) |
| `refill-whisper-base` | `ggml-base.en` | 8178 | no, comparison and fallback |

Each unit runs `whisper-server` from `~/whisper.cpp` with `-t 4`, so the two models compare at the same
thread count, and restarts on failure.

```sh
systemctl --user status refill-whisper-tiny refill-whisper-base
systemctl --user restart refill-whisper-tiny
journalctl --user -u refill-whisper-tiny -f
```

### By hand (development)

Stop the matching unit first, or the port is already taken.

```sh
cd ~/whisper.cpp
setsid nohup ./build/bin/whisper-server \
  -m models/ggml-tiny.en.bin --host 0.0.0.0 --port 8179 -t 4 \
  --prompt "Drinks: water, coke, coffee, orange juice. Just a little coffee, please. No thanks." \
  > ~/whisper.cpp/whisper-8179.log 2>&1 < /dev/null &
```

`--prompt` is a decoding hint, not an instruction. Listing the menu words makes Whisper prefer them
(for example "coke" over "coca").

## Check

```sh
curl -s localhost:8179/health; echo                       # {"status":"ok"}
curl -s localhost:8179/inference \
  -F file=@$HOME/whisper.cpp/samples/jfk.wav -F response_format=json; echo

# Real microphone, same device as the Controller (.env.board AUDIO_DEVICE)
arecord -D plughw:CARD=B101,DEV=0 -f S16_LE -r 16000 -c 1 -d 4 /tmp/mic.wav
curl -s localhost:8179/inference -F file=@/tmp/mic.wav -F response_format=json; echo

# Through the app's STT API (adds normalize and the no_speech check)
curl -s localhost:8002/v1/transcribe -F "file=@/tmp/mic.wav;type=audio/wav"; echo
```

`/ui/stt.html` on the Controller records a phrase and transcribes it with every configured model side by
side; results are kept on the board (see [STT evaluation](stt_evaluation/README.md)).

## Choosing the model

`STT_WHISPER_URL` in `.env.board` decides which server the app uses. Switching model means changing that
URL and restarting the Controller/STT (`systemctl --user restart refill-controller`); the whisper
servers keep running.

| Measurement (board CPU) | Result |
| --- | --- |
| `jfk.wav` 11 s, `whisper-cli`, base.en vs small.en | 5.0 s vs 17.7 s; small.en dropped as too slow |
| `jfk.wav` 11 s, whisper-server base.en, warm | ~5.2 s per request (model load is not the cost) |
| 20 real recordings, base.en vs tiny.en ([raw](stt_evaluation/base-vs-tiny-20261018.json)) | exact match 75% vs 70%, mean WER 10.4% vs 15.0%, median 6.9 s vs 3.0 s |

tiny.en was chosen: 17 of 20 transcripts were identical, the drink name survived 19 of 20, and the
operator reviews the transcript before sending, while a four-second wait on every request does not recover.
Avoid "Just a half portion of water" in demos: both models heard it as "I still have a portion of water".

Whisper pads every input to a 30-second window, so a short answer costs about as much as a long one.
Not yet tried on the board: a smaller audio context (`-ac`), quantized models (`q8_0`), and other thread
counts.

## Transcript clean-up

The STT API runs every transcript through [`normalize.py`](../services/stt/normalize.py) before it reaches the
Controller: menu aliases and near-miss spellings (for example "coca", "cola", "Coca-Cola" → coke), Whisper
tags such as `[BLANK_AUDIO]` removed. An empty result becomes the `no_speech` error ("Please retry or type your
request"); there is no fixture fallback.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `couldn't bind to server socket` | The port is taken (often the unit is already running). `sudo ss -ltnp \| grep -E ':(8178\|8179) '` |
| STT API returns `stt_unavailable` / connection refused | whisper-server is down or `STT_WHISPER_URL` points at the wrong port. Check `/health` |
| `no_speech` on every request | The recording is silent: wrong ALSA device or capture volume. `arecord -l`, `alsamixer -c <card>` |
| `arecord: Device or resource busy` | Another process holds the mic (PipeWire or a test script). Use the `plughw:` device or stop the other recorder |
| `cmake: command not found` / `pip` blocked | Install `build-essential cmake`; on Ubuntu 24.04 use a venv for Python tools |
| Slow requests while demoing | Vision, Gemma4 and TTS share the board CPU. Compare `/inference` timing with the other services idle |

## Known gaps

- The `--prompt` in both systemd units still lists an older menu ("juice, cola, water, sprite, …"). Update it to
  the current menu (water, coke, coffee, orange juice) and restart the units.
- Recording is a fixed 6 seconds (`AUDIO_SECONDS`); there is no end-of-speech detection yet.
