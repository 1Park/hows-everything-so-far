# 보드 설치 기록 (2026-10-17)

당시 설치·실측 기록이다. 현재 실행 방법은 [보드 runbook](BOARD_RUNBOOK.md)을 따른다.
아래 CLI 호출 시간은 현재 상주 서비스의 invoke 지연과 구분한다.

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
