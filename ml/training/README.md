# Head 학습

- `make_crops.py`: YOLO 검출로 추론과 같은 pad crop을 생성한다.
- `make_head.py`: 배포할 DINO `.pte`의 특징으로 scaler + 선형 head를 학습한다. sklearn 또는 numpy 경로를 사용한다.
- `gen_synthetic.py`: 파이프라인 검증용 합성 이미지. 실제 정확도 자료가 아니다.

원본·crop은 `data/`, head·산출물은 `models/`에 둔다. 배포할 `.pte`와 같은 전처리·특징을 사용하고 학습·평가 split을 분리한다. 실행 옵션은 각 모듈 `--help`, 전체 흐름은 [ML 안내](../README.md)를 따른다.
