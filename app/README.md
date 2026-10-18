# Controller

`create_app` in [`server.py`](server.py) serves HTTP/WS/UI.

| File | Responsibility |
| --- | --- |
| `controller.py` | Policy, state transitions, request edits, confirmation, cancellation, invalidating late results |
| `clients.py` | Vision/STT/LLM fixture and HTTP clients |
| `language.py` | English product prompts, strict intent/item parser |
| `media.py`, `audio.py` | Single video input, board recording |
| `capture.py` | Manual/auto capture, stability, frame selection |
| `events.py` | detected/requested history |
| `hardware/`, `ui/` | Hardware boundary, browser UI |

[Running](../README.md), [Auto capture](../docs/AUTO_CAPTURE.md), [API](../docs/CONTRACTS.md).
