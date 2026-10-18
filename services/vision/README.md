# Vision

`server.py:create_app`, 기본 localhost:8001, `POST /v1/analyze`.
원본 JPEG/PNG를 받아 객체별 종류·잔량·bbox를 반환한다. 카메라는 Controller만 연다.
fixture 또는 아래 external backend를 명시적으로 선택한다. 자동 fallback은 없다.

## DINOv2 backend (`backend.py`)

### 카테고리 통합

기존 DINO `.pte`와 logistic regression `head.json`은 변경하지 않는다.
softmax 이후 `coffee`와 `coke`의 확률을 합산해 대표 클래스 **`coke`** 로 반환하고,
`water`는 유지한다. 잔량 단계는 합치지 않으며 기존 확률 가중 평균을 유지한다.
음료 신뢰도는 통합한 확률로 계산한다. 따라서 관찰 결과의 `coke`는 커피도 포함한다.
고객이 명시한 coffee 요청 및 메뉴는 그대로 coffee를 사용할 수 있다.
Controller는 현재 frozen scene의 모든 관찰 카테고리를 펼쳐 `allowed_items`를 만든다:
water만 있으면 water, coke 그룹만 있으면 coke/coffee, 둘 다 있으면 세 음료다.
LLM 프롬프트에 이 목록을 전달하고, 모델이 목록 밖 음료를 반환하면 Controller가
`not_understood`로 처리해 확인을 차단한다. UI의 음료 그림 버튼도 같은 목록을 사용한다.
unknown은 선택지를 추가하지 않는다. 고객의 선택은 요청 카드이며 자동 물리 승인이 아니다.

고정 매핑의 원본은 `common/vision_categories.py`, 적용은 `labels.py`에 있다.
Demo tools의 읽기 전용 표시와 `GET /api/vision-categories`가 같은 매핑을 사용한다.
런타임 수정 API는 제공하지 않는다. 이 통합은 DINO backend 후처리에 적용되며
fixture 및 별도 외부 adapter의 결과를 Controller에서 강제로 바꾸지는 않는다.

추가 하위 음료는 Controller의 demo-only 토글로만 활성화한다 (기본 OFF).
water → water/sparkling water/soda, coke → coke/coke zero/coffee이며 DINO head 클래스는
추가하지 않는다. Vision 계약의 관찰 enum과 고객 요청 enum은 분리되어 있다.

```sh
VISION_MODEL_BACKEND=external \
VISION_ADAPTER=services.vision.backend:create_backend \
VISION_MODEL_PATH=models/local/vision/<bundle> \
python -m uvicorn services.vision.server:create_app --factory --host 127.0.0.1 --port 8001
```

설정은 `common.config.Settings`에서 읽는다 — 선택한 env 파일(`.env`, 보드는 `.env.board`)에 적거나 프로세스 환경변수로 덮어쓴다.

| 설정 | 의미 |
|---|---|
| `VISION_MODEL_PATH` | bundle 디렉터리 (`bundle.json`, `.pte`, `head.json`). 상대 경로는 레포 루트 기준. `ml/export/make_bundle.py`가 생성 |
| `VISION_RUNNER_BIN` | 독립 CLI pipeline·학습·진단에서 사용할 `qnn_executor_runner` 경로. 상주 서비스는 `VISION_WORKER_BIN` 사용 |
| `VISION_WORKER_BIN` | 서비스에서 DINO·YOLO를 상주시키는 native worker 경로. CLI bundle을 사용할 때 필수 |

- 흐름: 이미지 bytes → 컵 박스 (`boxes.mode`: `yolo` .pte / 고정 `rois` / `center`) → crop (`yolo`는 기본 `crop_mode: pad` = 박스×1.15 + 회색 패딩) → DINOv2 .pte → head → `item`·`fill_ratio`·`confidence`·`item_confidence` ([labels.py](labels.py)).
- head에 `other` 클래스(캔·병)가 있으면 p(other) ≥ 0.5인 박스는 결과에서 뺀다. object_id는 남은 컵 기준으로 다시 매긴다.
- YOLO 모드 head는 추론과 같은 crop으로 학습한다 (`ml/training/make_crops.py` → `make_head --data data/crops`). 보드 배포 bundle: `models/board/vision/dinov2-qnn-v4c` (물 full/mid/low 포함, 클래스 11개). 아래 지연 비교 기록은 당시 `dinov2-qnn-v3` bundle을 사용했다.
- 서비스는 시작 시 DINO와 YOLO(detector)를 모두 로드하고 준비 신호를 기다린다. 기존 bundle의 `runner=cli`는 서비스 안에서 상주 worker로 연결하며 bundle 파일은 수정하지 않는다. `py`는 Python 런타임 모델을 한 번 로드해 유지한다. 학습·독립 진단의 `CliRunner`는 기존 일회성 동작을 유지한다.
- 의존성: numpy + Pillow (OpenCV·ultralytics 불필요). 추론은 전용 스레드 1개에서 직렬 실행.
- bundle·worker 없음 또는 시작 로드 실패면 서비스 시작에 실패한다. `/ready`는 실제 worker 생존 여부와 `runners.dino/detector`의 resident·PID를 표시한다. 추론 실패·timeout·취소는 해당 worker를 회수하고 ready=false가 되며, 서비스 재시작으로 복구한다. fixture/일회성 CLI 자동 전환 없음.
- 카메라는 열지 않는다 (Controller VideoSource 소유). object_id는 장면 안에서만 유일 (`cup-0`… 왼쪽부터).
- 검증: `tests/test_vision_backend.py` (가짜 runner로 계약·오류 경로), Mac XNNPACK bundle로 실제 HTTP 6장면 → [평가 기록](../../docs/vision_evaluation/README.md).

## 상주 worker 빌드·배포

주최 측 기존 SDK/빌드의 compiler flags와 linked QNN 라이브러리를 사용한다.
SDK 소스와 빌드 디렉터리는 수정하지 않으며, 생성 소스·object·binary·build manifest는
지정한 출력 경로에만 쓴다. SDK에 이미 있는 stdin 확장도 생성 사본에서만 처리한다.
지원하지 않는 소스/빌드 구조는 명시적으로 실패한다.

```sh
python scripts/build_vision_worker.py --sdk "$HOME/git/executorch" \
  --build-dir "$HOME/git/executorch/build-x86" --output-dir /tmp/vision-worker-build
```

실험은 로컬 코드 사본을 `/tmp`에 복사해 실행한다. 정식 배포는 로컬 변경 push 후
배포 절차로 binary를 `models/board/bin/qnn_vision_worker`에 배치하고,
`VISION_WORKER_BIN`을 설정한 뒤 Vision 서비스를 재시작한다. `.env.board`에 경로가
있어도 worker 파일은 따로 빌드·배포해야 한다. 서비스 재시작 없이 기존 프로세스가
상주 방식으로 바뀌지는 않는다.

동작: `--vision_resident=true`로 모델·method·QNN context를 한 번 로드하고,
`VISION_READY` 이후 stdin의 요청별 input-list/output-directory 두 줄을 처리한다.
완료는 `VISION_DONE`으로 동기화한다. 입력·출력 파일은 요청마다 격리하고 검증하며,
ETDump 이벤트 누적은 상주 모드에서 비활성화한다. 원래 QNN 입력/출력 및 연산은 유지한다.

## 변경 전후 지연 비교

```sh
python scripts/benchmark_vision_residency.py --bundle /actual/bundle \
  --cli /actual/qnn_executor_runner --worker /tmp/vision-worker-build/qnn_vision_worker \
  --image /actual/cups.jpg --output /tmp/vision-latency.json --warmups 3 --repetitions 20
```

동일 이미지·bundle로 CLI 23회(워밍업3+측정20), 상주 23회를 순서대로 실행한다.
pipeline 시작 로드 시간과 첫 invoke, 반복 invoke의 중앙값·평균·p95, boxes/DINO 시간을
분리하고 모든 출력의 동등성을 확인한다. HTTP·카메라·네트워크를 제외한 직접 pipeline
wall time이다. OS cold cache/전체 모델 정확도 검증은 아니며 원본 샘플·hash·PID를
새 JSON/Markdown 파일로 남긴다.
