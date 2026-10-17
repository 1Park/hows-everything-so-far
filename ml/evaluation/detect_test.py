"""COCO 사전학습 YOLO가 (파인튜닝 없이) 우리 잔을 잡는지 확인.

  1) 단일 잔 실사 (data/real/*): 잔을 찾았나, 어떤 COCO 클래스로 봤나
  2) 여러 잔 합성 프레임: 실사 crop 2~3장을 가로로 이어 붙여 잔 개수만큼 박스가 나오는지
결과 이미지: models/experiments/vision/detect/

사용 예:
  python -m ml.evaluation.detect_test --conf 0.15
"""

import argparse
import random
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

from ml.common import load_dataset

# 잔으로 볼 수 있는 COCO 클래스
GLASS_LIKE = {"cup", "wine glass", "bottle", "bowl", "vase"}


def detect(model, img, conf):
    # agnostic_nms: 같은 잔에 cup+vase처럼 클래스만 다른 박스가 겹치면 하나만 남김
    r = model.predict(img, conf=conf, agnostic_nms=True, verbose=False)[0]
    out = []
    for b in r.boxes:
        name = r.names[int(b.cls)]
        out.append((name, float(b.conf), b.xyxy[0].tolist()))
    return out, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    ap.add_argument("--data", default="data/real")
    ap.add_argument("--conf", type=float, default=0.15)
    ap.add_argument("--n-composite", type=int, default=12)
    args = ap.parse_args()

    model = YOLO(args.weights)
    out = Path("models/experiments/vision/detect")
    out.mkdir(parents=True, exist_ok=True)
    paths, y, classes = load_dataset(args.data)

    # 1) 단일 잔
    print(f"== single-glass photos ({len(paths)}) conf>={args.conf}")
    found, top_names, confs = 0, Counter(), []
    for i, p in enumerate(paths):
        dets, r = detect(model, str(p), args.conf)
        glass = [d for d in dets if d[0] in GLASS_LIKE]
        if glass:
            found += 1
            best = max(glass, key=lambda d: d[1])
            top_names[best[0]] += 1
            confs.append(best[1])
        else:
            top_names["(none)" if not dets else f"other:{max(dets, key=lambda d: d[1])[0]}"] += 1
        if i % 10 == 0:
            cv2.imwrite(str(out / f"single_{p.parent.name}_{p.stem}.jpg"), r.plot())
    print(f"glass-like found: {found}/{len(paths)} ({found / len(paths) * 100:.0f}%)"
          + (f" | best conf mean {np.mean(confs):.2f}, min {np.min(confs):.2f}" if confs else ""))
    print("top class per image:", dict(top_names.most_common()))

    # 2) 여러 잔: 서로 다른 실사 crop 2~3장을 가로로 이어 붙임
    print(f"\n== multi-glass composites ({args.n_composite})")
    rng = random.Random(0)
    exact = 0
    for k in range(args.n_composite):
        n = rng.choice([2, 3])
        picks = rng.sample(paths, n)
        tiles = [cv2.resize(cv2.imread(str(p)), (420, 420)) for p in picks]
        frame = np.concatenate(tiles, axis=1)
        dets, r = detect(model, frame, args.conf)
        glass = [d for d in dets if d[0] in GLASS_LIKE]
        exact += len(glass) == n
        names = ", ".join(f"{d[0]}:{d[1]:.2f}" for d in sorted(glass, key=lambda d: d[2][0]))
        print(f"  #{k:02d} glasses={n} boxes={len(glass)}  [{names}]  ({' + '.join(p.parent.name for p in picks)})")
        cv2.imwrite(str(out / f"multi_{k:02d}.jpg"), r.plot())
    print(f"box count == glass count: {exact}/{args.n_composite}")
    print(f"\nsaved annotated images → {out}/")


if __name__ == "__main__":
    main()
