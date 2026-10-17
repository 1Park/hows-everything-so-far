# Model assets and integration guidelines

For developers and coding agents connecting real models. Keep integration small: use the existing service backend boundary, a few explicit environment settings, and the public API contracts. Do not introduce a model registry, automatic runtime detection, or another configuration framework.

## Asset layout

```text
models/
  local/                 # Native development runtime assets
    vision/              # Detector / DINOv2 bundle owned by the Vision developer
    stt/                 # STT assets owned by the STT developer
    qwen/                # Only if running Qwen weights on this machine
  board/                 # VENTUNO Q runtime assets
    vision/              # Board-compatible Vision bundle
    stt/                 # Only if STT runs on the board
    qwen/                # Qwen .pte, tokenizer, and required companion files
  experiments/           # Local training/export outputs
```

This is a placement convention, not an installed bundle. Create directories when adding assets; Git does not preserve empty directories. Keep vendor bundle filenames and companion files together. No particular tensor layout, internal labels, or bundle format is assumed. Existing assets elsewhere may be referenced by an explicit path without copying them.

Only this README is tracked under `models/`. Weights, tokenizers, exports, and other large assets remain ignored. Record acquisition instructions, model version/checksum, and required runtime in the owning service README or `ml/configs/`; do not commit personal absolute paths or credentials.

## Configuration convention

Use personal `.env` for development and `.env.board` plus process-environment overrides for the board. Choose the backend explicitly as well as its path: a local development model and a board `.pte` may require different runtimes. `APP_ENV` alone must not silently select a runtime or scan folders for a model.

When implementing a file-loading backend, use these names as needed:

| Setting | Purpose | Example relative paths: local / board |
| --- | --- | --- |
| `VISION_MODEL_PATH` | Vision bundle file or directory | `models/local/vision/...` / `models/board/vision/...` |
| `STT_MODEL_PATH` | STT bundle file or directory | `models/local/stt/...` / `models/board/stt/...` |
| `QWEN_MODEL_PATH` | Qwen weights or runtime bundle | `models/local/qwen/...` / `models/board/qwen/...` |
| `QWEN_TOKENIZER_PATH` | Separate tokenizer, if the runtime needs one | Within the matching Qwen bundle |

Resolve relative paths against the repository root; allow explicit absolute paths through personal configuration. Add only the settings needed by the concrete backend to `common/config.py` when connecting it. A path may identify a file or directory according to the actual runtime; validate the required files in that backend.

**Current implementation:** QWEN_MODEL_PATH, QWEN_TOKENIZER_PATH and VISION_MODEL_PATH are wired into Settings. QNN_LLAMA_RUNNER and QWEN_SEQ_LEN configure native Qwen execution; QNN_RUNNER and VISION_MODEL_PATH configure common.executorch.DinoRunner. STT_MODEL_PATH remains a convention for its owner. MLX still calls HTTP. Native runtime/bundles are supplied separately; board inference is unverified. See [Qwen setup](../services/qwen/README.md) and [Vision integration](../services/vision/README.md).

## Implementation boundaries

1. Read the owning `services/vision`, `services/stt`, or `services/qwen` README and [public contracts](../docs/CONTRACTS.md) first. Preserve the current HTTP API and Vision/STT no-argument `package:create_backend` factory contract.
2. Put model loading and runtime-specific work behind that service's backend; connect board Qwen at the existing `ExecuTorchBackend` boundary. The Controller uses API URLs and must not load model files.
3. Vision developers own detection, crop, DINOv2, preprocessing, and output conversion. STT developers own decoding, audio preprocessing, and recognition. Other agents must not guess or replace those implementations. Keep DINOv2 and Qwen3-0.6B.
4. Load/reuse the model where the runtime supports it, keep blocking inference off the event loop, and retain the existing timeout/readiness/error contract. Missing files, unsupported runtimes, or failed initialization must produce an explicit error/not-ready state, never an automatic fixture or remote fallback. Fixtures remain explicit; source labels must stay truthful.
5. Keep camera ownership in Controller VideoSource and microphone/speaker ownership in the tablet browser. Model backends receive the transported image/audio; do not open those devices again.
6. Document the actual backend setting, asset acquisition, runtime dependencies, and one startup command. Verify readiness, a real input, and missing-file behavior. Report local runtime verification separately from board verification.

Training/export dependencies and any required Docker environment belong in `ml/`. App deployment remains native Ubuntu + venv; do not add training dependencies or guessed board SDK versions to the app just to prepare this structure.
