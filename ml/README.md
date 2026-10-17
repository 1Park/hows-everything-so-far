# ML — training, evaluation, export

모델을 **만드는 환경**을 둔다. 보드에서 모델을 **실행하는 서버**는 `services/`에 있다. 앱의 Docker 없는 배포와 별개로, 주최 측이 요구하는 Linux Docker 학습·QNN export 환경은 이 폴더에서 관리한다.

| 위치 | 넣을 내용 |
| --- | --- |
| [`Dockerfile`](Dockerfile), [`docker-run.sh`](docker-run.sh) | x86-64 QNN export·HTP 시뮬레이터 환경 (Mac은 Rosetta). 주최 측 checkout/SDK로 교체 가능 |
| [`requirements.txt`](requirements.txt) | 앱과 분리한 학습·평가·export 의존성 (Mac, Python 3.13) |
| [tools/](tools/) | 카메라 수집·live 확인 (`camera.py`), CLI runner 테스트용 가짜 runner |
| [configs/](configs/README.md) | 모델·데이터·학습·전처리·양자화·export 설정 |
| [training/](training/README.md) | 모델 head·학습·fine-tuning·checkpoint 생성 |
| [evaluation/](evaluation/README.md) | 이미지 모델 오프라인 평가·변환 전후 비교 |
| [export/](export/README.md) | 보드용 `.pte` 변환·검증·bundle metadata 생성 |

학습과 export의 지원 환경은 서로 다를 수 있고, Docker만 설치했다고 Linux x86-64 도구와 ARM 호스트가 자동으로 호환되는 것은 아니다.

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

## 현재 구현 — DINOv2 Vision (2026-10-17)

결과 기록: [docs/vision_evaluation](../docs/vision_evaluation/README.md). 런타임은 [services/vision](../services/vision/README.md).

### 환경

```sh
python3.13 -m venv ml/.venv && ml/.venv/bin/pip install -r ml/requirements.txt   # Mac 학습·평가·XNNPACK export
docker build --platform linux/amd64 -t refill-ml-export ml                          # x86 QNN export·시뮬레이터
```

모든 명령은 레포 루트에서 `python -m ml.<폴더>.<스크립트>`로 실행한다 (`ml/.venv/bin/python`). Docker는 `ml/docker-run.sh python -m ...`.
첫 Docker export 때 ExecuTorch가 QAIRT SDK 2.37(~3GB)과 libc++(~5GB)를 volume `refill-qnn-cache`에 받는다.

### 흐름

| 단계 | 명령 | 산출물 |
|---|---|---|
| 데이터 수집 | `python -m ml.tools.camera collect --drinks water coke coffee` (iTerm/터미널.app — 카메라 권한) | `data/real/<drink>__<level>/` |
| 합성 데이터 | `python -m ml.training.gen_synthetic` | `data/synthetic/` (파이프라인 검증용) |
| 정확도 | `python -m ml.evaluation.eval_fewshot --data data/real --shots 3 5 10` | `models/experiments/vision/fewshot_*.json` |
| 컵 검출 | `python -m ml.evaluation.detect_test` | COCO YOLO가 컵을 잡는지 |
| CPU .pte | `python -m ml.export.export_xnnpack`, YOLO는 ultralytics `format="executorch"` | `models/local/vision/` |
| NPU .pte | `ml/docker-run.sh python -m ml.export.export_qnn --model {yolo,dinov2} [--quant fp16] --soc_model QCS8275 --build_folder /tmp --compile_only` | `models/experiments/vision/qnn/<soc>_<quant>/` |
| NPU 검증 | `ml/docker-run.sh python -m ml.evaluation.qnn_sim_check {yolo,dinov2} <pte>` | HTP 시뮬레이터 출력 vs fp32 |
| head 학습 | `python -m ml.training.make_head --dino-pte <pte> --runner {py,cli}` (**배포할 .pte로**) | head JSON |
| bundle | `python -m ml.export.make_bundle --out models/{local,board}/vision/<name> ...` | `bundle.json` + .pte + head |

### 꼭 지킬 것

- **head는 보드에서 실제로 돌릴 .pte가 낸 특징으로 학습한다.** fp32 head를 양자화 모델에 쓰면 크게 떨어진다 (int8 근사 88.8%→68.2%, QNN 16a8w 24%).
- DINOv2 QNN은 **fp16 우선** (fp32 대비 cosine 0.9992). 16a8w는 0.58, 16a16w는 망가짐.
- 일반 ExecuTorch 1.5.1엔 QCS8275 타깃이 없다. 주최 측 checkout/SDK로 export하고, SM8650(같은 HTP v75) 산출물은 리허설용으로만 쓴다.
- 보드 SDK 버전과 export SDK 버전을 맞춘다 (`QNN_SDK_ROOT_HOST=<qairt> ml/docker-run.sh ...`).
- 입력 텐서는 연속 메모리여야 한다 (stride 0이면 export·raw 입력 실패) — `services/vision/preprocess.py`가 보장.
- HF DINOv2는 그대로 export 안 됨 (위치 임베딩 bicubic 보간, 그래프 안 attention mask expand) → `export_qnn.build_dinov2` 래퍼 사용. YOLO는 640 입력으로 1회 실행해 앵커를 상수화 (`build_yolo`).
