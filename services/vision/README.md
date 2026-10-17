# Vision service

기본 bind: `127.0.0.1:8001`. 카메라 입력·영상 스트림과 검출·crop·DINOv2 실행 파이프라인을 둔다. 아직 구현 전이다.

구현할 코드:

- USB 카메라 또는 파일 입력 adapter, 최신 프레임 관리
- 단일 카메라 소유 모듈에서 영상 전송과 분석용 프레임 분기
- 객체 검출 → bounding box → 객체별 crop
- 모델 규격에 맞는 전처리, DINOv2 실행 adapter, 종류·잔량 후처리
- scene·object ID와 bbox·판단 결과를 공통 schema로 반환하는 API
- 로컬 mock model backend, 실제 보드 ExecuTorch backend

검출 모델·DINO 출력 해석·최종 라벨·영상 endpoint는 미정이다. 처음에는 공통 사진으로 API와 전후처리를 개발한다. 영상 전달 방식은 MJPEG 후보이며 UI 연결/프록시 경로는 구현 시 정한다.

모델을 학습하거나 export하는 코드는 `ml/`에 둔다. 서비스는 runtime용 전처리를 직접 소유하되 `ml/`에서 검증한 규격·라벨을 bundle metadata로 공유한다. `models/`의 bundle 경로는 설정으로 전달한다. 다른 프로세스가 같은 카메라를 열지 않도록 한다.
