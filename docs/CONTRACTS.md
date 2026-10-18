# API boundaries

The schema in [`common/contracts.py`](../common/contracts.py) and the settings in [`common/config.py`](../common/config.py) are the source of truth. For detailed fields, limits, and error responses, check each running service's `/docs` and `/openapi.json`.

## Identifiers, images, and requests

- `scene_id` is one analyzed image, and `object_id` is an object within that scene. It is not a tracking ID across scenes. `session_id` is one customer interaction, and the card's `request_id/revision` is the request and its edit version.
- Bboxes are **normalized xyxy [0,1] relative to the full original image**, with the origin at the top left. The Controller keeps the original, and Vision returns results in the same coordinate system.
- Observed items are water/coke/coffee/unknown; request items are water/coke/coffee. `fill_ratio` and `item_confidence` may be null. `confidence` and `item_confidence` are the overall confidence and the drink-class confidence, respectively.
- The DINO backend sums the coffee/coke probabilities and returns the representative observed item `coke`. In this case `item_confidence` is the group confidence. Fixtures and separate adapters may use the existing observation enum.
- `allowed_items` in the state is the request menu expanded from the observation groups across the whole frozen scene. The coke group allows coke/coffee, and unknown adds no menu items. The LLM input carries `current_request`, `allowed_items`, and `utterance`, and the Controller also blocks refills outside the list.
- `targets` holds all eligible cups in the frozen scene. The legacy `target` and card `object_id` anchor the session/ACK/Confirm identity. Card `selections` is the authoritative list of selected cup IDs and requested drinks; repeated drinks retain separate IDs.
- One batch request is handled at a time. Confirm requires the current card's scene/object/request/revision to match when `REQUIRE_CONFIRMATION=true`; otherwise an understood request starts the existing simulated sequence. No new physical motion is implemented.

## Service APIs

| Service | Input | Output |
| --- | --- | --- |
| Vision `POST /v1/analyze` | multipart `file` JPEG/PNG, `scene_id`, `scenario` (for fixtures) | `VisionResult`: scene_id/source/objects |
| STT `POST /v1/transcribe` | multipart audio `file` | text/language/source |
| LLM `POST /v1/chat/completions` | `Generation`: model/messages/generation options | choices[0].message.content/source, board runner stats |

The Vision/STT model servers do not open the camera or microphone. The Controller passes image and audio bytes. Supported MIME and size checks are in [`common/media.py`](../common/media.py); the actual preprocessing is in each service backend.

The product prompt and parser are in [`app/language.py`](../app/language.py). Cup-aware output is `{"intent":"refill","selections":[{"object_id":"cup-0","item":"water"}]}`. Other intents have an empty selections array. The Controller rejects IDs outside the frozen offer and drinks outside each cup's allowed list. Legacy `{intent,item}` output remains supported for single-cup callers, but cannot approve a multi-cup offer. A single JSON Markdown fence is allowed; prose extraction, extra fields, duplicate keys, and duplicate cup IDs are rejected. See [multi-cup requests](MULTI_CUP.md).

External Vision/STT plugins are selected with `*_MODEL_BACKEND=external` and `*_ADAPTER=package:create_backend`. The no-argument factory is called once, and the backend provides the following async methods. Return values are the common types or dicts of the same shape.

```python
async def ready(self) -> bool: ...
async def infer(self, data, content_type, scene_id, scenario): ...  # Vision
async def infer(self, data, content_type): ...  # STT
async def close(self): ...  # optional
```

Connecting to a separate HTTP server uses the Controller's `VISION_BACKEND=http`/`VISION_BASE_URL` and the corresponding STT settings. `source=fixture|external` must match the actual backend. The LLM uses the mlx/fixture/executorch sources. There is no automatic switch to fixtures.

`/health` is process liveness, and `/ready` is backend readiness (503 when not ready). Readiness does not guarantee generation accuracy. Inference uses a bounded queue and timeout, with defaults from Settings. The common error is `{error: {code,message,request_id,retryable}}`, and `X-Request-ID` is a call tracing ID separate from the card ID.

## Controller

| Route | Purpose |
| --- | --- |
| `GET /api/state` | Full `StateSnapshot` |
| `GET /api/vision-categories` | Fixed groups/member mapping, editable=false; no edit API |
| `POST /api/demo-features` | `{untrained_categories: boolean}` → full state. Default false; 409 when changed mid-flow |
| `GET/POST /api/capture` | Automatic/manual mode and progress, POST `{mode}` |
| `POST /api/capture/restart-timer` | `{enabled,seconds}` sets automatic restart after serving ends |
| `POST /api/observe` | Starts observation with an optional multipart image and scenario |
| `POST /api/utterance` | Interprets a request from scene_id/object_id/utterance |
| `POST /api/voice/listen` | Prompt-done ACK: session_id/scene_id/object_id/sequence |
| `POST /api/transcribe` | Transcribes uploaded audio only |
| `POST /api/confirm` | Confirms the current card with scene_id/object_id/request_id/revision |
| `POST /api/cancel` | Cancels the current work by session_id |
| `GET /api/frame`, `/api/video` | Latest image, MJPEG at the configured FPS |
| `GET /api/snapshot/{session_id}` | Frozen image used for analysis |
| `GET /api/hardware`, `/api/events` | Hardware state and dashboard history |
| `/api/stt/*` | `/stt` accuracy measurement and result-saving tool; see OpenAPI for details |
| `WS /ws` | Initial full state, change events, heartbeat, capture events |

The state event is `{type:"state",version:1,sequence,state}`; stale REST/WS responses are ignored using the per-server-run `state.instance_id` and the monotonically increasing sequence. Reconnects recover from the full snapshot. The capture event uses `{type:"capture",instance_id,capture}` and a separate `capture.revision`. [Auto capture](AUTO_CAPTURE.md).

The full phase list follows the `Phase` type in code, and allowed transitions follow the Controller methods. The board voice flow is offered → listening → transcribing → interpreting → card, and not_understood waits for new input. [Voice flow](TABLET_DEMO.md).
