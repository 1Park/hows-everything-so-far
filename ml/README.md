# ML — training, evaluation, export

모델을 **만드는 환경**을 둔다. 보드에서 모델을 **실행하는 서버**는 `services/`에 있다. 앱의 Docker 없는 배포와 별개로, 주최 측이 요구하는 Linux Docker 학습·QNN export 환경은 이 폴더에서 관리한다.

| 위치 | 넣을 내용 |
| --- | --- |
| `Dockerfile` (예정) | 주최 측 지원 이미지·ExecuTorch commit·QAIRT/QNN SDK에 맞춘 모델 개발 환경 |
| `requirements.txt` 또는 ML 전용 manifest (예정) | 앱과 분리한 학습·양자화·export 의존성 |
| [configs/](configs/README.md) | 모델·데이터·학습·전처리·양자화·export 설정 |
| [training/](training/README.md) | 모델 head·학습·fine-tuning·checkpoint 생성 |
| [evaluation/](evaluation/README.md) | 이미지 모델 오프라인 평가·변환 전후 비교 |
| [export/](export/README.md) | 보드용 `.pte` 변환·검증·bundle metadata 생성 |

Dockerfile·의존성 manifest와 실행 코드는 아직 없다. 주최 측 이미지·SDK·CPU 아키텍처를 확인한 후 작성한다. 학습과 export의 지원 환경은 서로 다를 수 있고, Docker만 설치했다고 Linux x86-64 도구와 ARM 호스트가 자동으로 호환되는 것은 아니다.

```text
data/ 원본·라벨 → training → models/ checkpoint
                          → evaluation
                          → export / 양자화 → models/ 배포 bundle
                                                ↓
                            services/에서 ExecuTorch로 추론
```

우선 사용할 모델은 DINOv2와 Qwen3-0.6B다. 제공 `.pte`를 그대로 쓸 수 있으면 재학습·재export를 필수 작업으로 만들지 않는다. 검출 모델·DINO head/후처리·미세조정 범위는 미정이다. 새 모델 계열로 바꾸는 폴더가 아니라 필요한 조정·검증과 재현을 위한 공간이다.

데이터는 `data/`, 가중치·산출물은 `models/`에 저장하고 Git에서 제외한다. 재현에 필요한 설정·획득 방법·모델 버전·데이터 split 정보는 코드와 함께 기록한다. 배포 bundle에는 모델·필요한 tokenizer 외에도 입력 shape/dtype/layout, 전처리·라벨, 출력 규격, 모델 출처, runtime·SDK 버전, target SoC·export 설정을 포함한다.

보드 서버는 이 폴더의 학습 환경을 import하거나 학습용 Docker를 실행하지 않는다. 기존 Qwen 발화 평가 기록은 `docs/qwen_evaluation/`에 보존하며 음료 평가를 추가할 때는 기존 결과와 구분한다.
