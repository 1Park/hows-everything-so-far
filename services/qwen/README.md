# Qwen 생성 서버

`server.py:create_app`, 기본127.0.0.1:8000. POST /v1/chat/completions, GET /v1/models, /health, /ready. model/messages/생성 옵션 검증, admitted4/동시1 queue, queue+실행 timeout20초, 요청 ID/log 제공.

QWEN_MODEL_BACKEND=mlx는 QWEN_UPSTREAM_URL(기본 Mac)로 HTTP 생성, fixture는 결정적 개발용, executorch는 실제 board adapter 미연결을 명시적으로503 반환. 자동 fixture fallback 없음. .env.board의 executorch readiness503은 보드 전 상태를 정확히 나타낸다.

Controller의 QWEN_BACKEND=fixture/http는 서버 내부 backend 설정과 별개다. direct 모드는 실제 Mac 직접 호출, proxy/integration은 우리 서버→Mac. 제품 프롬프트/JSON 검증/메뉴/승인은 app/language.py와 Controller. [계약](../../docs/CONTRACTS.md).
