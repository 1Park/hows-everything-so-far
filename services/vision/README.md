# Vision 서비스 레이어

`server.py:create_app`, 기본127.0.0.1:8001, POST /v1/analyze. JPEG/PNG 원본→객체별 결과. fixture JSON은 fixtures/vision.json이며 임의 bbox/점수임을 표시한다.

검출/crop/DINOv2·모델 전후처리는 다른 팀원 소유다. `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=package:create_backend` 또는 별도 HTTP 서버를 연결한다. [정확한 async/HTTP 계약](../../docs/CONTRACTS.md). Controller의 VideoSource가 카메라를 열므로 이 backend는 카메라를 다시 열지 않는다.

실제 모델 연결 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. 로컬/보드 파일 배치와 VISION_MODEL_PATH는 담당 backend를 구현할 때 연결하며, 현재 파일 로더가 준비됐다고 가정하지 않는다.
