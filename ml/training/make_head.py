"""Train the head on the board: run training photos (data/real/<class>/*.jpg) through the **board .pte**,
extract features, and save the head JSON.

A head trained on Mac fp32 features does not match the quantized .pte, so run this on the board.
Falls back to numpy gradient descent if sklearn is missing.

  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner py --out models/experiments/vision/heads/head_board.json
  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner cli \
      --runner-bin $QNN_RUNNER --dino-out-shape 1 384 --out models/experiments/vision/heads/head_board.json

For a YOLO-mode bundle, first turn the training photos into the same crops as inference (ml/training/make_crops.py):
  python -m ml.training.make_crops --data data/real --bundle <bundle> --runner-bin $QNN_RUNNER --out data/crops
  python -m ml.training.make_head --data data/crops --class-weight balanced ...
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from services.vision.head import fit_head
from services.vision.runners import make_runner
from services.vision.preprocess import dino_input as preprocess

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/real")
    ap.add_argument("--dino-pte", required=True)
    ap.add_argument("--runner", choices=["py", "cli"], default="py")
    ap.add_argument("--runner-bin")
    ap.add_argument("--dino-out-shape", type=int, nargs="+", default=[1, 384])
    ap.add_argument("--batch", type=int, default=16, help="images per cli runner call")
    ap.add_argument("--C", type=float, default=0.1)
    ap.add_argument("--class-weight", choices=["balanced"], help="correct for per-class image count imbalance")
    ap.add_argument("--out", default="models/experiments/vision/heads/head_board.json")
    args = ap.parse_args()

    root = Path(args.data)
    classes = sorted(d.name for d in root.iterdir() if d.is_dir() and any(p.suffix.lower() in EXTS for p in d.iterdir()))
    paths, y = [], []
    for ci, c in enumerate(classes):
        fs = sorted(p for p in (root / c).iterdir() if p.suffix.lower() in EXTS)
        paths += fs
        y += [ci] * len(fs)
    print(f"{len(paths)} images, classes {classes}")

    runner = make_runner(args.runner, args.dino_pte, binary=args.runner_bin, out_shape=args.dino_out_shape)
    t0 = time.perf_counter()
    feats = []
    for i in range(0, len(paths), args.batch):
        xs = [preprocess(Image.open(p)) for p in paths[i : i + args.batch]]
        feats += [o.reshape(-1) for o in runner.run(xs)]
    X = np.stack(feats)
    print(f"features {X.shape} in {time.perf_counter() - t0:.1f}s via {runner.name}")
    if hasattr(runner, "close"):
        runner.close()

    head = fit_head(X, y, classes, C=args.C, class_weight=args.class_weight)
    head["source"] = dict(pte=str(args.dino_pte), runner=args.runner, data=str(root), class_weight=args.class_weight)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(head))
    np.savez(Path(args.out).with_suffix(".npz"), X=X, y=np.array(y), classes=np.array(classes))
    print(f"saved {args.out} (fit={head['fit']}, train acc {head['train_acc'] * 100:.1f}%)")


if __name__ == "__main__":
    main()
