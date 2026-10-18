# Vision evaluation records — DINOv2 + YOLO11n (local / QNN simulator)

The numbers, PIDs, and deployment states below are records from each run at the time. Current settings and the resident structure follow the [Vision service](../../services/vision/README.md) and the [board runbook](../BOARD_RUNBOOK.md).

Dates: 2026-10-15 ~ 10-17. **These are Mac (M4) and x86 Docker HTP simulator results, not board measurements.** Board numbers are recorded separately. Synthetic images are not evidence of real accuracy.

Reproduction code: `ml/` ([ml/README.md](../../ml/README.md)); runtime: `services/vision/`.

## Board latency before/after resident execution (2026-10-18 UTC)

Experiments used only a local copy of the code in a separate `/tmp`; the board repo and the existing Vision/Gemma services were
not modified or restarted. The existing Gemma4 worker PID 133141 was kept. The numbers below are
direct Vision pipeline invoke times, excluding HTTP/camera/network.

| Item | Previous CLI | Resident DINO+YOLO |
| --- | ---: | ---: |
| Full invoke median | 778.978 ms | 102.309 ms |
| Full invoke p95 | 901.521 ms | 104.053 ms |
| Detection stage median | 380.278 ms | 56.448 ms |
| DINO stage median | 406.668 ms | 44.737 ms |
| Pipeline initial setup/load | 4.189 ms (Python wrapper only) | 515.092 ms (includes loading both models) |

The median of repeated full invokes is about 7.61× faster, and latency dropped by 86.9%. Each was run with the same image and
the `dinov2-qnn-v3` bundle: 3 warm-up runs + 20 measured runs. The image has 3 detected cups,
and the interpreted output matched in all 46 runs. The resident DINO/YOLO PIDs were confirmed to stay
the same from start to finish, and all experiment workers were reaped afterward. This is a single-image, sequential
measurement and does not verify OS cold cache, model accuracy, or concurrent load as a whole.

[Measurement summary](resident-20261018.md), [all samples, input hashes, PIDs](resident-20261018.json),
[SDK source hash and actual build commands](resident-build-20261018.json).
The production service needs a separate push, worker deployment, and Vision restart.

## Pipeline

```text
original image → YOLO11n (COCO, no fine-tuning) cup boxes → box×1.35 square crop
           → DINOv2-small CLS(384) → StandardScaler + LogisticRegression head
           → item / fill_ratio / confidence (services/vision/labels.py)
```

- DINOv2 weights are frozen (`facebook/dinov2-small`); only the head (384×number of classes) is trained = linear probe.
- Internal classes `<drink>__<full|mid|low>` + `empty` → the contract's `fill_ratio` is the probability-weighted expectation of the per-level representative values (0.85/0.5/0.18/0.02).

## Few-shot accuracy (synthetic images, Mac fp32)

`python -m ml.evaluation.eval_fewshot --data data/synthetic` — 10 classes, 200 test images, logreg.

| Drink set | shots/class | joint | fill | drink |
|---|---:|---:|---:|---:|
| **water / coke / coffee** (current demo) | 5 | 60.2% | 67.8% | 84.6% |
| | 10 | 74.5% | 78.6% | 90.7% |
| | 20 | **83.0%** | 86.0% | **93.3%** |
| cola / orange juice / water (earlier experiment) | 20 | 90.0% | 91.5% | 96.7% |

- **coke ↔ coffee confusion is the main error** (5~8 of 60 dark-drink images at 20-shot). In synthetic data they differ only by coke = translucent + bubbles + foam, coffee = opaque + crema → must be checked on real photos.
- CLS alone + standardization worked best (better than CLS+patch-mean or vertical-strip patch pooling). Without standardization, accuracy drops sharply.
- dinov2-small ≥ dinov2-base (same or better accuracy, 4× lighter).

## Real photos (MacBook camera, 2 classes: coke__full 11 / water__full 60)

| Train → test | Result |
|---|---|
| Real 3-shot → real | 100% (optimistic, since most of the 60 water images are consecutive frames) |
| Synthetic only → real | Drink type 91~98%, **fill level fails** (glass shape differs) → fill level needs a few real photos |

## Cup detection (COCO YOLO11n, no fine-tuning)

- Detected 69 of 71 real jar images (97%). Class names were vase 41 / cup 26 / bowl 2 → a group of cup-like classes is used instead of names.
- `agnostic NMS` is required (double cup+vase boxes on the same cup). In synthetic 2~3-glass scenes, box count = cup count in 11/12.

## Vision service end-to-end (Mac, XNNPACK .pte)

`services.vision.backend:create_backend` + bundle `dinov2-xnnpack-yolo` (YOLO and DINOv2 both XNNPACK fp32, head = real-photo 2 classes).
6 scenes with 3 real crops placed on 1280×720 → `POST /v1/analyze`:

- All responses passed `VisionResult` validation; item 9/9 correct in scenes where all 3 cups were detected
- In 3/6 with a cup-count mismatch, other glasses were actually present in the background of the original photo (+1 image missed one)
- HTTP latency p50 102 ms (Mac CPU XNNPACK)

## Latency (Mac M4, batch 1)

| Model | CPU 1 thread | CPU 4 threads | MPS | XNNPACK .pte |
|---|---:|---:|---:|---:|
| dinov2-small 224 | 22.7 ms | 17.8 ms | 10.2 ms | 18.6 ms |
| dinov2-base 224 | 66.0 ms | 55.2 ms | 27.0 ms | — |
| YOLO11n 640 | 16.9 ms | — | 9.9 ms | 21~25 ms |

## QNN (HTP) export + simulator (x86 Docker, SM8650 = HTP v75 rehearsal)

QCS8275 is also HTP v75 (Ultralytics QNN docs, Qualcomm Dragonwing docs). **Stock ExecuTorch 1.5.1 has no QCS8275 target, so this was only a rehearsal on SM8650 — not for board deployment.**

| Model | quant | Ops unsupported on NPU | Simulator check |
|---|---|---:|---|
| YOLO11n | 16a8w | 0 | 25/27 boxes match fp32 (IoU>0.8), class score max\|diff\| 0.85 |
| DINOv2-small CLS | 16a8w | 0 | **cosine 0.58 vs. fp32** → fp32 head 24%, retrained head 54.5% (fp32 61%) |
| DINOv2-small CLS | **fp16** | 0 | **cosine 0.9992**, fp32 head usable as is |
| DINOv2-small CLS | 16a16w | — | cosine 0.08 (do not use) |

- Conclusion: for DINOv2, **prefer fp16**; if that fails, 16a8w + **retrain the head on board .pte features** (`ml/training/make_head.py`).
- The same trend holds for an XNNPACK int8 approximation: using the Mac fp32 head on the int8 model drops 88.8% → 68.2%.
- Even though the official bundle `dino_v2.pte` outputs ImageNet 1000 logits, it can be used for features (synthetic 10 classes 86.2% vs. CLS 88.8%).

## Threshold for asking when cola vs. coffee is ambiguous (2026-10-17, 286 real photos)

`item_confidence` = share of the top drink in the summed drink probabilities. 190 cola/coffee photos, mean over 5-fold × 5 seeds.

| Threshold | Ask rate | Confusions caught | Wrong without asking |
|---:|---:|---:|---:|
| 0.7 | 10.3% | 65% | 2.3% |
| **0.8** | **17.3%** | **87%** | **0.8%** |
| 0.9 | 31.6% | 100% | 0% |

Confusion direction: cola→coffee 8.7% (8.8 of 101), coffee→cola 3.1% (2.8 of 89). Cola in a pint glass is most often confused with coffee.
After label cleanup (14 cases, `data/relabel_log.tsv`): overall 89.3%, refill decision precision 98.3% / recall 69.4%.

## Filtering out non-cup objects (cans, bottles) (2026-10-17)

COCO YOLO11n also detects cans and bottles as `cup` (measured: yellow sparkling-water can 0.81, cola can 0.64). Class names cannot filter them.

- Added an `other` class to the head (28 can/bottle images, `ml.tools.camera collect --classes other`). Vision drops a result when p(other) ≥ 0.5
- Cross-validation (5-fold × 5 seeds): filtered 95.7% of the 28 other images, **0 of 286 cup images wrongly filtered**, cup classification kept at 89.3%
- **The crop method mattered more.** With square ×1.35 expansion, for tall cans or objects at the frame edge, the neighboring cup got into the crop and the classification followed the neighbor (coffee cup next to a can → can classified as coffee)

| crop (YOLO mode) | Yellow can | Coffee cup | Empty glass | Cola can | 3-cup scene |
|---|---|---|---|---|---|
| Square ×1.35 (previous) | coffee | coffee | empty | empty | 9/9 |
| Square ×1.0 | other | coffee | coffee_low ✗ | other | 9/9 |
| **Gray padding ×1.15 (current default)** | **other** | **coffee** | **empty** | **other** | **9/9** |

`pad_crop`: crops the box widened by only 1.15× and fills the rest of the square with gray (114). The box center is fixed, so it does not shift at the edges either.

## Training the head on YOLO crops (2026-10-17, board bundle v3)

Symptom: on the board, a cola can came out as `coke__full`. Two causes.
- The head was trained on whole photos (756 square ROI, including background), but inference only sees the YOLO box pad crop
- About half of the 44 coke__full photos had a red cola can next to the glass, and other had only 2 cola cans → it learned "red can = coke"

Fix: `ml/training/make_crops.py` crops the training photos the same way as inference. A label box is used **only when exactly one box contains the image center** (0 = YOLO missed a clear glass, 2 or more = a can overlaps behind → skipped. Picking the box closest to the center instead put cans in with cup labels: 12 of 15 images). 314 images → 246 crops. `class_weight=balanced`.

Evaluation (board fp16 `.pte` features; 226 cup crops, 5-fold × 3~5 seeds / 112 cans and bottles hand-picked from neighbor-object crops, on photos not used for training):

| head | Cups wrongly dropped | Drink correct | Red cola cans filtered | Yellow cans/bottles filtered | Real board frame (3 glasses + 5 cans/bottles) |
|---|---:|---:|---:|---:|---|
| v1 trained on whole photos (previous) | 0* | 97.8%* | 8% | 62% | yellow can → water, cola can → coke |
| v2 crops + all neighbor-object can crops as other | 1/226 | 98.7% | 97% | 100% | **drops up to 2 glasses** (glasses cut off at the bottom of the frame) |
| crops + only can crops not touching the edge as other + balanced | 1/226 | 97.8% | 97% | 99% | drops a glass with a cola can visible behind it in the can crop |
| **v3 crops only + balanced (deployed)** | **0/226** | **97.3%** | **86%** | **96%** | **keeps the glasses, drops 2 cans and a bottle cap**, snack bag is unknown |

\* v1 is optimistic because it was trained on these photos. Most neighbor-object can crops are cut off at the photo edge, so adding them as other teaches "cut-off object = other" and also drops real glasses at the bottom of the demo frame → v3 does not include them.

Remaining limits: about 14% of cola cans not used in training still pass (cans overlapping directly behind a glass). The bundle looks at no more than 6 boxes (`max_objects`). A live check with cans placed at the actual demo spot has not been done yet.

## Adding water full/mid/low (2026-10-17, board bundle v4c)

v3 saw almost every water glass as empty: of 31 newly taken water__full photos, 28 came out `unknown` (empty), mean fill level 0.19. Water is transparent, so the 60 water__full images (MacBook built-in camera, small glass jar) were not enough.

Added photos of the demo glasses taken with a Brio (connected to the Mac): water__full 37 / mid 22 / low 40 + low 29 (2 labels fixed, `data/relabel_log.tsv`). Crops were made with Mac XNNPACK YOLO and features extracted with Mac fp32 DINOv2, then mixed with the existing board fp16 features (board-measured cosine 0.9995, so the same feature space). 5-fold × 5 seeds with each group of 5 consecutive shots kept in the same fold, criteria fill level ≤ 0.35 · confidence ≥ 0.6:

| head | Drink correct | Refill decision match | Water low caught (1st / extra shoot) | Water full/mid false positives | Cola/coffee low caught | Red cans / yellow cans/bottles filtered |
|---|---:|---:|---|---:|---:|---|
| v3 (no water mid/low) | — | — | sees water as `unknown` (low 23/27 caught as empty glasses) | **24/49** | — | 84% / 95% |
| v4 (27 water low) | 98.5% | 92.0% | 18/27 · 16/23 | 3/49 | 30/36 | 81% / 92% |
| **v4c (50 water low, deployed)** | **99.1%** | **93.5%** | 18/27 · **21/23** | 3/49 | 30/36 | 81% / 92% |

- Training without the small glass jar photos (water__full 0000-0059, coke__full 0000-0010) made no difference (water low stays 18/27) → kept
- The missed water lows had correct labels (10~25%) and were seen as mid/full. Transparent water + the background behind it appear to be the cause
- Collection tool: `ml/tools/board_collect.py` (board Controller `/api/frame` → labels from the left). This shoot used Mac `ml.tools.camera collect` because the board was not connected

## Adding orange juice (2026-10-18, board bundle v5)

Orange juice (`orange_juice`) was added to the menu. Demo glass photos with a Brio (connected to the Mac): full 60 / mid 50 / low 49 → 130 YOLO crops (Mac XNNPACK YOLO, Mac fp32 DINOv2 features). Combined with the v4c data for 14 classes, `class_weight=balanced`. 5-fold × 5 seeds with groups of 5 consecutive shots, criteria fill level ≤ 0.35 · confidence ≥ 0.6:

| Drink | Drink correct | Refill targets caught (low/empty) | full/mid false positives |
|---|---:|---:|---:|
| **Orange juice** | **100%** | **36/36** | 1/93 |
| Water | 100% | 40/50 | 2/97 |
| Cola/coffee | 98.0% | 33/36 | 0/117 |
| Empty glass | — | 24/24 | — |

- Orange juice mean fill level: full 0.82 / mid 0.54 / low 0.20 (opaque with strong color, so the levels are distinct)
- Of 39 yellow sparkling-water cans/bottles, 1 was seen as orange juice. Red cans filtered 78% (v4c 81%), yellow cans/bottles 92%
- Board frame (3 glasses + 5 cans/bottles) gives the same result as v4c

## Snack bag detected as orange juice (2026-10-18, board bundle v5e)

At the demo spot, when a red snack bag overlapped in front of or behind an orange juice glass, the bag's box came out as an `orange_juice` refill target (27%, conf 74%).

- Cause: orange packs and bags often appeared behind the orange juice training photos, and in one of them a bag crop went in with an orange juice label (also one red can crop). `other` had no bags like this. In the problem scene, the bag's box also contained the edge of the orange juice glass.
- Fix: removed the 2 wrong images, added bag/red can/bottle crops from next to the orange juice photos as `other`, and **collected at the demo spot with the board camera** (`ml/tools/board_collect.py` method, 3 sessions: bag alone, overlapping a glass, held by hand; bags/cans/bottles → other, glasses → orange_juice mid/low).
- Even so, the bag in the problem scene scored other 0.47 / orange_juice__low 0.38 → changed `split_other` to **drop the object when other is the highest, even below 0.5**.

| | Bag in problem scene | Orange juice glass next to it | Later part of an untrained session (14 bags/cans/bottles / 5 glasses) | Cups dropped in cross-validation |
|---|---|---|---|---|
| v5 | orange_juice refill target (other ≈ 0) | kept | — | 2/455 |
| **v5e + new rule** | **dropped** (other 0.47) | kept | 14/14 dropped / 5/5 kept | **1/453** |

Remaining limits: checked only on the one problem scene and sessions from the same day. During the demo, it is safer to keep bags and cans from overlapping the glasses.

## Head classifier benchmark and LDA head (2026-10-18, board bundle v6)

Question: would a different classifier on top of the frozen DINOv2 features, or data augmentation, beat the logistic-regression head?

- Data: the v5e training set rebuilt from `data/real` (476 YOLO pad crops + 35 bag/can/bottle crops beside the orange juice glasses as `other`), plus the board-camera sessions (snack bag, cans, bottles, orange juice glasses; not augmented, always in training). Features are from the **board NPU** DINOv2 fp16 `.pte` (Mac fp32 features gave the same ranking; mean cosine 0.9994).
- Augmentation (training folds only, ×4 per crop): flip, 85–100% shift/scale, brightness/contrast/saturation ±20%, and with 70% probability a board-quality degradation (downscale to 30–60%, JPEG 55–85, light blur). Hue is untouched because it separates the drinks.
- Evaluation: 5-fold grouped CV (5 consecutive shots per group), 5 seeds; refill decision with the board policy (fill ≤ 0.35, confidence ≥ 0.6). Drink accuracy uses the visual categories (coffee and coke are one `coke` category since 871ad85).

| Head (board features) | Aug | Refill decision | Low/empty caught | Full/mid false refill | Cups dropped | Drink |
|---|:-:|---:|---:|---:|---:|---:|
| Logistic C=0.1 (v5e) | - | 95.9 ± 0.2% | 127/144 | 2.2/310 | 2.0 | 99.0% |
| Logistic C=0.1 | ✓ | 96.9 ± 0.2% | 132/144 | 2.2/310 | 2.0 | 98.7% |
| **LDA shrinkage (v6)** | **✓** | **98.4 ± 0.4%** | **139/144** | 2.4/310 | 1.0 | 99.1% |
| LDA shrinkage | - | 97.5 ± 0.4% | 136/144 | 3.0/310 | 1.4 | 99.0% |

Single-seed screening of other heads with augmentation: linear SVM 95.8%, RBF SVM 95.3% (drops 2 of 3 real glasses cut off at the frame bottom), kNN k=7 93.6% (6/310 false refills), MLP 256 94.7%. Test-time augmentation (averaging flipped/shifted crops) did not help (LDA 98.4% → 98.2%, logistic 96.9% → 96.4%). A zero-shot CLIP ViT-B/32 check on the same crops was also below the head (drinks 96.5%; 90.6% on the boxes where the head is unsure) and was not adopted.

Before deploying, v5e and v6 were run end to end on five saved board scenes (snack bag scene, an older frame with cut-off glasses and cans, and three real demo captures): the same boxes were refill targets in all five, the snack bag stayed dropped, and the orange juice glass beside it moved from 0.42 to 0.50 fill (about 60% in reality). One nearly empty glass with a red can behind it changed from `coke` to `water`, which matches the clear remnant in it.

- Trade-off: LDA posteriors are sharp, so v6 confidence is usually 0.9–1.0 and the 0.6 confidence floor filters less. CV false refills did not increase, but watch this in the rehearsal.
- The head is StandardScaler → `LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")`, exported as `W = coef_`, `b = intercept_`. v6/v7 were first fit with an ad hoc script; `make_head --model lda --augment 4` now does the same (on the v7 training features it reproduces the deployed v7 head to within 6e-5 in `W`/`b`). LDA needs scikit-learn.

## Board-camera sessions at the demo spot (2026-10-18, board bundle v7)

Problem: in rehearsal at the demo spot, v6 often read low water glasses as `mid` (no refill offer).

- Data: two sessions captured with the board camera (640×480) at the demo spot while moving the camera, 12 frames each, crops labeled by position: `s1_wl_cl_empty` (water low, coke low, empty, bottles) and `s2_shuffled` (order and glasses changed; coffee low, water low, empty). 75 crops, ×4 augmented, added to the v6 training set (2995 rows in total). Head: `make_head --model lda --augment 4` equivalent.
- Check: train on one session, test on the other (v6 has seen neither). Counted with the Controller rule (fill ≤ 0.35, confidence ≥ 0.6, not empty); for `empty` and `other` the count is wrongly offered / dropped.

| Held-out session | Head | Water low offered | Coke / coffee low offered | Empty wrongly offered | Other dropped |
|---|---|---:|---:|---:|---:|
| s1 | v6 | 6/11 (4 read as `mid`) | coke 11/12 | 1/9 | 4/4 |
| s1 | v7 trained with s2 | 10/11 | **coke 3/12 (9 read as empty)** | 2/9 | 4/4 |
| s2 | v6 | 9/12 | coffee 11/11 | 0/12 | 4/4 |
| s2 | v7 trained with s1 | 10/12 | coffee 11/11 | 1/12 | 4/4 |

- Grouped CV on the older data (sessions always in training), with empty counted as "do not offer" as in the Controller: v6 configuration 97.9%, v7 configuration 98.2% refill decision; full/mid false refills 2.3 → 3.0 /310. The v6 table above counts empty as "should flag", so its numbers are not directly comparable.
- Saved scenes, v6 vs v7 end to end: the snack bag stays dropped, the orange juice glass is unchanged, and refill targets on drinks are the same except two glasses v6 offered as water low and v7 reads as empty: in `s1_frame05` that glass is labeled empty (v6 was wrong; this frame is in v7's training), the other scene is unlabeled.
- Deployed: `dinov2-qnn-v7` (both sessions in training), selected in `~/.config/refill-assist/vision.env`.
- Risk: with only s2 in training, v7 read most s1 coke-low glasses as empty. The deployed head has seen s1, but a coke-low glass in a new arrangement may still be read as empty and get no offer. Check coke low live at the demo spot before the demo; a third session with coke low in other positions is the fix if it misses.

## Board NPU measurements (2026-10-17, VENTUNO Q / QCS8275, organizer ExecuTorch + QNN 2.49)

| Model | Format | Latency | Accuracy |
|---|---|---:|---|
| DINOv2-small CLS | fp16, 46 MB | **5.8~6.0 ms/image** | cosine 0.9995 vs. fp32 (min 0.9991) → Mac head usable as is |
| YOLO11n | 16a8w, 3.3 MB | **16 ms/image** | 19/21 boxes match fp32 (IoU>0.8); the 2 missed are low-confidence glasses in the background |

Same trend as the SM8650 x86 simulator rehearsal (DINOv2 fp16 0.9992 / YOLO 25/27). Measured with `ml/evaluation/board_npu_check.py`. For the installation procedure and paths, see the [board installation record](../board-installation-20261017.md#board-executorch-installation-record-2026-10-17-qcventuno002).
