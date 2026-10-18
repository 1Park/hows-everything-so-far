# 서비스 계약 v1

실제 타입: [`common/contracts.py`](../common/contracts.py). 실행 중 OpenAPI는 각 서버 `/docs`, `/openapi.json`. 모델 내부 tensor·crop·정규화·head·codec 처리는 이 계약이 정의하지 않는다.

## ID·좌표·정책

- scene_id: Controller가 분석 입력마다 UUID 발급, 하나의 고정 원본 이미지에 해당.
- object_id: Vision이 장면 안에서 유일하게 발급. 배열 index의 장기 ID 사용 금지. 장면 사이 동일성 보장 없음.
- session_id: 새 관찰마다 발급. Cancel은 현재 session에만 적용.
- request_id: 첫 유효 요청 카드에서 발급, 수정 시 유지; revision은 수정마다 증가.
- bbox: **원본 전체 이미지 기준 normalized xyxy [0,1], 좌상단 원점**, x1<x2, y1<y2. EXIF 자동 회전 없음. 담당자 adapter가 원본 표시 좌표와 일치시킨다.
- 음료 water/coke/coffee/unknown; fill_ratio 0..1 또는 null; confidence 0..1. 이는 외부 표현이며 모델 내부 라벨 변환은 모델 담당자 책임이다.
- item_confidence 0..1 또는 null(선택): **음료 종류만**의 확신도. confidence는 음료·잔량을 함께 본 값이다. 제공하지 않으면 null.
- 요청 음료 water/coke/coffee. 분량은 요청·카드·LLM 출력에 포함하지 않는다.
- 초기 정책: confidence>=0.7, fill_ratio<=0.3 중 최소 잔량 컵; 동률 object_id 정렬. 환경변수로 변경 가능하며 보드 실측 기준은 아니다.
- 대상이 coke/coffee이고 item_confidence<0.8(`ITEM_CONFIRM_THRESHOLD`)이면 제안 문구에서 음료를 묻는다("Is that coke or coffee?"). 추정 음료로 카드는 만들되 고객이 수정·Confirm한다. 0.8은 Mac 실사 교차검증(콜라·커피 190장) 기준: 17%를 묻고 혼동의 87%를 잡음 — [vision_evaluation](vision_evaluation/README.md).
- 한 번에 한 대상/요청. 제안 자체는 Confirm 불가. 고객 입력→카드→명시 Confirm 필요.
- 관측 음료와 요청 음료는 별개다. 물 컵을 대상으로 coffee 주문 가능; 대상은 유지된다.

## 공통 HTTP

자동 캡처: `GET /api/capture`, `POST /api/capture` (`{"mode":"manual"}` / `{"mode":"auto"}`)는 CaptureStatus를 반환한다. Controller state의 `capture`와 별도 WS `type=capture` 이벤트로 모드/5초 안정성 진행도를 제공한다. 이 이벤트는 요청 sequence를 변경하지 않는다. [프레임 선택·중복 방지·설정](AUTO_CAPTURE.md).

`GET /health`는 프로세스 생존, `/ready`는 backend 가용성(503 가능). Qwen readiness는 모델 목록에 설정 ID가 있는지 검사하며 생성 성공과 구분한다.

```json
{"error":{"code":"stale_confirmation","message":"This request has changed or was already confirmed","request_id":"uuid","retryable":false}}
```

X-Request-ID 생성/전파/응답. validation422, 형식415, 크기413, stale/state409, backend502/503, timeout504. raw transport 최대26MB, 이미지 기본5MB/16M pixels, 오디오 기본10MB. signature·크기 검사는 transport 검증으로 모델 전처리가 아니다. 오디오 codec/길이 검사는 STT 담당자 책임이다.

HTTP 오류의 request_id/X-Request-ID는 호출 추적 ID이며, 요청 카드 request_id(업무 ID)와 별개다. 상태/이벤트도 StateSnapshot/StateEvent/Heartbeat 공통 타입으로 검증하며 Controller OpenAPI에 상태 schema를 노출한다.

## Vision·STT 담당자 연결

Vision `POST /v1/analyze` multipart: file JPEG/PNG 원본 bytes, scene_id, scenario=normal|enough|uncertain (fixture용; external은 무시 가능).

```json
{"scene_id":"s","source":"external","objects":[{"object_id":"cup-a","bbox":{"x1":0.1,"y1":0.2,"x2":0.3,"y2":0.7},"item":"water","fill_ratio":0.15,"confidence":0.9,"item_confidence":0.97}]}
```

STT `POST /v1/transcribe` multipart file. MIME: audio/wav, audio/x-wav, audio/webm, audio/ogg, audio/mp4; codec parameter 허용. 응답 `{"text":"A little water, please","language":"en","source":"external"}`. 보드 마이크 흐름은 STT→Qwen→카드를 자동 생성하고 전사를 UI에 표시한다. STT만으로 동작을 승인하지 않으며 Confirm이 필요하다. 개발용 브라우저 업로드는 전사 검토 후 Send를 유지한다.

Plugin: `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=your_package:create_backend` (STT도 동일). factory는 인자 없이 한 번 실행된다. backend:

```python
async def ready(self) -> bool: ...
# Vision: VisionResult 또는 같은 shape dict
async def infer(self, data: bytes, content_type: str, scene_id: str, scenario: str): ...
# STT: STTResult 또는 같은 shape dict
async def infer(self, data: bytes, content_type: str): ...
async def close(self): ...  # 선택
```

담당자는 blocking 추론을 전용 worker/queue로 분리해 event loop를 막지 않는다. 서비스 기본 admitted4/동시실행1, queue+실행 전체20초 timeout. native 호출 취소/수명은 담당자와 확인한다. 모델 미준비면 ready=False, fixture 자동 전환 금지. 결과 source는 선택한 backend와 일치해야 한다.

별도 팀 서버가 HTTP 계약을 제공하면 Controller `VISION_BACKEND=http`, VISION_BASE_URL 지정(STT 동일). 내부 출력 변환은 담당자 adapter 책임. **검출/crop/DINO 전후처리·오디오 전처리/STT 모델은 이번 구현 범위 밖**이다.

카메라는 **Controller VideoSource 하나**가 소유한다. 원본 capture bytes를 Vision에 전달하고 모델 서버는 같은 카메라를 열지 않는다. 파일 루프/USB는 선택 OpenCV, 모델 resize/정규화 없음. **보드 Controller만 마이크를 열고 태블릿은 스피커를 소유**한다. STT 모델 서버는 마이크를 다시 열지 않는다. 분석 bbox는 고정 snapshot에 겹치고 live preview에는 과거 bbox를 겹치지 않는다.

## Qwen

`POST /v1/chat/completions`: model/messages, temperature0..1(제품·평가0), max_completion_tokens16..512(기본192), stream=false, chat_template_kwargs.enable_thinking=false. 서버는 generic 생성; 프롬프트/strict 파서는 app/language.py.

응답 choices[0].message.content + source mlx/fixture/executorch. 실패 시 fixture 대체 없음. 파서는 intent refill/decline/cancel/not_understood, item 필수키, refill만 허용 음료, 나머지는 item=null. 이해하지 못한 요청은 not_understood로 반환하고 재입력을 요청한다. 단일 Markdown JSON fence만 허용; prose에서 JSON 추출/필드 보정 없음.

## Controller

| 경로 | 입력·결과 |
| --- | --- |
| GET /api/state | 전체 상태·scene/target/card/source/sequence |
| POST /api/observe | multipart scenario, 선택 file; 202 background 분석 |
| POST /api/utterance | JSON scene_id, object_id, utterance; 202 background Qwen |
| POST /api/confirm | JSON scene_id, object_id, request_id, revision; 202 |
| POST /api/cancel | JSON session_id; 현재 작업 무효화/시퀀스 취소 |
| POST /api/transcribe | multipart audio file; STT 결과만 반환 |
| POST /api/voice/listen | 안내 재생 후 `{session_id,scene_id,object_id,sequence}`. 현재 offered/not_understood/error에서만 녹음 시작; 중복/오래된 ACK409. listening→transcribing→interpreting→card, 승인 없음 |
| GET /api/frame, /api/video | 최신 원본·MJPEG5fps |
| GET /api/snapshot/{session_id} | 고정 원본 이미지 |
| GET /api/hardware | simulator/Bridge 입력·상태·명령 ID |
| WS /ws | 초기 전체 상태, 변경 이벤트, 10초 heartbeat |

WS `{type:"state",version:1,sequence:42,state:{...}}`, heartbeat는 type/sequence만. 연결별 큐16, 과거 상태를 버려 최신 전체 상태 유지. 재연결 시 전체 snapshot. 세션 영속화 없음.

state.instance_id는 서버 실행마다 새 UUID, sequence는 같은 서버에서 단조 증가한다. UI는 늦게 도착한 REST/WS 응답의 작은 sequence를 무시한다. 새 서버 instance는 WS의 초기 전체 상태를 통해 수용해 재시작 후에도 복구한다.

phase: idle/observing/offered/interpreting/not_understood/card/loading/returning/done/skipped/declined/cancelled/expired/error. 고객 대기60초. 오류 후 같은 대상 입력 재시도 또는 새 관찰 가능. loading/returning 중 관찰 거부; Cancel 후 다시 시작. generation token+lock으로 오래된 확인·중복 클릭·취소 뒤 늦은 결과·장면 변경 결과를 무효화한다.
