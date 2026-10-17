# App — Controller

보드 또는 개발자 노트북에서 실행하는 FastAPI Controller와 제품 로직을 둔다. 기본 포트는 8080이다. 아직 서버 코드는 없다.

구현할 코드:

- 서버 진입점, HTTP 고객 입력·확인/취소와 WebSocket 상태 이벤트
- 상태 머신, 리필 대상 선택·잔량 정책, 요청 검증, timeout·취소·중복 확인 처리
- Vision fixture / HTTP client와 Qwen HTTP client
- 영어 프롬프트, 현재 요청 + 새 발화 구성, 모델 응답 파싱과 제품 메뉴 검증
- [시연 UI](ui/README.md), [HardwareIO](hardware/README.md)

Controller가 scene·object·request를 연결하고 물리 동작을 승인한다. Qwen 서버는 텍스트를 생성하고 Controller가 요청을 검증한다. 공통 데이터 schema는 `common/`에 둔다.

카메라를 직접 다시 열거나 모델을 여기서 로드하지 않는다. Vision 모델·카메라는 `services/vision/`, Qwen 모델 runtime은 `services/qwen/`에서 관리한다. 로컬에서는 Vision fixture와 Mac Qwen API로 개발할 수 있다.
