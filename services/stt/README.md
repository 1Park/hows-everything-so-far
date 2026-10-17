# STT 서비스 레이어

`server.py:create_app`, 기본127.0.0.1:8002, POST /v1/transcribe. 브라우저 WAV/WebM/Ogg/MP4 원본을 검증·전달하고 영어 전사를 반환한다. 모델·오디오 전처리/resampling은 담당자 소유다.

기본 fixture는 모든 입력에 A little water, please를 반환하고 source=fixture로 표시한다. `STT_MODEL_BACKEND=external`, `STT_ADAPTER=package:create_backend` 또는 별도 HTTP 서버를 사용한다. [계약](../../docs/CONTRACTS.md). WebM/Opus, Safari MP4/AAC 지원은 담당자와 확인한다. 마이크는 태블릿 브라우저만 소유한다.
