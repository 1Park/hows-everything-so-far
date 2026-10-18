# STT

`server.py:create_app`, 기본 localhost:8002. `POST /v1/transcribe`는 오디오 파일을 받아 영어 text/language/source를 반환한다. 마이크는 Controller만 연다.

- `STT_MODEL_BACKEND=fixture`: 고정 문장, source=fixture.
- `STT_MODEL_BACKEND=external`, `STT_ADAPTER=services.stt.whisper_http:create_backend`: `STT_WHISPER_URL`의 별도 whisper.cpp 서버로 전달한다. `.env.board`는 localhost:8178을 사용한다.
- [`normalize.py`](normalize.py)가 전사 공백·지원 음료의 일부 철자/별칭을 정규화한다. 빈 전사는 no_speech 오류이며 fixture로 대체하지 않는다.

이 adapter는 모델 파일을 로드하거나 마이크를 열지 않는다. codec 지원·모델 수명은 외부 서버가 담당한다. [API/plugin 계약](../../docs/CONTRACTS.md), [음성 흐름](../../docs/TABLET_DEMO.md), [STT 평가](../../docs/stt_evaluation/README.md).
