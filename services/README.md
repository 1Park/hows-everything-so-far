# Model services

Each service is an independent FastAPI/Uvicorn process (1 worker). `server.py:create_app` is the entry point and provides `/health`, `/ready` and OpenAPI.

- [Qwen API :8000](qwen/README.md): board Gemma4 / dev Mac HTTP / explicit fixture.
- [Vision :8001](vision/README.md): fixture or YOLO/DINOv2 backend.
- [STT :8002](stt/README.md): fixture or external Whisper adapter.

`sensory.py` shares Vision/STT transport validation, the inference gate and the external factory. The Controller owns product prompts, policy and confirmation. [API boundaries](../docs/CONTRACTS.md), [Run modes](../README.md).
