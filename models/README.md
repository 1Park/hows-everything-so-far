# Model files

Models, tokenizers and native binaries are not committed to Git. Use `models/local/`, `models/board/` and `models/experiments/` by purpose, or specify an explicit external path. Setting a path alone does not automatically select a backend.

| Used by | Actual settings and files |
| --- | --- |
| Vision | `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=services.vision.backend:create_backend`, `VISION_MODEL_PATH` is the bundle directory (`bundle.json`, `.pte`, head) |
| Board Vision native worker | `VISION_WORKER_BIN`; YOLO/DINO are preloaded at service start. For build and deployment see the [Vision guide](../services/vision/README.md) |
| Board Gemma4 | `QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4`. Check file paths with `scripts/board_llm.sh config` |
| Dev Mac LLM | HTTP connection. Does not read local model files |
| Optional Qwen CLI | `QWEN_MODEL_BACKEND=qwen_cli`, runner/model/tokenizer/seq_len settings. Separate from the board's default Gemma path |
| STT | `STT_MODEL_BACKEND=external`, Whisper HTTP adapter and `STT_WHISPER_URL`. The model is owned by the external whisper.cpp server |

There is currently no `STT_MODEL_PATH` setting in the code. Each backend defines its actual file requirements and path resolution. Vision bundle relative paths are relative to the repo root.

Model loading and pre/postprocessing live in the corresponding service backend. The Controller calls the APIs and is the sole owner of the camera and microphone. Missing files and load failures are handled as explicit errors and are not automatically replaced with fixtures.

[Board operation](../docs/BOARD_RUNBOOK.md), [LLM](../services/qwen/README.md), [Vision](../services/vision/README.md), [STT](../services/stt/README.md), [Training and export](../ml/README.md).
