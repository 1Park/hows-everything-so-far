# API 경계

스키마는 [`common/contracts.py`](../common/contracts.py), 설정은 [`common/config.py`](../common/config.py)가 기준이다. 상세 필드·제한·오류 응답은 실행 중 각 서비스 `/docs`와 `/openapi.json`을 확인한다.

## 식별자·이미지·요청

- `scene_id`는 분석 이미지 하나, `object_id`는 그 장면 안의 객체다. 장면 사이 추적 ID가 아니다. `session_id`는 고객 응대, 카드 `request_id/revision`은 요청과 수정 버전이다.
- bbox는 **원본 전체 이미지 기준 normalized xyxy [0,1]**, 좌상단 원점이다. Controller가 원본을 보관하고 Vision이 같은 좌표계로 반환한다.
- 관찰 item은 water/coke/coffee/unknown, 요청 item은 water/coke/coffee다. `fill_ratio`, `item_confidence`는 null일 수 있다. `confidence`와 `item_confidence`는 각각 종합·음료 종류 확신도다.
- 요청·카드·LLM 출력에는 분량이 없다. 관찰 음료와 다른 음료로 요청을 수정해도 대상 객체는 유지한다.
- 한 번에 한 대상·요청만 처리한다. Confirm은 현재 카드의 scene/object/request/revision이 모두 일치해야 한다. 제안·STT·LLM 결과만으로 하드웨어를 승인하지 않는다.

## 서비스 API

| 서비스 | 입력 | 출력 |
| --- | --- | --- |
| Vision `POST /v1/analyze` | multipart `file` JPEG/PNG, `scene_id`, `scenario`(fixture용) | `VisionResult`: scene_id/source/objects |
| STT `POST /v1/transcribe` | multipart audio `file` | text/language/source |
| LLM `POST /v1/chat/completions` | `Generation`: model/messages/생성 옵션 | choices[0].message.content/source, 보드 runner 통계 |

Vision/STT 모델 서버는 카메라·마이크를 열지 않는다. Controller가 이미지·오디오 bytes를 전달한다. 지원 MIME·크기 검사는 [`common/media.py`](../common/media.py), 실제 전처리는 서비스 backend에 있다.

LLM 제품 프롬프트·파서는 [`app/language.py`](../app/language.py)에 있다. 출력은 `{"intent":"refill","item":"water"}` 형태이며 intent는 refill/decline/cancel/not_understood다. refill은 유효 item 필수, 나머지는 item=null이다. 단일 JSON Markdown fence는 허용하지만 prose 추출·추가 필드·중복 키·필드 보정은 허용하지 않는다.

외부 Vision/STT plugin은 `*_MODEL_BACKEND=external`, `*_ADAPTER=package:create_backend`로 선택한다. 인자 없는 factory를 한 번 호출하며 backend는 다음 async 메서드를 제공한다. 반환값은 공통 타입 또는 같은 shape dict다.

```python
async def ready(self) -> bool: ...
async def infer(self, data, content_type, scene_id, scenario): ...  # Vision
async def infer(self, data, content_type): ...  # STT
async def close(self): ...  # 선택
```

별도 HTTP 서버 연결은 Controller의 `VISION_BACKEND=http`/`VISION_BASE_URL`과 STT 대응 설정을 사용한다. `source=fixture|external`을 실제 backend와 일치시킨다. LLM은 mlx/fixture/executorch source를 사용한다. 자동 fixture 전환은 없다.

`/health`는 프로세스 생존, `/ready`는 backend 준비 상태(미준비503)다. 준비 상태가 생성 정확도를 보장하지는 않는다. 추론은 bounded queue와 timeout을 적용하며 기본값은 Settings를 따른다. 공통 오류는 `{error: {code,message,request_id,retryable}}`이고 `X-Request-ID`는 카드 ID와 별도의 호출 추적 ID다.

## Controller

| 경로 | 용도 |
| --- | --- |
| `GET /api/state` | 전체 `StateSnapshot` |
| `GET/POST /api/capture` | 자동/수동 모드·진행 상태, POST `{mode}` |
| `POST /api/observe` | multipart 선택 이미지·scenario로 관찰 시작 |
| `POST /api/utterance` | scene_id/object_id/utterance로 요청 해석 |
| `POST /api/voice/listen` | 안내 종료 ACK: session_id/scene_id/object_id/sequence |
| `POST /api/transcribe` | 업로드 오디오 전사만 수행 |
| `POST /api/confirm` | scene_id/object_id/request_id/revision으로 현재 카드 확인 |
| `POST /api/cancel` | session_id로 현재 작업 취소 |
| `GET /api/frame`, `/api/video` | 최신 이미지·설정 FPS의 MJPEG |
| `GET /api/snapshot/{session_id}` | 분석에 사용한 고정 이미지 |
| `GET /api/hardware`, `/api/events` | 하드웨어 상태·대시보드 이력 |
| `/api/stt/*` | `/stt` 정확도 측정·결과 저장 도구; 상세는 OpenAPI |
| `WS /ws` | 초기 전체 상태·변경 이벤트·heartbeat·capture 이벤트 |

state 이벤트는 `{type:"state",version:1,sequence,state}`이며 서버 실행별 `state.instance_id`와 단조 증가 sequence로 오래된 REST/WS 응답을 무시한다. 재연결은 전체 snapshot으로 복구한다. capture 이벤트는 `{type:"capture",instance_id,capture}`와 별도 `capture.revision`을 사용한다. [자동 캡처](AUTO_CAPTURE.md).

phase 전체 목록은 코드의 `Phase` 타입, 허용 전이는 Controller 메서드를 따른다. 보드 음성 흐름은 offered → listening → transcribing → interpreting → card이며, not_understood는 재입력을 기다린다. [음성 흐름](TABLET_DEMO.md).
