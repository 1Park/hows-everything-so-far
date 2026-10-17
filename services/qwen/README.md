# Qwen service

기본 bind: `127.0.0.1:8000`. 보드의 Qwen3-0.6B `.pte`·tokenizer와 ExecuTorch runtime을 연결하는 API 서버를 둔다. 아직 구현 전이다.

- 입력 메시지 검증, tokenizer·chat template 적용, 생성 옵션 처리
- 모델 로딩·추론 backend와 제공 runner adapter
- 생성 결과·오류 반환, health·소요 시간 기록
- 로컬 API 개발용 mock model backend

리필 정책·영어 제품 프롬프트·메뉴 검증·고객 확인은 Controller의 `app/`에 둔다. 이 서버는 물리 동작을 승인하지 않는다. API 계약은 Mac의 `/v1/chat/completions` 호출과 호환되도록 맞추거나 Controller client adapter에서 차이를 흡수한다. 최종 구현은 보드 runner를 확인한 뒤 결정한다.

공용 Mac mini의 기존 MLX 서버는 개발 중 그대로 호출한다. 이 폴더의 서버를 Mac 서버 대신 반드시 띄울 필요는 없다. HTTP 서버가 상주해도 일회성 runner를 요청마다 실행하면 모델 재로딩이 생길 수 있으므로 실제 상주 실행 여부를 확인한다.
