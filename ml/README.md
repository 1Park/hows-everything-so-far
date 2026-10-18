# ML — training, evaluation, export

Holds the environment for **building** models. The servers that **run** models on the board are in `services/`. Separate from the app's Docker-free deployment, the Linux Docker training and QNN export environment required by the organizers is managed in this folder.

| Location | Contents |
| --- | --- |
| [`Dockerfile`](Dockerfile), [`docker-run.sh`](docker-run.sh) | x86-64 QNN export and HTP simulator environment (Rosetta on Mac). Can be replaced with the organizers' checkout/SDK |
| [`requirements.txt`](requirements.txt) | Training, evaluation and export dependencies kept separate from the app (Mac, Python 3.13) |
| [tools/](tools/) | Camera collection and live check (`camera.py`), fake runner for CLI runner tests |
| [configs/](configs/README.md) | Model, data, training, preprocessing, quantization and export settings |
| [training/](training/README.md) | Model heads, training, fine-tuning, checkpoint creation |
| [evaluation/](evaluation/README.md) | Offline image model evaluation, comparison before and after conversion |
| [export/](export/README.md) | `.pte` conversion for the board, validation, bundle metadata creation |

The supported environments for training and export may differ, and installing Docker does not automatically make Linux x86-64 tools compatible with an ARM host.

```text
data/ raw, labels → training → models/ checkpoint
                             → evaluation
                             → export / quantization → models/ deployment bundle
                                                        ↓
                                     inference with ExecuTorch in services/
```

Vision currently uses YOLO11n detection plus DINOv2 features and a linear head. The board LLM is the provided Gemma4 bundle and is not trained in this folder.

Data is stored in `data/` and weights and outputs in `models/`, both excluded from Git. Record the settings, collection methods, model versions and data split information needed for reproduction alongside the code. Besides the model and any required tokenizer, a deployment bundle includes the input shape/dtype/layout, preprocessing and labels, output spec, model source, runtime and SDK versions, and target SoC and export settings.

The board server does not import this folder's training environment or run the training Docker. The existing Qwen utterance evaluation records are kept in `docs/qwen_evaluation/`; when adding drink evaluations, keep them separate from the existing results.

## Current implementation — DINOv2 Vision (2026-10-17)

Result records: [docs/vision_evaluation](../docs/vision_evaluation/README.md). The runtime is in [services/vision](../services/vision/README.md).

### Environment

```sh
python3.13 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt   # Mac training, evaluation, XNNPACK export
docker build --platform linux/amd64 -t refill-ml-export ml                          # x86 QNN export and simulator
```

Run all commands from the repo root as `python -m ml.<folder>.<script>` (`ml/.venv/bin/python`). For Docker, use `ml/docker-run.sh python -m ...`.
On the first Docker export, ExecuTorch downloads QAIRT SDK 2.37 (~3GB) and libc++ (~5GB) into the volume `refill-qnn-cache`.

### Flow

| Step | Command | Output |
|---|---|---|
| Data collection | `python -m ml.tools.camera collect --drinks water coke coffee` (iTerm/Terminal.app — camera permission). For cans and bottles, `--classes other` | `data/real/<drink>__<level>/`, `data/real/other/` |
| Synthetic data | `python -m ml.training.gen_synthetic` | `data/synthetic/` (for pipeline validation) |
| Accuracy | `python -m ml.evaluation.eval_fewshot --data data/real --shots 3 5 10` | `models/experiments/vision/fewshot_*.json` |
| Cup detection | `python -m ml.evaluation.detect_test` | Whether COCO YOLO detects the cups |
| CPU .pte | `python -m ml.export.export_xnnpack`; for YOLO, ultralytics `format="executorch"` | `models/local/vision/` |
| NPU .pte | `ml/docker-run.sh python -m ml.export.export_qnn --model {yolo,dinov2} [--quant fp16] --soc_model QCS8275 --build_folder /tmp --compile_only` | `models/experiments/vision/qnn/<soc>_<quant>/` |
| NPU validation | `ml/docker-run.sh python -m ml.evaluation.qnn_sim_check {yolo,dinov2} <pte>` | HTP simulator output vs fp32 |
| Board export and NPU | In the board ExecuTorch venv, `python -m ml.export.export_qnn ... --soc_model QCS8275`, `python -m ml.evaluation.board_npu_check {dinov2,yolo} --pte <pte> --images <dir>` | Board measurements (installation and env vars: [BOARD_RUNBOOK](../docs/board-installation-20261017.md)) |
| Board LLM | `scripts/board_llm.sh status / use gemma4 / ask "..."` | Switches to and runs the organizers' Gemma `.pte` |
| Training crops | `python -m ml.training.make_crops --data data/real --bundle <bundle> --runner-bin <runner> --out data/crops` | YOLO mode: training photos → the same pad crops as inference (`data/crops/`, neighboring objects in `data/crops_extra/`) |
| Board camera collection | `python -m ml.tools.board_collect --bundle <bundle> --runner-bin <runner> --labels water__low water__mid ...` | Controller `/api/frame` (real 640×480) → YOLO crops labeled from left to right |
| Head training | `python -m ml.training.make_head --data data/crops [more roots] --dino-pte <pte> --runner {py,cli} --model lda --augment 4` (**with the .pte that will be deployed**; board v6/v7 head; logistic: `--class-weight balanced`) | head JSON + features `.npz` |
| bundle | `python -m ml.export.make_bundle --out models/{local,board}/vision/<name> ...` | `bundle.json` + .pte + head |

### Rules

- **In YOLO mode, train the head on YOLO crops too** (`make_crops`). Training on whole photos also learns the background objects: half of the coke__full photos had a cola can next to the cup, and can crops came out as coke. Adding crops of neighboring objects cut off at the edges as other would also discard real glasses at the edge of the frame → do not add them
- **Train the head on features produced by the .pte that will actually run on the board.** Using an fp32 head on a quantized model drops accuracy sharply (int8 approximation 88.8%→68.2%, QNN 16a8w 24%).
- For DINOv2 QNN, **prefer fp16** (cosine 0.9992 vs fp32). 16a8w gives 0.58, and 16a16w is broken.
- Stock ExecuTorch 1.5.1 has no QCS8275 target. Export with the organizers' checkout/SDK, and use SM8650 (same HTP v75) outputs only for rehearsal.
- Match the board SDK version and the export SDK version (`QNN_SDK_ROOT_HOST=<qairt> ml/docker-run.sh ...`).
- Input tensors must be contiguous in memory (with stride 0, export and raw input fail) — guaranteed by `services/vision/preprocess.py`.
- HF DINOv2 does not export as is (bicubic interpolation of position embeddings, attention mask expand inside the graph) → use the `export_qnn.build_dinov2` wrapper. YOLO is run once with a 640 input to turn the anchors into constants (`build_yolo`).
