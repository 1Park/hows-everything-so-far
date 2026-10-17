# Qwen 생성 서버

`server.py:create_app`, 기본127.0.0.1:8000. POST /v1/chat/completions, GET /v1/models, /health, /ready. model/messages/생성 옵션 검증, admitted4/동시1 queue, queue+실행 timeout20초, 요청 ID/log 제공.

QWEN_MODEL_BACKEND=mlx는 QWEN_UPSTREAM_URL(기본 Mac)로 HTTP 생성, fixture는 결정적 개발용, executorch는 보드 Gemma(`board_llm.py` → `scripts/board_llm.sh ask` → `qnn_llama_runner`, NPU)로 생성한다. 자동 fixture fallback 없음.

## 보드 LLM = Gemma (Qwen 안 씀)

주최 측 번들에 Qwen3 `.pte`가 없어서 보드 LLM은 Gemma다(보드 export 중단 경위는 [BOARD_RUNBOOK](../../docs/BOARD_RUNBOOK.md)). 서비스 이름·포트·`QWEN_*` 설정 이름은 Controller와의 경계라 그대로 둔다.

- 모델 선택: `scripts/board_llm.sh use gemma4|gemma3|auto` (`auto`는 MemAvailable ≥ 3.7GB면 gemma4). **gemma4 권장** — Controller 프롬프트 실측에서 gemma4 정답, gemma3 오답
- 모델은 상주하지 않는다. 요청마다 runner를 실행해 load 4~7초 + 생성 → 요청당 약 9초(gemma4). 전체 timeout 20초 안
- `/ready`: 선택된 모델 `.pte`가 있으면 200. timeout·취소 시 runner 프로세스 그룹까지 종료(NPU 반환). 메모리 부족은 503 `model_memory`
- 응답의 `runner` 필드에 실제 실행된 모델과 load/prefill/decode 속도가 들어간다
- `QWEN_MODEL` 값(`.env.board`의 `mlx-community/Qwen3-0.6B-4bit`)은 Controller와 서비스가 맞춰 쓰는 ID일 뿐 실제 모델이 아니다. 바꾸려면 두 프로세스를 같이 재시작한다

보드 실행 (레포 루트, `.env.board`가 `QWEN_MODEL_BACKEND=executorch`):

```bash
setsid nohup .venv/bin/python -m uvicorn services.qwen.server:create_app --factory --host 127.0.0.1 --port 8000 > ~/model_output/logs/qwen-8000.log 2>&1 < /dev/null &
```

Controller의 QWEN_BACKEND=fixture/http는 서버 내부 backend 설정과 별개다. direct 모드는 실제 Mac 직접 호출, proxy/integration은 우리 서버→Mac. 제품 프롬프트/JSON 검증/메뉴/승인은 app/language.py와 Controller. [계약](../../docs/CONTRACTS.md).

파일 기반 runtime을 연결하기 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. QWEN_MODEL은 API model ID이며 QWEN_MODEL_PATH와 다른 개념이다. 현재 mlx backend는 HTTP client이고, models/local 또는 models/board의 가중치를 직접 읽지 않는다. 실제 runtime 연결 시 필요한 경로 설정만 추가한다.
