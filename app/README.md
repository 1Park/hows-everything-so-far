# Controller

[`server.py`](server.py)의 `create_app`이 HTTP/WS/UI를 제공한다.

| 파일 | 책임 |
| --- | --- |
| `controller.py` | 정책·상태 전이·요청 수정·확인·취소·늦은 결과 무효화 |
| `clients.py` | Vision/STT/LLM fixture·HTTP 클라이언트 |
| `language.py` | 영어 제품 프롬프트·strict intent/item 파서 |
| `media.py`, `audio.py` | 단일 영상 입력·보드 녹음 |
| `capture.py` | 수동/자동 캡처·안정성·프레임 선택 |
| `events.py` | detected/requested 이력 |
| `hardware/`, `ui/` | 하드웨어 경계·브라우저 UI |

[실행](../README.md), [자동 캡처](../docs/AUTO_CAPTURE.md), [API](../docs/CONTRACTS.md).
