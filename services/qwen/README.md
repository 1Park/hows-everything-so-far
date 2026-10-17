# Qwen 생성 서버

`server.py:create_app`, 기본127.0.0.1:8000. POST /v1/chat/completions, GET /v1/models, /health, /ready. model/messages/생성 옵션 검증, admitted4/동시1 queue, queue+실행 timeout20초, 요청 ID/log 제공.

QWEN_MODEL_BACKEND=mlx는 QWEN_UPSTREAM_URL(기본 Mac)로 HTTP 생성, fixture는 결정적 개발용, executorch는 실제 board adapter 미연결을 명시적으로503 반환. 자동 fixture fallback 없음. .env.board의 executorch readiness503은 보드 전 상태를 정확히 나타낸다.

Controller의 QWEN_BACKEND=fixture/http는 서버 내부 backend 설정과 별개다. direct 모드는 실제 Mac 직접 호출, proxy/integration은 우리 서버→Mac. 제품 프롬프트/JSON 검증/메뉴/승인은 app/language.py와 Controller. [계약](../../docs/CONTRACTS.md).

파일 기반 runtime을 연결하기 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. QWEN_MODEL은 API model ID이며 QWEN_MODEL_PATH와 다른 개념이다. 현재 mlx backend는 HTTP client이고, models/local 또는 models/board의 가중치를 직접 읽지 않는다. 실제 runtime 연결 시 필요한 경로 설정만 추가한다.

## 보드 ExecuTorch (Gemma)

`QWEN_MODEL_BACKEND=executorch`는 보드의 `qnn_llama_runner`를 요청마다 실행한다(`common/backends.py:ExecuTorchBackend`). system 메시지는 `--system_prompt`, user 메시지는 `--prompt`로 전달하고, runner가 `--decoder_model_version`에 맞는 chat template을 적용한다. `--output_path` transcript에서 마지막 model 턴만 반환한다. timeout/취소 시 runner 프로세스를 종료한다. 경로 미설정·파일 없음·실행 권한 없음이면 ready=False(503), fixture/원격 대체 없음.

| 설정 | 의미 |
| --- | --- |
| `QWEN_RUNNER_BIN` | `qnn_llama_runner` (Linux aarch64 빌드) |
| `QWEN_MODEL_PATH` / `QWEN_TOKENIZER_PATH` | `.pte`와 같은 번들의 `tokenizer.json` |
| `QWEN_DECODER_VERSION` | runner `--decoder_model_version` (기본 `gemma4`, Gemma 3는 `gemma3`) |
| `QWEN_SEQ_LEN` | 프롬프트+출력 토큰 상한 (기본 1024, `.pte` context 이하) |
| `QWEN_EVAL_MODE` | 비우면 runner 기본값, 필요 시 `--eval_mode` 값 |
| `QWEN_RUNNER_LIBRARY_PATH` | runner `LD_LIBRARY_PATH` 앞에 추가 (`libqnn_executorch_backend.so`, `libQnnHtp.so`) |
| `QWEN_ADSP_LIBRARY_PATH` | runner `ADSP_LIBRARY_PATH` (`libQnnHtpV75Skel.so`) |
| `QWEN_MODEL` | API model ID (`gemma4-e2b` 등). Controller와 같은 값 |

`.env.board` 기본은 Gemma 4 E2B(`~/model_output/gemma4_e2b`). 매 요청 모델 로드 + 프롬프트 prefill 시간이 있으므로 `INFERENCE_TIMEOUT=120`. 실제 지연·정확도는 보드에서 `scripts/evaluate_qwen.py`로 재측정한다.
