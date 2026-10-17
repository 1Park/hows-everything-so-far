# 보드 수령 후 연결·검증

현재 앱은 보드 없이 개발/시연 가능하다. 아래 보드 관련 코드는 **준비 단계이며 실기 검증 완료가 아니다**. Ubuntu에 직접 실행, ROS·앱 Docker 없음. 학습·QNN export Docker는 ml/ 관심사.

## 1. 환경 확인

대회 [IoT guide](../qc-executorch-guide/IoT/README.md)와 [artifact inventory](../qc-executorch-guide/IoT/artifacts/README.md)의 실제 checkout/runtime/bundle을 확인한다. QCS8275(Qualcomm Dragonwing IQ8) Linux와 STM32H5F5 MCU를 구분한다. 지원 Python 버전/제공 ExecuTorch commit/QAIRT SDK/모델·tokenizer·shared library·DSP library 경로를 기록한다. 대회 runtime을 pip 최신판으로 임의 교체하지 않는다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python scripts/diagnose.py
```

실제 배포 안내에서 확인한 절대경로만 shell 환경에 지정한다. 예시의 꺾쇠 placeholder는 정상 설정이 아니다.

```sh
export QNN_EXECUTOR_RUNNER='<actual executable path>'
export QNN_LLAMA_RUNNER='<actual executable path>'
export VISION_MODEL_PATH='<Vision bundle directory containing bundle.json>'
export VISION_RUNNER_BIN='<qnn_executor_runner path, only for cli-runner bundles>'
export QWEN_MODEL_PATH='<actual Qwen .pte>'
export QWEN_TOKENIZER_PATH='<actual tokenizer path>'
export LD_LIBRARY_PATH='<actual host library paths>'
export ADSP_LIBRARY_PATH='<actual DSP library paths>'
python scripts/diagnose.py
# 해당 runner --help와 대회 제공 단일 입력 명령을 확인한 뒤 정확한 flags를 전달:
python scripts/runner_smoke.py -- /absolute/path/to/runner <actual flags>
```

smoke는 한 입력·출력/exit code/시간만 logs에 저장한다. 모델 로딩/상주 실행/정확도/NPU delegation 검증을 대체하지 않는다. 모델 미제공 시 add smoke를 제품 DINO/Qwen 성공으로 보고하지 않는다. 실행 timeout은 configurable이며 runner CLI/input 규격을 임의 생성하지 않는다.

## 2. 모델 연결

Vision/STT 담당자는 [API·async 계약](CONTRACTS.md)을 구현한다. factory/HTTP를 연결하고 실제 source=external/readiness를 확인한다. DINO output이 embedding인지 classification logits인지 bundle을 보고 결정하며 담당자 전처리를 서비스가 대체하지 않는다.

Vision(DINOv2): `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=services.vision.backend:create_backend`, `VISION_MODEL_PATH=models/board/vision/<bundle>`(bundle 디렉터리, `.pte` 파일 아님). bundle은 `ml/export/make_bundle.py`로 만들고, head는 **보드에서 돌릴 `.pte`의 특징으로** `ml/training/make_head.py`로 학습한다(fp32 head를 양자화 모델에 쓰면 크게 떨어짐). bundle 없음/로드 실패는 ready503. 세부는 [services/vision](../services/vision/README.md)·[ml](../ml/README.md)·[평가 기록](vision_evaluation/README.md).

Qwen ExecuTorch는 common/backends.py의 ExecuTorchBackend 경계에 실제 runtime을 연결한다. 토크나이저·chat template·생성 옵션·취소/timeout·상주 실행·원본 output을 확인한다. 일회성 CLI를 감싼 HTTP 상주만으로 모델 상주를 주장하지 않는다. .env.board는 QWEN_MODEL_BACKEND=executorch라서 연결 전 ready503을 반환하며 Mac/fixture로 자동 전환하지 않는다. 실제 보드 bundle의 공개 model ID는 확인 후 설정한다.

## 3. 카메라와 태블릿

선택 `python -m pip install -e '.[camera]'`, CAMERA_SOURCE에 확인한 USB index/파일 경로. Controller만 장치를 열고 stream과 분석으로 분기한다. 다른 camera process는 종료한다. 태블릿 브라우저의 마이크/스피커는 [HTTPS runbook](TABLET_DEMO.md)을 따른다. 서버 오디오 장치 접근은 필요 없다.

## 4. MCU·Bridge

호스트 arduino-router와 MCU firmware는 앱 supervisor 밖에서 관리한다. `systemctl status/cat arduino-router`로 설치 상태 확인, Bridge UART 직접 열기 금지. 공식 arduino.app_utils 설치/초기화는 board image 문서 기준. MCU sketch를 실제 core로 컴파일하고 LED pin/polarity 확인. provide_safe/짧은 handler/nested RPC 금지/nonblocking sequence/cancel/watchdog를 점검한다.

HARDWARE_BACKEND=bridge는 이 확인 뒤 명시 선택한다. 버튼/센서는 확보 하드웨어를 정한 후 연결한다. draft의 false 입력값은 simulator이며 실센서가 아니다. phase polling→watchdog, 중복 command_id 거부, timeout 후 늦은 RPC, 단절/복구를 검증한다. 실제 주행/집기는 여전히 범위 밖이다.

## 5. 배포·종료

```sh
bash scripts/start-board.sh
# 각 서비스 health와 ready 확인. 기본 Controller127.0.0.1:8080.
curl http://127.0.0.1:8080/ready
bash scripts/stop-board.sh
```

프로세스별 logs, tmp/board.lock. startup 실패 시 시작한 자식들만 정리한다. stale lock이면 PID/cmdline와 열린 포트를 확인한 후 수동 제거한다. 종료는 matching supervisor만 대상으로 하고 router/firmware/Tailscale은 건드리지 않는다. 다시 시작해 동일 demo를 재현한다.

## 현장 승인 전 확인

실제 DINO/STT 입력·출력·bbox 좌표계, 영어 음료 요청 결과, CPU/QNN 별도 export 및 delegation/profile, 메모리/지연/두 모델 동시 자원, USB disconnect, Bridge/watchdog/cancel, 태블릿 HTTPS·마이크 권한·출력 청취. 모두 **현장 미검증**이며 로컬 fixture/UI 테스트와 구분해 기록한다.
