# Qwen 생성 서버 / 보드 Gemma

`server.py:create_app`, 기본 127.0.0.1:8000. POST `/v1/chat/completions`, GET
`/v1/models`, `/health`, `/ready`. model/messages/생성 옵션 검증, admitted4/동시1
queue, queue+실행 timeout20초, 요청 ID/log 제공. 제품 프롬프트와 `intent/item`
검증은 `app/language.py`와 Controller 소유다. `portion`은 사용하지 않고 이해하지
못한 요청은 `not_understood`로 반환한다. 자동 fixture fallback은 없다.

## 보드: 상주 Gemma4

`QWEN_MODEL_BACKEND=board`, `QWEN_MODEL=gemma4`. 기존 보드 설정의
`QWEN_MODEL_BACKEND=executorch`도 같은 `BoardLLMBackend`에 연결한다.
주최 측 번들에 Qwen3 `.pte`가 없어 실제 보드 모델은 Gemma이며 서비스 이름·포트와
`QWEN_*`는 Controller와의 API 경계 이름이다. 설치 기록은
[BOARD_RUNBOOK](../../docs/BOARD_RUNBOOK.md), 기존 상주 실측은
[RESIDENT_LLM](../../docs/RESIDENT_LLM.md)을 참고한다.

- 서버 시작 시 Gemma4 worker를 띄워 모델 로드 완료 신호를 기다린다. 생성 요청은
  보내지 않는다. 같은 모델의 요청은 같은 PID와 로드된 QNN 컨텍스트를 재사용한다.
- 파일 없음·worker 오류·120초 시작 timeout이면 서버 시작에 실패하고 child를 정리한다.
  `/ready`는 실제 로드된 worker가 살아 있을 때만 ready=true다.
- 취소·timeout·실행 오류에는 worker 프로세스 그룹을 회수한다. 이후 `/ready`는 false이고
  다음 생성 요청에서 다시 로드한다. 요청 간 KV는 초기화한다.
- Gemma3 모델·업로드·명시 실행 코드는 유지하지만 기본 선택과 평가는 Gemma4다.
  `scripts/board_llm.sh use gemma4`로 선택을 고정하며 API 시작도 항상 Gemma4를 로드한다.
- API `model=gemma3|gemma4`는 명시 전환을 지원한다. 응답 `runner`에는 실제 모델·PID·
  cold_start·load_seconds·prefill/decode 통계가 들어간다.
- `QWEN_MODEL`은 API 식별자다. 과거 Qwen ID를 사용한 프로세스와 설정을 바꾸려면
  Controller와 Qwen 서비스를 같이 재시작한다. native worker와 호환 번들은 별도 설치한다.

```bash
setsid nohup .venv/bin/python -m uvicorn services.qwen.server:create_app --factory --host 127.0.0.1 --port 8000 > ~/model_output/logs/qwen-8000.log 2>&1 < /dev/null &
```

## 개발 HTTP / fixture

`QWEN_MODEL_BACKEND=mlx`는 `QWEN_UPSTREAM_URL`의 Mac HTTP를 호출한다.
`fixture`는 결정적 개발용이다. Controller의 `QWEN_BACKEND=fixture|http`와 서버 내부
설정은 별개다. direct는 Mac 직접 호출, proxy/integration은 우리 서버를 경유한다.
[계약](../../docs/CONTRACTS.md), [모델 파일 가이드](../../models/README.md).

## 선택적 Qwen CLI 어댑터

`QWEN_MODEL_BACKEND=qwen_cli`만 `common.backends.ExecuTorchBackend`를 사용한다.
기존 `executorch` 보드 설정을 이 CLI로 바꾸지 않는다. 호환 Qwen3 `.pte`, tokenizer,
runner를 별도로 확보한 경우 `QNN_LLAMA_RUNNER`, `QWEN_MODEL_PATH`,
`QWEN_TOKENIZER_PATH`, `QWEN_SEQ_LEN`을 지정한다. 현재 보드 Gemma의 경로가 아니다.

Qwen CLI는 매 요청 프로세스를 실행한다. ChatML과 non-thinking prefix, qwen3 decoder,
temperature, total seq_len, output_path를 전달하고 출력 파일을 읽는다. seq_len은
입력+출력 전체 한도이며 max_completion_tokens는 강제하지 않는다. timeout/cancellation은
child를 종료·회수한다. 실제 Qwen 보드 모델·template·NPU 동작은 미검증이며 process
double로 계약을 검사한다. [QC guide](../../qc-executorch-guide/IoT/README.md#part-4-run-qwen-06b).
