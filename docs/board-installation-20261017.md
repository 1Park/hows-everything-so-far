# Board installation record (2026-10-17)

This is the installation and measurement record from that time. For current operation, follow the [board runbook](BOARD_RUNBOOK.md).
The CLI call times below are separate from the invoke latency of the current resident services.

## Board ExecuTorch installation record (2026-10-17, QCVENTUNO002)

Installed following the organizer Drive `ExecuTorch/Ventuno Q/source` `ventuno_executorch_source.tar.gz` (3.18GB) and the `Ventuno_Q_ExecuTorch_Bringup.pdf` procedure. This checkout includes **the QCS8275 target (SoC ID 82) and aarch64 QNN Python bindings**, so **QNN export works directly on the board** (no Mac Docker workaround needed).

| Item | Value |
| --- | --- |
| QNN runtime | apt `ppa:ubuntu-qcom-iot/qcom-ppa` → `libqnn1 libqnn-dev qnn-tools` **2.49.0** (requires sudo) |
| ExecuTorch | `~/git/executorch` (commit `5249a13c55`), venv `~/git/executorch/.venv` (Python 3.12.3) |
| Dependencies | `requirements-ventuno.txt` (`requirements.txt` in the PDF is a typo). The `torchao==0.18.0.dev20260729+xpu` nightly was removed, so **pinned to `torchao==0.18.0`**, `--extra-index-url https://download.pytorch.org/whl/cpu`. Added `ultralytics==8.4.178` for YOLO export |
| flatc | Not on PATH → `FLATC_EXECUTABLE=~/git/executorch/build-xnnpack/third-party/flatc_ep/bin/flatc` (aarch64, 24.3.25) |
| QNN_SDK_ROOT | The export config assumes the x86 SDK layout (`lib/x86_64-linux-clang/libQnnHtp.so`) → symlink `/usr/lib/libQnn*.so` into `~/qnn_sdk_root/lib/x86_64-linux-clang/`, then `QNN_SDK_ROOT=~/qnn_sdk_root` |
| export | `PYTHONPATH=~/git` + the two variables above. The example script's default SoC is SM8650, so **`--soc QCS8275` is required** (`--soc_model add` in the PDF is a typo for `-m add`) |
| runner | `~/git/executorch/build-x86/examples/qualcomm/executor_runner/qnn_executor_runner`; for LLMs, `.../oss_scripts/llama/qnn_llama_runner`. `LD_LIBRARY_PATH=~/git/executorch/build-x86/backends/qualcomm:/usr/lib`, `ADSP_LIBRARY_PATH=/usr/lib` |
| Python runtime | **None** (`_portable_lib` not included) → the board Vision bundle uses the `cli` runner (`VISION_RUNNER_BIN`) |

Board NPU measurements (`ml/evaluation/board_npu_check.py`, `scripts/board_llm.sh`):

| Model | Format | Result |
| --- | --- | --- |
| add.pte (smoke) | `export_example.py -m add --soc QCS8275` | 0.37 ms |
| DINOv2-small CLS | `ml.export.export_qnn --model dinov2 --quant fp16` (46 MB, 49 s) | **5.8~6.0 ms/image**, cosine 0.9995 vs. fp32 |
| YOLO11n | `--model yolo --quant 16a8w` (3.3 MB, 2 min 22 s) | **16 ms/image**, 19/21 boxes match fp32 |
| Gemma3 1B (organizer `.pte`, ctx 5000) | `qnn_llama_runner --decoder_model_version gemma3 --eval_mode 1` | prefill 317~393 tok/s, decode 26~30 tok/s, load 3~5 s, max RSS 1.4 GB. Some wrong answers on short arithmetic |
| Gemma4 E2B (organizer `.pte`, ctx 2000) | `--decoder_model_version gemma4 --eval_mode 1` | prefill 205~233 tok/s, decode 16 tok/s, load 3.3~4.9 s, max RSS 2.2 GB |

- **There is no Qwen3 0.6B `.pte` in the organizer bundle.** Board export was abandoned: hybrid mode needs ~100GB of memory, and kv mode also hits a torchtune↔torchao dependency conflict. The LLM uses the organizer's Gemma through `scripts/board_llm.sh` (`use gemma3|gemma4|auto`; `auto` picks gemma4 when MemAvailable ≥ 3.7GB). App connection: Qwen service `executorch` backend = `services/qwen/board_llm.py`. One measured Controller prompt: gemma4 correct in 8.8 s / gemma3 wrong in 5.4 s → the demo uses `use gemma4`.
- Running the LLM back to back can fail with `Failed to find available PD` because the previous process returns NPU memory late → the script retries after 5 s.
- Building the board Vision bundle: with the QNN `.pte` above, `python -m ml.training.make_head --runner cli --runner-bin <qnn_executor_runner>` → `python -m ml.export.make_bundle --out models/board/vision/<name> --dino-runner cli --yolo-runner cli ...`.
