# 보드 수령 후 연결·검증

Gemma 상주 서비스는 `QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4`로 설정한다. 시작 시 Gemma4 로드 완료를 기다리며 생성 API를 먼저 호출할 필요가 없다. `/ready`의 `runner.resident=true`, `runner.llm=gemma4`를 확인한다. 모델이 없거나 실행기가 실패하면 시작에 실패하고 자식 프로세스를 정리한다. DINOv2의 현재 보드 bundle은 CLI 방식이므로 모델 상주와 별개다.

2026-10-17 실제 보드 검증: LLM 서버 재시작 후 생성 API 호출 없이 GET `/ready`만 확인해 약 5.586초에 ready=true, resident=true, llm=gemma4를 확인했다. 보드 서버와 이 워크스페이스 모두 기존 `executorch` 선택을 `BoardLLMBackend`에 연결한다. 독립 Qwen CLI 어댑터는 `qwen_cli`로 선택한다. 보드 측 증거는 `logs/gemma-preload-verification.json`에 저장했다. 변경 범위는 상주 백엔드와 서버 시작·종료 처리이며, 제품 프롬프트·요청 계약의 별도 배포와는 구분한다.

DINOv2 현황: 실제 Vision bundle(`dinov2-qnn-v4c`)의 DINO와 detector 모두 runner=cli다. Vision 서버/파이프라인은 유지되지만 추론마다 `qnn_executor_runner`를 실행하므로 모델 상주는 아니다. Gemma4 상주 시 가용 RAM 약 11.1GiB, DINO 파일 44MiB를 확인했으나 이는 DINO 실행 메모리 실측이나 두 QNN/HTP 컨텍스트 동시 상주 성공의 증거는 아니다. 동시 상주를 적용하기 전 두 모델을 로드한 상태에서 순차 추론의 성공·지연·메모리·반복 안정성을 검증한다.

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

보드 LLM은 Qwen이 아니라 주최 측 **Gemma**다. `.env.board`의 `QWEN_MODEL_BACKEND=executorch`면 Qwen 서비스(127.0.0.1:8000)가 `services/qwen/board_llm.py`로 상주 `qnn_llm_runner_host`(NPU)를 사용한다. 서버 시작 시 생성 호출 없이 Gemma4를 로드하며 같은 모델은 재사용하고 다른 모델을 명시적으로 요청할 때만 교체한다. 요청 간 KV는 초기화하고 취소/timeout/오류 때 worker를 회수한다. Mac/fixture로 자동 전환하지 않는다. [상주 실행·전환·실측](RESIDENT_LLM.md), [서비스 안내](../services/qwen/README.md).

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

## 6. 현재 보드 포트 배치 (2026-10-17, QCVENTUNO002)

| 포트 | 서비스 | 실제 backend | 누가 띄우나 | 로그 |
|---|---|---|---|---|
| 0.0.0.0:8080 | Controller/UI | Vision·STT·Qwen HTTP 호출, Hardware mock | `scripts/dev.py --mode direct` | `logs/controller.log` |
| 127.0.0.1:8000 | Qwen 서비스 | **Gemma** (qnn_llm_runner_host, NPU, 서버 시작 시 preload 후 상주) | 단독 uvicorn (아래) | `~/model_output/logs/qwen-8000.log` |
| 127.0.0.1:8001 | Vision 서비스 | DINOv2 fp16 + YOLO11n 16a8w QNN (cli runner, NPU) | 단독 uvicorn (아래) | `~/model_output/logs/vision-8001.log` |
| 127.0.0.1:8002 | STT 서비스 | whisper.cpp HTTP adapter (`services.stt.whisper_http`) | `dev.py --with-stt` | `logs/stt.log` |
| 0.0.0.0:8178 | whisper-server | whisper.cpp `ggml-base.en` (레포 밖 `~/whisper.cpp`) | 팀원 수동 실행, 건드리지 않음 | — |

보드 시스템 포트(22 ssh, 53 DNS, 631 cups, 5683 arduino-cloud-connector, 8800 arduino-app-cli, Tailscale)는 앱과 무관하다.

- 연결 순서: Controller → Vision 8001 / Qwen 8000 / STT 8002 → whisper-server 8178. 주소는 `.env.board` 기본값(`*_BASE_URL`)과 같다
- **Vision과 Gemma는 `dev.py`가 관리하지 않는다.** `dev.py --stop`이나 Controller 재시작으로는 꺼지지 않고, 보드를 재부팅하면 아래 명령으로 다시 띄운다
- Controller는 `--mode direct`로 띄운다. `--mode fixture`는 Vision·STT를 강제로 fixture로 바꾸고, `--mode integration`/`board`는 8000·8001을 직접 띄우려다 포트 충돌로 시작하지 않는다
- 모델이 둘 다 NPU를 쓰지만 동시 실행 확인함(Gemma4 + DINOv2 + YOLO, 오류 없음). 데모 전 `bash scripts/board_llm.sh use gemma4`로 Gemma4 고정 권장

```sh
cd ~/project/hows-everything-so-far
ET=$HOME/git/executorch

# Vision 8001 (bundle: models/board/vision/dinov2-qnn-v4c, 되돌리기는 -v3 / -v1)
LD_LIBRARY_PATH=$ET/build-x86/backends/qualcomm:/usr/lib ADSP_LIBRARY_PATH=/usr/lib \
VISION_MODEL_BACKEND=external VISION_ADAPTER=services.vision.backend:create_backend \
VISION_MODEL_PATH=models/board/vision/dinov2-qnn-v4c \
VISION_RUNNER_BIN=$ET/build-x86/examples/qualcomm/executor_runner/qnn_executor_runner \
setsid nohup .venv/bin/python -m uvicorn services.vision.server:create_app --factory \
  --host 127.0.0.1 --port 8001 > ~/model_output/logs/vision-8001.log 2>&1 < /dev/null &

# Gemma 8000 (.env.board가 QWEN_MODEL_BACKEND=executorch)
setsid nohup .venv/bin/python -m uvicorn services.qwen.server:create_app --factory \
  --host 127.0.0.1 --port 8000 > ~/model_output/logs/qwen-8000.log 2>&1 < /dev/null &

# Controller 8080 + STT 8002 (whisper-server 8178이 떠 있어야 함)
STT_MODEL_BACKEND=external STT_ADAPTER=services.stt.whisper_http:create_backend \
setsid nohup .venv/bin/python scripts/dev.py --mode direct --with-stt --env-file .env.board \
  > logs/dev-8080.out 2>&1 < /dev/null &

# 확인: 전체 ready=true, vision/stt source=external
curl -s http://127.0.0.1:8001/ready; curl -s http://127.0.0.1:8000/ready; curl -s http://127.0.0.1:8080/ready

# Vision·Gemma 끄기 (Controller는 .venv/bin/python scripts/dev.py --stop --env-file .env.board)
pkill -f 'services.vision.server:create_app --factory --host 127.0.0.1 --port 8001'
pkill -f 'services.qwen.server:create_app --factory --host 127.0.0.1 --port 8000'
```

## 현장 승인 전 확인

실제 DINO/STT 입력·출력·bbox 좌표계, 영어 음료 요청 결과, CPU/QNN 별도 export 및 delegation/profile, 메모리/지연/두 모델 동시 자원, USB disconnect, Bridge/watchdog/cancel, 태블릿 출력 청취·안내 완료 신호·보드 마이크 녹음. 모두 **현장 미검증**이며 로컬 fixture/UI 테스트와 구분해 기록한다.

## 보드 ExecuTorch 설치 기록 (2026-10-17, QCVENTUNO002)

주최 측 Drive `ExecuTorch/Ventuno Q/source`의 `ventuno_executorch_source.tar.gz`(3.18GB)와 `Ventuno_Q_ExecuTorch_Bringup.pdf` 절차대로 설치했다. 이 checkout은 **QCS8275 타깃(SoC ID 82)과 aarch64용 QNN Python 바인딩**을 포함해 **보드에서 직접 QNN export**가 된다(Mac Docker 우회 불필요).

| 항목 | 값 |
| --- | --- |
| QNN 런타임 | apt `ppa:ubuntu-qcom-iot/qcom-ppa` → `libqnn1 libqnn-dev qnn-tools` **2.49.0** (sudo 필요) |
| ExecuTorch | `~/git/executorch` (commit `5249a13c55`), venv `~/git/executorch/.venv` (Python 3.12.3) |
| 의존성 | `requirements-ventuno.txt` (PDF의 `requirements.txt`는 오기). `torchao==0.18.0.dev20260729+xpu` 나이틀리가 삭제돼 **`torchao==0.18.0`으로 고정**, `--extra-index-url https://download.pytorch.org/whl/cpu`. YOLO export용 `ultralytics==8.4.178` 추가 |
| flatc | PATH에 없음 → `FLATC_EXECUTABLE=~/git/executorch/build-xnnpack/third-party/flatc_ep/bin/flatc` (aarch64, 24.3.25) |
| QNN_SDK_ROOT | export 설정이 x86 SDK 레이아웃(`lib/x86_64-linux-clang/libQnnHtp.so`)을 가정 → `~/qnn_sdk_root/lib/x86_64-linux-clang/`에 `/usr/lib/libQnn*.so` 심볼릭 링크 후 `QNN_SDK_ROOT=~/qnn_sdk_root` |
| export | `PYTHONPATH=~/git` + 위 두 변수. 예제 스크립트 기본 SoC가 SM8650이므로 **`--soc QCS8275` 필수** (PDF의 `--soc_model add`는 `-m add` 오기) |
| runner | `~/git/executorch/build-x86/examples/qualcomm/executor_runner/qnn_executor_runner`, LLM은 `.../oss_scripts/llama/qnn_llama_runner`. `LD_LIBRARY_PATH=~/git/executorch/build-x86/backends/qualcomm:/usr/lib`, `ADSP_LIBRARY_PATH=/usr/lib` |
| Python 런타임 | **없음**(`_portable_lib` 미포함) → 보드 Vision bundle은 `cli` runner(`VISION_RUNNER_BIN`) 사용 |

보드 NPU 실측 (`ml/evaluation/board_npu_check.py`, `scripts/board_llm.sh`):

| 모델 | 형식 | 결과 |
| --- | --- | --- |
| add.pte (smoke) | `export_example.py -m add --soc QCS8275` | 0.37 ms |
| DINOv2-small CLS | `ml.export.export_qnn --model dinov2 --quant fp16` (46 MB, 49초) | **5.8~6.0 ms/장**, fp32 대비 cosine 0.9995 |
| YOLO11n | `--model yolo --quant 16a8w` (3.3 MB, 2분 22초) | **16 ms/장**, fp32 박스 19/21 일치 |
| Gemma3 1B (주최 측 `.pte`, ctx 5000) | `qnn_llama_runner --decoder_model_version gemma3 --eval_mode 1` | prefill 317~393 tok/s, decode 26~30 tok/s, 로딩 3~5초, 최대 RSS 1.4 GB. 단답 산수 오답 있음 |
| Gemma4 E2B (주최 측 `.pte`, ctx 2000) | `--decoder_model_version gemma4 --eval_mode 1` | prefill 205~233 tok/s, decode 16 tok/s, 로딩 3.3~4.9초, 최대 RSS 2.2 GB |

- **Qwen3 0.6B `.pte`는 주최 측 번들에 없다.** 보드 export는 hybrid 모드가 메모리 ~100GB를 요구하고 kv 모드도 torchtune↔torchao 의존성 충돌이 있어 중단했다. LLM은 주최 측 Gemma를 `scripts/board_llm.sh`로 쓴다(`use gemma3|gemma4|auto`, `auto`는 MemAvailable ≥ 3.7GB면 gemma4). 앱 연결: Qwen 서비스 `executorch` backend = `services/qwen/board_llm.py`. Controller 프롬프트 1건 실측 gemma4 정답 8.8초 / gemma3 오답 5.4초 → 데모는 `use gemma4`.
- LLM을 연달아 실행하면 직전 프로세스의 NPU 메모리 반환이 늦어 `Failed to find available PD`가 날 수 있다 → 스크립트가 5초 후 재시도.
- 보드 Vision bundle 만들기: 위 QNN `.pte`로 `python -m ml.training.make_head --runner cli --runner-bin <qnn_executor_runner>` → `python -m ml.export.make_bundle --out models/board/vision/<name> --dino-runner cli --yolo-runner cli ...`.
