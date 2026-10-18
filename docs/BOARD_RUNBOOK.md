# 보드 배포·실행

코드·설정 변경은 **로컬 수정 → 검증 → commit/push → 보드 배포** 순서로 한다. 보드 레포를 직접 수정하지 않는다. 실험·빌드는 `/tmp` 등 별도 경로에서 수행하고 임시 소스 변경은 복원한다. 모델·SDK·외부 Whisper 서버는 앱 배포와 별도 관리한다.

## 실행 구조

| 포트 | 서비스 | 실행 주체 |
| --- | --- | --- |
| 8080 | Controller/UI | `dev.py --mode direct --with-stt` |
| 8000 (localhost) | Qwen API → 상주 Gemma4 | 별도 Uvicorn |
| 8001 (localhost) | Vision → 상주 YOLO + DINOv2 | 별도 Uvicorn |
| 8002 (localhost) | STT API → whisper.cpp HTTP | 위 supervisor |
| 8003 (localhost) | TTS → Piper, 디코더 상주 NPU | 별도 Uvicorn |
| 8178 | 외부 whisper.cpp | 레포 밖에서 관리 |

이 배치에서 `integration`/`board` 모드나 `start-board.sh`를 추가 실행하면 모델 서버 포트가 충돌한다. 이 도구들은 네 서비스를 모두 새로 관리할 때만 사용한다.

## 준비

레포 루트에서 `.venv`와 의존성(`pip install -c requirements.lock -e '.[dev,camera]'`)을 준비한다. 제공 SDK·QNN 라이브러리·모델 bundle은 별도 설치한다. [과거 설치 기록](board-installation-20261017.md)은 재설치 명령의 기준으로 사용하지 않는다.

- Gemma: `.env.board`의 `QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4`. `bash scripts/board_llm.sh use gemma4`로 기본 선택을 고정한다. 경로·실행 수명은 [LLM 서비스](../services/qwen/README.md)를 따른다.
- Vision: `.env.board` 기본 내부 backend는 fixture다. 실제 모델은 아래처럼 external factory·bundle·worker를 명시해야 한다. bundle은 디렉터리이며 `bundle.json`, `.pte`, head가 필요하다.
- TTS: `.env.board`의 `TTS_*`. voice와 NPU 디코더(`<voice>.dec_f384.pte`)를 `models/board/tts/`에 두고 `.venv`에 `.[tts]` 의존성을 설치한다. 없으면 태블릿은 고정 WAV를 튼다. [TTS 서비스](../services/tts/README.md).
- STT: `.env.board`의 Whisper adapter가 `127.0.0.1:8178`에 연결한다. 외부 서버를 먼저 준비한다.
- 카메라·ALSA 장치는 `.env.board`와 현장 장치 목록을 대조한다. `python scripts/diagnose.py`로 읽기 전용 진단을 수행한다.

Vision worker는 제공 SDK를 수정하지 않고 별도 경로에서 빌드한다:

```sh
python scripts/build_vision_worker.py --sdk "$HOME/git/executorch" \
  --build-dir "$HOME/git/executorch/build-x86" --output-dir /tmp/vision-worker-build
```

생성 binary를 배포할 `models/board/bin/qnn_vision_worker`에 배치한다. 이 파일과 모델 가중치는 Git에 포함되지 않는다. [Vision 세부 설정](../services/vision/README.md).

## 시작

아래는 제공 SDK가 `~/git/executorch`, bundle이 `dinov2-qnn-v5e`(오렌지주스, 데모 자리 과자봉지 포함)에 있는 배치 예다. 실제 경로를 확인하고 **기존 listener가 없는 서비스만** 시작한다. 선택 env를 각 프로세스에 명시한다.

```sh
mkdir -p logs tmp
export REFILL_ENV_FILE="$PWD/.env.board"
export LD_LIBRARY_PATH="$HOME/git/executorch/build-x86/backends/qualcomm:/usr/lib"
export ADSP_LIBRARY_PATH=/usr/lib

VISION_MODEL_BACKEND=external VISION_ADAPTER=services.vision.backend:create_backend \
VISION_MODEL_PATH=models/board/vision/dinov2-qnn-v5e \
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

Gemma4와 Vision은 서버 시작 시 모델을 로드하므로 생성/invoke 없이 `/ready`가 준비된다. Gemma의 `runner.resident/llm/pid`, Vision의 `runners`를 확인한다. Controller `/ready`는 종속 서비스 상태도 보여준다.

```sh
curl -fsS http://127.0.0.1:8000/ready
curl -fsS http://127.0.0.1:8001/ready
curl -fsS http://127.0.0.1:8003/ready
curl -fsS http://127.0.0.1:8080/ready
```

태블릿은 `http://<board-address>:8080/`으로 접속한다. [보드 마이크·스피커 흐름](TABLET_DEMO.md). 데모 전 실제 이미지·발화·카드 수정·Confirm·Cancel을 확인한다. fixture 결과와 실제 모델 출력을 구분한다.

## 종료·복구

Controller/STT는 Ctrl+C 또는 같은 env의 `dev.py --mode direct --stop`으로 종료한다. 별도 Vision/Gemma는 자동 종료되지 않는다. 위 PID 파일과 `/proc/<pid>/cmdline`을 대조한 뒤 해당 Uvicorn PID에 TERM을 보낸다. 전체 Python·runner를 대상으로 한 광범위 종료는 사용하지 않는다. 외부 Whisper·router·MCU·Tailscale은 유지한다.

Vision worker가 실패하면 `/ready=false`이며 Vision 서비스를 재시작한다. Gemma worker 오류는 다음 생성 요청에서 재로드할 수 있다. 준비 실패는 로그·파일·라이브러리 경로를 확인하며 fixture로 우회하지 않는다.

Hardware 기본은 mock이다. `bridge`는 [`RouterClient`](../app/hardware/router.py)의 `/var/run/arduino-router.sock`을 통해 통신한다. UART는 arduino-router만 소유한다. MCU 빌드·LED 극성·센서·watchdog 검증은 [firmware 안내](../firmware/README.md)를 따른다.
