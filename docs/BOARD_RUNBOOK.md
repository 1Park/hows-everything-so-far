# 보드 수령 후 연결·검증

Gemma 상주 서비스는 `QWEN_MODEL_BACKEND=board`, `QWEN_MODEL=gemma4`로 설정한다. 시작 시 Gemma4 로드 완료를 기다리며 생성 API를 먼저 호출할 필요가 없다. `/ready`의 `runner.resident=true`, `runner.llm=gemma4`를 확인한다. 모델이 없거나 실행기가 실패하면 시작에 실패하고 자식 프로세스를 정리한다. DINOv2의 현재 보드 bundle은 CLI 방식이므로 모델 상주와 별개다.

2026-10-17 실제 보드 검증: LLM 서버 재시작 후 생성 API 호출 없이 GET `/ready`만 확인해 약 5.586초에 ready=true, resident=true, llm=gemma4를 확인했다. 보드 서버의 기존 `executorch` 선택은 `BoardLLMBackend`에 연결돼 있으며, 이 워크스페이스에서는 기존 Qwen CLI 구현과 구분하기 위해 `board`를 사용한다. 보드 측 증거는 `logs/gemma-preload-verification.json`에 저장했다. 변경 범위는 상주 백엔드와 서버 시작·종료 처리이며, 제품 프롬프트·요청 계약의 별도 배포와는 구분한다.

DINOv2 현황: 실제 Vision bundle(`dinov2-qnn-v3`)의 DINO와 detector 모두 runner=cli다. Vision 서버/파이프라인은 유지되지만 추론마다 `qnn_executor_runner`를 실행하므로 모델 상주는 아니다. Gemma4 상주 시 가용 RAM 약 11.1GiB, DINO 파일 44MiB를 확인했으나 이는 DINO 실행 메모리 실측이나 두 QNN/HTP 컨텍스트 동시 상주 성공의 증거는 아니다. 동시 상주를 적용하기 전 두 모델을 로드한 상태에서 순차 추론의 성공·지연·메모리·반복 안정성을 검증한다.

실제 Gemma 서비스가 설치된 보드에서는 `bash scripts/board_llm.sh use gemma4`로 모델 선택을 고정한다. `auto`는 메모리 상황에 따라 Gemma3를 고를 수 있으므로 사용하지 않는다. Gemma3 모델 파일·업로드·실행 코드는 보존하며 기본 평가도 Gemma4만 사용한다. 현재 보드는 selection=gemma4와 `/ready`의 `runner.llm=gemma4`를 확인했다. 이 워크스페이스의 요청 계약 변경(`portion` 제거, `not_understood`)은 별도 앱 배포가 필요하다.

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
export VISION_MODEL_PATH='<actual DINO bundle .pte>'
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

Qwen ExecuTorch는 common/backends.py의 ExecuTorchBackend가 native qnn_llama_runner를 호출한다. services/qwen/README.md에 따라 실제 runner·model·tokenizer 경로와 QWEN_SEQ_LEN을 설정한다. 토크나이저·chat template·생성 옵션·취소/timeout·원본 output을 실기 검증한다. 현재 요청별 CLI 실행이므로 모델 상주를 주장하지 않는다. .env.board는 QWEN_MODEL_BACKEND=executorch라서 필수 설정 전 ready503을 반환하며 Mac/fixture로 자동 전환하지 않는다. 실제 보드 bundle의 공개 model ID는 확인 후 설정한다.

## 3. 카메라와 태블릿

선택 `python -m pip install -e '.[camera]'`, CAMERA_SOURCE에 확인한 USB index/파일 경로. Controller만 장치를 열고 stream과 분석으로 분기한다. 다른 camera process는 종료한다. 보드 마이크·태블릿 UI/스피커는 [음성 runbook](TABLET_DEMO.md)을 따른다. 태블릿 안내 재생 완료→보드 녹음→STT→Qwen→카드 순서이며, 이 경로는 태블릿 마이크 권한/HTTPS가 필요 없다.

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

실제 DINO/STT 입력·출력·bbox 좌표계, 영어 음료 요청 결과, CPU/QNN 별도 export 및 delegation/profile, 메모리/지연/두 모델 동시 자원, USB disconnect, Bridge/watchdog/cancel, 태블릿 출력 청취·안내 완료 신호·보드 마이크 녹음. 모두 **현장 미검증**이며 로컬 fixture/UI 테스트와 구분해 기록한다.


<!-- Native runner implementation status -->
### Native ExecuTorch runner status

Qwen's former placeholder now invokes the QC native runner via
`common/backends.py:ExecuTorchBackend`; configure actual runner/model/tokenizer
paths and `QWEN_SEQ_LEN` per [Qwen setup](../services/qwen/README.md).
DINOv2 prepared-tensor execution is available as `common.executorch.DinoRunner`
and `scripts/dino_smoke.py`; the Vision owner still supplies all image
preprocessing/detection and output conversion. See [Vision setup](../services/vision/README.md).
Earlier references to an unconnected adapter describe missing runtime assets or
remaining board validation, not a missing subprocess implementation.
This is per-request model loading, not a persistent runtime. Tests use a process
double; actual board model loading, template compatibility and NPU execution remain
unverified. Qwen's native limit is total sequence length, not exact completion tokens.
