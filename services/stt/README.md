# STT

`server.py:create_app`, default localhost:8002. `POST /v1/transcribe` takes an audio file and returns English text/language/source. Only the Controller opens the microphone.

- `STT_MODEL_BACKEND=fixture`: fixed sentence, source=fixture.
- `STT_MODEL_BACKEND=external`, `STT_ADAPTER=services.stt.whisper_http:create_backend`: forwards to a separate whisper.cpp server at `STT_WHISPER_URL`. `.env.board` uses localhost:8178.
- [`normalize.py`](normalize.py) normalizes transcript whitespace and some spellings/aliases of supported drinks. An empty transcript is a no_speech error and is not replaced with a fixture.

This adapter does not load model files or open the microphone. Codec support and model lifetime are handled by the external server. [API/plugin contracts](../../docs/CONTRACTS.md), [Voice flow](../../docs/TABLET_DEMO.md), [STT evaluation](../../docs/stt_evaluation/README.md).
