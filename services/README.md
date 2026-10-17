# Model service layers

Vision8001, STT8002, Qwen8000의 독립 FastAPI/Uvicorn(worker1). `python scripts/dev.py --mode integration`으로 모두 시작한다. 기본 로컬 direct는 모델 프로세스를 시작하지 않는다.

Vision/STT는 `sensory.py`의 transport validation·bounded gate·fixture·trusted async adapter factory. **모델과 전후처리는 팀원 영역**. Qwen은 generic 생성 서버이며 제품 프롬프트/정책은 app/ 소유. [공통 계약·연결 방법](../docs/CONTRACTS.md).
