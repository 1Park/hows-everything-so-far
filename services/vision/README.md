# Vision 서비스 레이어

`server.py:create_app`, 기본127.0.0.1:8001, POST /v1/analyze. JPEG/PNG 원본→객체별 결과. fixture JSON은 fixtures/vision.json이며 임의 bbox/점수임을 표시한다.

검출/crop/DINOv2·모델 전후처리는 다른 팀원 소유다. `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=package:create_backend` 또는 별도 HTTP 서버를 연결한다. [정확한 async/HTTP 계약](../../docs/CONTRACTS.md). Controller의 VideoSource가 카메라를 열므로 이 backend는 카메라를 다시 열지 않는다.

실제 모델 연결 전에 [모델 파일·설정 가이드](../../models/README.md)를 읽는다. 로컬/보드 파일 배치와 VISION_MODEL_PATH는 담당 backend를 구현할 때 연결하며, 현재 파일 로더가 준비됐다고 가정하지 않는다.


## Native DINOv2 runner integration

`common.executorch.DinoRunner(QNN_RUNNER, VISION_MODEL_PATH, timeout)` invokes
qnn_executor_runner with one sample's input list and isolated output directory.
`await runner.infer([tensor_bytes, ...])` returns `{relative_raw_path: bytes}`.
The Vision owner supplies exact prepared tensors and interprets raw outputs inside
the existing external adapter. No detection/crop/normalization/dtype/layout/labels
are invented. This helper is not itself a complete Vision backend.

Set QNN_RUNNER and VISION_MODEL_PATH to actual bundle files. Relative paths resolve
against repository root. QNN/HTP library setup follows the supplied image.
Each call reloads the model; calls on an instance serialize. Timeout/cancellation
kills and reaps the child, without fixture fallback.

```bash
python scripts/dino_smoke.py --env-file .env.board --output logs/dino-first /actual/bundle/sample.raw
```

Output directory must be new. Multiple tensor arguments are inputs to ONE sample.
Compare raw tensors with bundle reference outputs before claiming correctness.
[QC DINO guide](../../qc-executorch-guide/IoT/README.md#part-3-run-and-evaluate-dinov2).
Locally tested with a child-process double only. Actual board inference, model
preprocessing/labels and NPU delegation remain unverified.

## DINOv2 backend (`backend.py`)

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
| `VISION_RUNNER_BIN` | bundle이 `cli` runner일 때만 — 보드 `qnn_executor_runner` 경로 |

- 흐름: 이미지 bytes → 컵 박스 (`boxes.mode`: `yolo` .pte / 고정 `rois` / `center`) → crop (`yolo`는 기본 `crop_mode: pad` = 박스×1.15 + 회색 패딩) → DINOv2 .pte → head → `item`·`fill_ratio`·`confidence`·`item_confidence` ([labels.py](labels.py)).
- head에 `other` 클래스(캔·병)가 있으면 p(other) ≥ 0.5인 박스는 결과에서 뺀다. object_id는 남은 컵 기준으로 다시 매긴다.
- YOLO 모드 head는 추론과 같은 crop으로 학습한다 (`ml/training/make_crops.py` → `make_head --data data/crops`). 보드 배포 bundle: `models/board/vision/dinov2-qnn-v4c` (물 full/mid/low 포함, 클래스 11개).
- runner: `py` = `executorch.runtime` (모델 1회 로드 후 재사용, torch 필요) / `cli` = `qnn_executor_runner` 규칙(`input_list.txt` 한 줄=1회, `outputs/output_{i}_0.raw`), 컵 N개를 1회 실행으로 묶음. 보드에 Python 바인딩이 있는지 먼저 확인.
- 의존성: numpy + Pillow (OpenCV·ultralytics 불필요). 추론은 전용 스레드 1개에서 직렬 실행.
- bundle 없음·로드 실패 → `/ready` 503, `/v1/analyze` 503 `vision_not_ready`. fixture 자동 전환 없음.
- 카메라는 열지 않는다 (Controller VideoSource 소유). object_id는 장면 안에서만 유일 (`cup-0`… 왼쪽부터).
- 검증: `tests/test_vision_backend.py` (가짜 runner로 계약·오류 경로), Mac XNNPACK bundle로 실제 HTTP 6장면 → [평가 기록](../../docs/vision_evaluation/README.md).
