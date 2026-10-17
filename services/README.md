# Model services

FastAPI + Uvicorn으로 각각 실행하는 [Vision](vision/README.md)과 [Qwen](qwen/README.md) API 서버를 둔다. 앱과 같은 레포에 있지만 별도 프로세스다. 보드에서는 Docker 없이 직접 실행한다.

각 서버는 API·입력 검증·모델 실행 adapter·후처리·health 상태를 담당한다. 초기 Uvicorn worker는 서버별 1개로 두고 긴 추론 작업은 요청 처리와 분리한다. 지원되는 모델 상주 실행 방식은 보드에서 확인한다.

서버 코드는 로컬에서 작성하고 mock model backend로 검증할 수 있다. 실제 `.pte`·QNN·runner 연결과 지연·메모리·장치 접근은 보드에서 검증한다. 학습·변환 코드는 `ml/`에 두고 서버는 배포 bundle만 사용한다.
