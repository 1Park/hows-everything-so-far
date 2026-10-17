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
