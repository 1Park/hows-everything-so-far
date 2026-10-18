# TTS service (board)

`server.py:create_app`, default 127.0.0.1:8003. `POST /v1/speak {"text": "..."}` → `audio/wav` (22050 Hz mono), `GET /ready`, `/health`.

- Engine: Piper voice `en_US-hfc_female-medium` (demo speaking style: 12% faster, larger pitch variation, -1 dBFS peak).
- **Front end on CPU, decoder on NPU.** The voice `.onnx` is split into the front end (phonemes, duration prediction, flow; output length changes per input) and
  the decoder (HiFi-GAN, Conv/ConvTranspose only), and only the decoder runs on ExecuTorch QNN fp16.
  The decoder needs a fixed latent length, so there is one `<voice>.dec_f<N>.pte` per length; for each sentence the smallest one that fits is chosen,
  zero-padded, and then trimmed. If no length fits or the `.pte` is missing, that sentence is generated with the CPU decoder.
- The NPU decoder keeps its model loaded in the same resident worker as Vision (`TTS_WORKER_BIN`; if empty, `VISION_WORKER_BIN`).
- Decoder export: `ml/export/export_piper_decoder.py` (board ExecuTorch venv).

| Setting | Meaning |
|---|---|
| `TTS_VOICE_PATH` | Piper voice `.onnx` (with `.onnx.json` in the same folder). The front/dec graphs are created next to it on the first run |
| `TTS_DECODER_DIR` | Folder containing `<voice>.dec_f<N>.pte`. If empty, CPU decoder only |
| `TTS_WORKER_BIN` | Resident QNN worker. If empty, `VISION_WORKER_BIN` |
| `TTS_BACKEND` | Controller-side setting. With `http`, the sentence to say for each state (`speech`) is read out through this service |

The Controller exports the sentence to say for each state (`app/speech.py`) as `StateSnapshot.speech`, and the tablet
fetches that audio from `GET /api/speech/{session_id}/{sequence}` and plays it. With `TTS_BACKEND=http`,
a failure does not fall back to the previous WAV; an error is shown, and the prompt-finished ACK and auto recording are not started.
The Enable sound welcome voice and Replay voice use the same TTS. The welcome and test sentences are
generated with `GET /api/speech-preview`. The Controller caches identical sentences.
The old fixed WAVs are used only when `TTS_BACKEND=disabled` is set explicitly in development.
With the http setting, TTS readiness is part of the Controller `/ready` success condition.

## Board measurements (2026-10-18)

7 demo sentences (1.7–3.9 s of audio), median service HTTP round trip. Repeated sentences are instant from the second time on thanks to the Controller cache.

| Decoder | HTTP round trip | Decoder | Front end (CPU) |
|---|---:|---:|---:|
| CPU | 495 ms | 274 ms (200–310 depending on length) | 215 ms |
| **NPU fp16, fixed 384 frames** | **373 ms** | **185 ms (independent of length)** | 175 ms |

- NPU output vs CPU: cosine 0.9999 (SNR 33 dB). Model load at startup takes about 2.5 s.
- The 128- and 256-frame exports hang at the QNN "VTCM Allocation" step (15+ min), so only 384 is used. A whole line (150–335 frames) is
  generated in a single decoder pass, and only long lines over 384 are split by sentence.

## Running

```sh
.venv/bin/pip install piper-tts==1.8.0 onnxruntime==1.31.0 onnx==1.23.2   # once on the board
setsid nohup .venv/bin/python -m uvicorn services.tts.server:create_app --factory \
  --host 127.0.0.1 --port 8003 > ~/model_output/logs/tts-8003.log 2>&1 < /dev/null &
```
