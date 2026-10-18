# TTS 서비스 (보드)

`server.py:create_app`, 기본 127.0.0.1:8003. `POST /v1/speak {"text": "..."}` → `audio/wav` (22050 Hz mono), `GET /ready`, `/health`.

- 엔진: Piper voice `en_US-hfc_female-medium` (데모용 말투: 12% 빠르게, 억양 변화 크게, 피크 -1 dBFS).
- **앞부분은 CPU, 디코더는 NPU.** voice `.onnx`를 앞부분(발음·길이 예측·flow, 입력마다 출력 길이가 바뀜)과
  디코더(HiFi-GAN, Conv/ConvTranspose만)로 나눠 디코더만 ExecuTorch QNN fp16으로 돌린다.
  디코더는 latent 길이를 고정해야 해서 `<voice>.dec_f<N>.pte`를 길이별로 두고, 문장마다 맞는 가장 작은 것을 골라
  0으로 채운 뒤 잘라낸다. 맞는 길이가 없거나 `.pte`가 없으면 그 문장은 CPU 디코더로 만든다.
- NPU 디코더는 Vision과 같은 상주 worker(`TTS_WORKER_BIN`, 비우면 `VISION_WORKER_BIN`)로 모델을 올려둔다.
- 디코더 export: `ml/export/export_piper_decoder.py` (보드 ExecuTorch venv).

| 설정 | 의미 |
|---|---|
| `TTS_VOICE_PATH` | Piper voice `.onnx` (같은 폴더에 `.onnx.json`). front/dec 그래프는 처음 실행 때 옆에 만든다 |
| `TTS_DECODER_DIR` | `<voice>.dec_f<N>.pte`가 있는 폴더. 비우면 CPU 디코더만 |
| `TTS_WORKER_BIN` | 상주 QNN worker. 비우면 `VISION_WORKER_BIN` |
| `TTS_BACKEND` | Controller 쪽 설정. `http`면 상태마다 말할 문장(`speech`)을 이 서비스로 읽게 한다 |

Controller는 상태마다 말할 문장(`app/speech.py`)을 `StateSnapshot.speech`로 내보내고, 태블릿은
`GET /api/speech/{session_id}/{sequence}`로 그 음성을 받아 재생한다. TTS가 꺼져 있거나 실패하면 태블릿은
기존 고정 WAV(`app/ui/audio/`)를 틀거나 조용히 넘어간다. 같은 문장은 Controller가 캐시한다.

## 보드 실측 (2026-10-18)

데모 문장 7개(음성 1.7~3.9초), 서비스 HTTP 왕복 중앙값. 같은 문장은 Controller 캐시로 두 번째부터 즉시.

| 디코더 | HTTP 왕복 | 디코더 | 앞부분(CPU) |
|---|---:|---:|---:|
| CPU | 495 ms | 274 ms (길이 따라 200~310) | 215 ms |
| **NPU fp16, 384 프레임 고정** | **373 ms** | **185 ms (길이 무관)** | 175 ms |

- NPU 출력은 CPU 대비 cosine 0.9999 (SNR 33 dB). 시작할 때 모델 로드 약 2.5초.
- 128·256 프레임 export는 QNN "VTCM Allocation" 단계에서 멈춰서(15분+) 384 하나만 쓴다. 한 줄(150~335 프레임)을
  통째로 디코더 1번으로 만들고, 384를 넘는 긴 줄만 문장별로 나눈다.

## 실행

```sh
.venv/bin/pip install piper-tts==1.8.0 onnxruntime==1.31.0 onnx==1.23.2   # 보드 1회
setsid nohup .venv/bin/python -m uvicorn services.tts.server:create_app --factory \
  --host 127.0.0.1 --port 8003 > ~/model_output/logs/tts-8003.log 2>&1 < /dev/null &
```
