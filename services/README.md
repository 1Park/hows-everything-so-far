# 모델 서비스

각 서비스는 독립 FastAPI/Uvicorn 프로세스(worker 1개)다. `server.py:create_app`이 진입점이며 `/health`, `/ready`, OpenAPI를 제공한다.

- [Qwen API :8000](qwen/README.md): 보드 Gemma4 / 개발 Mac HTTP / 명시적 fixture.
- [Vision :8001](vision/README.md): fixture 또는 YOLO·DINOv2 backend.
- [STT :8002](stt/README.md): fixture 또는 외부 Whisper adapter.

`sensory.py`는 Vision/STT transport 검증·추론 gate·external factory를 공유한다. 제품 프롬프트·정책·확인은 Controller가 소유한다. [API 경계](../docs/CONTRACTS.md), [실행 모드](../README.md).
