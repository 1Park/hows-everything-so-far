# Vision 평가 기록 — DINOv2 + YOLO11n (로컬 / QNN 시뮬레이터)

기준일: 2026-10-15 ~ 10-17. **Mac(M4)과 x86 Docker HTP 시뮬레이터 결과이며 보드 실측이 아니다.** 보드 수치는 별도로 기록한다. 합성 이미지는 실제 정확도 증거가 아니다.

재현 코드: `ml/` ([ml/README.md](../../ml/README.md)), 런타임: `services/vision/`.

## 구성

```text
원본 이미지 → YOLO11n(COCO, 파인튜닝 없음) 컵 박스 → 박스×1.35 정사각 crop
           → DINOv2-small CLS(384) → StandardScaler + LogisticRegression head
           → item / fill_ratio / confidence (services/vision/labels.py)
```

- DINOv2 가중치는 고정(`facebook/dinov2-small`), 학습하는 것은 head(384×클래스 수)뿐 = linear probe.
- 내부 클래스 `<drink>__<full|mid|low>` + `empty` → 계약 `fill_ratio`는 단계 대표값(0.85/0.5/0.18/0.02)의 확률 기대값.

## Few-shot 정확도 (합성 이미지, Mac fp32)

`python -m ml.evaluation.eval_fewshot --data data/synthetic` — 10클래스, test 200장, logreg.

| 음료 조합 | shots/class | joint | fill | drink |
|---|---:|---:|---:|---:|
| **water / coke / coffee** (현재 데모) | 5 | 60.2% | 67.8% | 84.6% |
| | 10 | 74.5% | 78.6% | 90.7% |
| | 20 | **83.0%** | 86.0% | **93.3%** |
| cola / orange juice / water (이전 실험) | 20 | 90.0% | 91.5% | 96.7% |

- **coke ↔ coffee 혼동이 주 오류** (20-shot에서 어두운 음료 60장 중 5~8장). 합성에선 coke=반투명+기포+거품, coffee=불투명+크레마로만 구분 → 실사에서 반드시 확인.
- CLS 단독 + 표준화가 가장 좋았음 (CLS+patch-mean, 세로 띠 patch pooling보다 높음). 표준화 없으면 크게 하락.
- dinov2-small ≥ dinov2-base (같거나 더 정확, 4배 가벼움).

## 실사 (MacBook 카메라, 2클래스: coke__full 11 / water__full 60)

| 학습 → 테스트 | 결과 |
|---|---|
| 실사 3-shot → 실사 | 100% (water 60장 대부분 연속 프레임이라 낙관적) |
| 합성만 → 실사 | 음료 종류 91~98%, **잔량은 실패** (잔 모양 차이) → 잔량은 실사 몇 장 필요 |

## 컵 검출 (COCO YOLO11n, 파인튜닝 없음)

- 실사 jar 71장 중 69장(97%) 검출. 클래스 이름은 vase 41 / cup 26 / bowl 2 → 이름 대신 컵류 클래스 묶음 사용.
- `agnostic NMS` 필수 (같은 컵 cup+vase 이중 박스). 2~3잔 합성 장면에서 박스 수 = 컵 수 11/12.

## Vision 서비스 end-to-end (Mac, XNNPACK .pte)

`services.vision.backend:create_backend` + bundle `dinov2-xnnpack-yolo` (YOLO·DINOv2 모두 XNNPACK fp32, head=실사 2클래스).
실사 crop 3장을 1280×720에 배치한 장면 6장 → `POST /v1/analyze`:

- 응답 전부 `VisionResult` 검증 통과, 컵 3개 잡힌 장면의 item 9/9 정답
- 컵 수 불일치 3/6은 원본 사진 배경에 실제로 찍힌 다른 잔 (+1장은 1개 누락)
- HTTP 지연 p50 102 ms (Mac CPU XNNPACK)

## 지연시간 (Mac M4, batch 1)

| 모델 | CPU 1 thread | CPU 4 threads | MPS | XNNPACK .pte |
|---|---:|---:|---:|---:|
| dinov2-small 224 | 22.7 ms | 17.8 ms | 10.2 ms | 18.6 ms |
| dinov2-base 224 | 66.0 ms | 55.2 ms | 27.0 ms | — |
| YOLO11n 640 | 16.9 ms | — | 9.9 ms | 21~25 ms |

## QNN(HTP) export + 시뮬레이터 (x86 Docker, SM8650 = HTP v75 리허설)

QCS8275도 HTP v75 (Ultralytics QNN 문서, Qualcomm Dragonwing 문서). **일반 ExecuTorch 1.5.1에는 QCS8275 타깃이 없어 SM8650으로 리허설만 함 — 보드 배포용 아님.**

| 모델 | quant | NPU 미지원 op | 시뮬레이터 검증 |
|---|---|---:|---|
| YOLO11n | 16a8w | 0 | fp32 박스 25/27 일치(IoU>0.8), class score max\|diff\| 0.85 |
| DINOv2-small CLS | 16a8w | 0 | **fp32 대비 cosine 0.58** → fp32 head 24%, 재학습 head 54.5% (fp32 61%) |
| DINOv2-small CLS | **fp16** | 0 | **cosine 0.9992**, fp32 head 그대로 사용 가능 |
| DINOv2-small CLS | 16a16w | — | cosine 0.08 (사용 금지) |

- 결론: DINOv2는 **fp16 우선**, 안 되면 16a8w + **보드 .pte 특징으로 head 재학습** (`ml/training/make_head.py`).
- XNNPACK int8 근사에서도 같은 경향: Mac fp32 head를 int8 모델에 쓰면 88.8% → 68.2%.
- 공식 번들 `dino_v2.pte`가 ImageNet 1000 logits여도 특징으로 사용 가능 (합성 10클래스 86.2% vs CLS 88.8%).

## 콜라·커피 애매할 때 묻는 임계값 (2026-10-17, 실사 286장)

`item_confidence` = 음료 확률 합 중 최고 음료의 비중. 콜라·커피 사진 190장, 5-fold × 5 seeds 평균.

| 임계 | 묻는 비율 | 잡는 혼동 | 묻지 않고 틀림 |
|---:|---:|---:|---:|
| 0.7 | 10.3% | 65% | 2.3% |
| **0.8** | **17.3%** | **87%** | **0.8%** |
| 0.9 | 31.6% | 100% | 0% |

혼동 방향: 콜라→커피 8.7% (101장 중 8.8), 커피→콜라 3.1% (89장 중 2.8). 파인트 잔 콜라가 커피와 가장 헷갈림.
라벨 정리(14건, `data/relabel_log.tsv`) 후 종합 89.3%, 리필 판단 precision 98.3% / recall 69.4%.

## 컵이 아닌 물체(캔·병) 걸러내기 (2026-10-17)

COCO YOLO11n은 캔·병도 `cup`으로 잡는다(실측: 노란 탄산수 캔 0.81, 콜라 캔 0.64). 클래스 이름으로는 못 거른다.

- head에 `other` 클래스 추가 (캔·병 28장, `ml.tools.camera collect --classes other`). Vision은 p(other) ≥ 0.5면 결과에서 뺀다
- 교차검증(5-fold × 5 seeds): other 28장 중 95.7% 걸러냄, **컵 286장 중 잘못 걸러냄 0장**, 컵 분류 89.3% 유지
- **crop 방식이 더 중요했다.** 정사각형 ×1.35 확장은 세로로 긴 캔이나 화면 가장자리 물체에서 옆 컵이 crop에 같이 들어가 분류가 옆 물체를 따라갔다(캔 옆 커피잔 → 캔을 coffee로)

| crop (YOLO 모드) | 노란 캔 | 커피 잔 | 빈 잔 | 콜라 캔 | 3컵 장면 |
|---|---|---|---|---|---|
| 정사각형 ×1.35 (이전) | coffee | coffee | empty | empty | 9/9 |
| 정사각형 ×1.0 | other | coffee | coffee_low ✗ | other | 9/9 |
| **회색 패딩 ×1.15 (현재 기본)** | **other** | **coffee** | **empty** | **other** | **9/9** |

`pad_crop`: 박스를 1.15배만 넓혀 자르고 정사각형의 남는 부분은 회색(114)으로 채운다. 박스 중심을 고정해 가장자리에서도 밀리지 않는다.

## head를 YOLO crop으로 학습 (2026-10-17, 보드 bundle v3)

증상: 보드에서 콜라캔이 `coke__full`로 나옴. 원인 두 가지.
- head는 사진 전체(756 정사각 ROI, 배경 포함)로 학습했는데, 추론은 YOLO 박스 pad crop만 본다
- coke__full 사진 44장 중 약 절반에 빨간 콜라캔이 잔 옆에 찍혀 있고, other에는 콜라캔이 2장뿐 → "빨간 캔 = coke"로 배움

수정: `ml/training/make_crops.py`로 학습 사진을 추론과 같은 crop으로 자른다. 라벨 박스는 **이미지 중심을 포함하는 박스가 정확히 1개일 때만** 쓴다 (0개 = 투명 잔을 YOLO가 놓침, 2개 이상 = 뒤에 캔이 겹침 → 건너뜀. 중심에 가까운 박스로 대신 고르면 캔이 컵 라벨로 들어갔다: 15장 중 12장). 314장 → crop 246장. `class_weight=balanced`.

평가 (보드 fp16 `.pte` 특징, 컵 crop 226장 5-fold × 3~5 seeds / 옆 물체 crop에서 눈으로 고른 캔·병 112장은 학습에 안 쓴 사진 기준):

| head | 컵 잘못 버림 | 음료 맞춤 | 빨간 콜라캔 걸러냄 | 노란 캔·병 걸러냄 | 실제 보드 프레임 (잔 3 + 캔·병 5) |
|---|---:|---:|---:|---:|---|
| v1 사진 전체로 학습 (기존) | 0* | 97.8%* | 8% | 62% | 노란 캔 → water, 콜라캔 → coke |
| v2 crop + 옆 물체 캔 crop 전부를 other로 | 1/226 | 98.7% | 97% | 100% | **잔 2개까지 버림** (화면 아래에 잘린 잔) |
| crop + 가장자리 안 닿은 캔 crop만 other로 + 균형 | 1/226 | 97.8% | 97% | 99% | 캔 crop 뒤에 콜라캔이 보이는 유리잔을 버림 |
| **v3 crop만 + 균형 (배포)** | **0/226** | **97.3%** | **86%** | **96%** | **잔 살림, 캔 2개·병뚜껑 버림**, 과자봉지는 unknown |

\* v1은 이 사진으로 학습해서 낙관적. 옆 물체 캔 crop은 대부분 사진 가장자리에서 잘려 있어서 other로 넣으면 "잘린 물체 = other"를 배우고, 데모 화면 아래에 걸린 진짜 잔도 버린다 → v3는 넣지 않았다.

남은 한계: 학습에 안 쓴 콜라캔의 약 14%는 통과(잔 바로 뒤에 겹친 캔). bundle은 박스를 최대 6개만 본다(`max_objects`). 실제 데모 자리에서 캔을 놓고 라이브 확인은 아직.

## 보드 NPU 실측 (2026-10-17, VENTUNO Q / QCS8275, 주최 측 ExecuTorch + QNN 2.49)

| 모델 | 형식 | 지연 | 정확도 |
|---|---|---:|---|
| DINOv2-small CLS | fp16, 46 MB | **5.8~6.0 ms/장** | fp32 대비 cosine 0.9995 (min 0.9991) → Mac head 그대로 사용 가능 |
| YOLO11n | 16a8w, 3.3 MB | **16 ms/장** | fp32 박스 19/21 일치(IoU>0.8), 놓친 2개는 배경 저신뢰 잔 |

SM8650 x86 시뮬레이터 리허설과 같은 경향(DINOv2 fp16 0.9992 / YOLO 25/27). 측정: `ml/evaluation/board_npu_check.py`. 설치 절차·경로는 [BOARD_RUNBOOK](../BOARD_RUNBOOK.md#보드-executorch-설치-기록-2026-10-17-qcventuno002).
