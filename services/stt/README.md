# STT 서비스 레이어

`server.py:create_app`, 기본127.0.0.1:8002, POST /v1/transcribe. 보드 녹음 WAV(개발용 업로드는 WebM/Ogg/MP4도 가능)를 검증·전달하고 영어 전사를 반환한다. 모델·오디오 전처리/resampling은 담당자 소유다.

기본 fixture는 모든 입력에 A little water, please를 반환하고 source=fixture로 표시한다. `STT_MODEL_BACKEND=external`, `STT_ADAPTER=package:create_backend` 또는 별도 HTTP 서버를 사용한다. [계약](../../docs/CONTRACTS.md). **마이크는 보드 Controller만 소유하며 STT 서버는 파일 입력만 받는다.**

기존 whisper.cpp 서버 연결: `STT_ADAPTER=services.stt.whisper_http:create_backend`, `STT_WHISPER_URL=http://127.0.0.1:8178`. `/health`, `/inference` multipart→우리 STT 계약으로만 변환한다. 모델 실행 옵션/프롬프트/전처리를 교체하지 않으며 영어 language와 JSON 응답을 요청한다. 실제 녹음 형식은 담당자 서버가 지원하는 설정을 사용한다. 실패/빈 전사를 fixture로 대체하지 않는다.

실제 모델 연결 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. 로컬/보드 파일 배치와 STT_MODEL_PATH는 담당 backend를 구현할 때 연결하며, 현재 파일 로더가 준비됐다고 가정하지 않는다.
