# Qwen 생성 서버

`server.py:create_app`, 기본127.0.0.1:8000. POST /v1/chat/completions, GET /v1/models, /health, /ready. model/messages/생성 옵션 검증, admitted4/동시1 queue, queue+실행 timeout20초, 요청 ID/log 제공.

QWEN_MODEL_BACKEND=mlx는 QWEN_UPSTREAM_URL(기본 Mac)로 HTTP 생성, fixture는 결정적 개발용, executorch는 실제 board adapter 미연결을 명시적으로503 반환. 자동 fixture fallback 없음. .env.board의 executorch readiness503은 보드 전 상태를 정확히 나타낸다.

Controller의 QWEN_BACKEND=fixture/http는 서버 내부 backend 설정과 별개다. direct 모드는 실제 Mac 직접 호출, proxy/integration은 우리 서버→Mac. 제품 프롬프트/JSON 검증/메뉴/승인은 app/language.py와 Controller. [계약](../../docs/CONTRACTS.md).

파일 기반 runtime을 연결하기 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. QWEN_MODEL은 API model ID이며 QWEN_MODEL_PATH와 다른 개념이다. 현재 mlx backend는 HTTP client이고, models/local 또는 models/board의 가중치를 직접 읽지 않는다. 실제 runtime 연결 시 필요한 경로 설정만 추가한다.
