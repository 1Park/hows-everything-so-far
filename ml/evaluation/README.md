# Offline model evaluation

Holds offline evaluation code for the detection, type and fill-level models, and code that compares PyTorch / export outputs.

- Comparison of images, ground truth, per-object results and failure cases
- Evaluation on data not used for training
- Comparison of outputs before and after conversion with the same input and preprocessing
- Analysis of real latency, memory and delegation records collected on the board

Store bulk outputs in places such as experiment folders under `models/`. Put shareable configs and summary reports in `docs/`, and state the model/data versions and where it was run. Generated illustrative photos and fixtures are not treated as measured accuracy data.

The archive of past Qwen text and STT-like substitution evaluations stays as is in `docs/qwen_evaluation/`. Keep the app's unit/integration tests separate from model accuracy evaluation.

## Files

- `eval_fewshot.py` — DINOv2 embeddings + prototype/logreg few-shot, CONF_MIN coverage
- `bench_latency.py` — Mac CPU/MPS latency
- `detect_test.py` — COCO YOLO11n cup detection (without fine-tuning)
- `yolo_et.py` — YOLO `.pte` + numpy postprocessing vs ultralytics comparison
- `qnn_sim_check.py` — runs a QNN `.pte` on the x86 HTP simulator and compares it with fp32 (Docker)
