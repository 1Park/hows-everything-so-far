# 보드 LLM 상주 실행

Qwen 서비스의 `executorch` backend는 주최 측 번들의 **`qnn_llm_runner_host`**를 자식 프로세스로 유지한다. FastAPI 프로세스만 살아 있는 것이 아니라 모델 가중치와 QNN context가 실제로 상주한다. 별도 SDK 교체·재빌드는 필요 없다.

## 동작

- 서버 시작: 생성 요청 없이 Gemma4를 로드하고 worker ready 신호를 기다린다. 로드 실패 또는 120초 timeout이면 서버 시작도 실패하며 child를 정리한다. 첫 요청부터 **동일 worker PID**를 재사용한다. `/ready`는 로드된 worker가 살아 있을 때만 true다.
- 다른 모델 요청: 현재 worker를 종료·회수한 후 새 모델을 로드한다. 한 번에 LLM 모델 하나만 상주시킨다. Vision 프로세스는 건드리지 않는다.
- 요청마다 anonymous session으로 KV cache를 초기화한다. 모델 재사용과 대화 기록 재사용은 별개이며 이전 고객 발화가 이어지지 않는다.
- `temperature`, `max_completion_tokens`를 worker에 전달한다. JSON 파싱·제품 정책은 기존 Controller 담당이다.
- 요청은 직렬 처리하며 기존 bounded queue·전체 timeout을 유지한다. 취소/timeout·worker 오류·깨진 protocol은 worker를 종료한다. 다음 요청은 다시 로드한다. fixture나 일회성 runner로 자동 대체하지 않는다.
- 서비스 종료 시 상주 worker도 회수한다. 서버가 살아 있는 동안에는 idle unload를 하지 않는다.

## 모델 선택

현재 `.env.board`는 `QWEN_MODEL=gemma4`로 고정한다. Gemma3 모델과 명시 실행 코드는 유지하지만 자동 평가에서는 제외하며 `auto`를 사용하지 않는다. 기존 별칭 ID로 요청하는 경우에는 `bash scripts/board_llm.sh use gemma4`의 선택을 따른다. 서버 시작 모델은 항상 Gemma4다.

API의 `model`에 **`gemma4` 또는 `gemma3`**를 보내면 그 요청이 모델을 명시적으로 선택한다. 이어서 같은 ID를 보내면 계속 재사용한다. 이 요청은 `llm_selected` 파일을 변경하지 않는다. 다시 기본 ID로 요청하면 파일의 선택으로 돌아간다. `GET /v1/models`에 지원 ID를 표시한다.

`auto`는 처음 로드할 때 모델을 정하고 상주 중에는 고정한다. 모델 자체가 사용하는 메모리 때문에 다음 요청에서 다른 모델로 반복 전환하지 않는다. 명시 선택 변경·worker 재시작 시 다시 결정한다. 데모 권장은 **gemma4**이며 Gemma3는 제품 JSON 정확도가 낮은 사례가 있다.

```sh
bash scripts/board_llm.sh use gemma4
curl -s http://127.0.0.1:8000/ready
# runner.resident / runner.llm / runner.pid 확인

# Model API diagnostic only; does not approve Controller/hardware actions.
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"gemma4","messages":[{"role":"user","content":"Reply with hello."}],"temperature":0,"max_completion_tokens":32}'
```

`/ready`는 모델·tokenizer·worker 파일의 준비 여부를 확인한다. 최초 생성 전 `runner.resident=false`는 정상이다. 실제 로딩 성공은 첫 생성 응답과 `resident=true`로 확인한다. 기존 `model` 필드는 API 호환 ID일 수 있으므로 실제 모델은 **`runner.llm`**을 본다.

기본 worker는 확인된 번들 경로 `$EXECUTORCH_ROOT/examples/qualcomm/oss_scripts/llama/qnn_llm_runner_host` (`EXECUTORCH_ROOT` 기본 `~/git/executorch`). 경로가 다르면 `QNN_LLM_WORKER`로 지정한다. 파일이 없으면 명시적으로 not-ready를 반환한다. `LD_LIBRARY_PATH`/`ADSP_LIBRARY_PATH`는 기존 보드 스크립트와 동일하게 전달한다.

`scripts/board_llm.sh ask`는 수동 진단용 **일회성 CLI**로 유지된다. HTTP 서비스의 상주 worker와 다르므로 반복 성능을 잴 때 혼동하지 않는다.

## 검증

2026-10-17 QCVENTUNO002의 별도 localhost:8010 QA 서버에서 실제 QCS8275 Gemma4 worker를 검증했다. 기존 Controller/Vision/STT/LLM 서버는 유지했고 QA 서버와 worker는 종료했다.

- Gemma4 첫 호출 **4.505초**(load 2.895초), 후속 두 호출 **1.569초 / 1.569초**, 동일 worker PID.
- `A small coffee instead, please.` → coffee/small, `No thanks.` → decline, 다시 coffee/small. 제품 JSON 검증 통과, 매 요청 session reset=new.
- 선택 파일 gemma4→gemma3→gemma4 전환 시 PID 교체 확인. Gemma3는 `No thanks.`에 제품 schema 대신 입력 JSON을 반환했다. 모델 전환 기능 성공과 모델 정확도는 별개다.
- API `model=gemma3|gemma4` 직접 전환도 별도 실행에서 검증했다: Gemma4 첫 호출 5.606초, 재사용 1.863/1.881초, Gemma3 전환 4.418초, Gemma4 복귀 5.272초. raw 응답은 [검증 기록](qwen_evaluation/resident-worker-20261017.json)에 보존한다. 소수 smoke 요청이며 음료 평가셋 전체 결과가 아니다.
- 로컬 real-child-process 테스트: 동일 PID 재사용·요청 격리·선택 변경·직접 model ID 전환·동시 요청 직렬화·worker crash/깨진 응답·취소 후 회수/재시작·API 종료 정리. 이 테스트의 child는 가짜 모델이며 실제 보드 성능 근거가 아니다.

성능은 당시 보드 부하와 입력에 따라 달라지며 이후 모든 요청의 지연을 보장하지 않는다. 상주 모델은 idle 중에도 메모리를 사용한다.
