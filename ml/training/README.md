# Training

필요한 경우 DINOv2 기반 head 학습·fine-tuning과 데이터 loader·checkpoint 저장 코드를 둔다. 실제 학습 범위는 아직 미정이며 제공 모델로 충분하면 학습 없이 진행한다.

원본·라벨은 `data/`, 학습 설정은 `ml/configs/`, 가중치·실험 산출물은 `models/`를 사용한다. 실제 데모 컵 사진으로 데이터 split을 관리하고 평가용 이미지를 학습·calibration에 섞지 않는다.

추론 API·카메라·GPIO는 여기서 구현하지 않는다. checkpoint를 `.pte`로 변환하는 과정은 `ml/export/`에서 관리한다.
