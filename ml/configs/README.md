# ML configs

학습·평가·export 재현에 필요한 작은 설정 파일을 커밋한다. 파일 형식과 loader는 구현 시 정한다.

- 모델 ID·가중치 버전·학습할 head 또는 layer
- dataset 위치·라벨 목록·train/validation/test split과 seed
- 입력 크기·정규화·색상·dtype/layout 등 전처리 규격
- 학습 hyperparameter와 양자화 calibration 설정
- QCS8275 target·ExecuTorch/SDK 버전·export 옵션

데이터·SDK·비밀값을 넣지 않는다. 개인 절대 경로는 로컬 환경 설정으로 주입한다. 배포 시 필요한 전처리·라벨·출력 규격은 bundle metadata에도 포함한다.
