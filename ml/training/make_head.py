"""보드에서 head 학습: 학습 사진(data/real/<class>/*.jpg)을 **보드 .pte**에 통과시켜 특징을 뽑고 head JSON 저장.

Mac fp32 특징으로 학습한 head 는 양자화 .pte 와 안 맞으므로 이걸 보드에서 돌린다.
sklearn 이 없으면 numpy 경사하강으로 학습.

  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner py --out models/experiments/vision/heads/head_board.json
  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner cli \
      --runner-bin $QNN_RUNNER --dino-out-shape 1 384 --out models/experiments/vision/heads/head_board.json
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
    ap.add_argument("--batch", type=int, default=16, help="cli runner 한 번에 넣을 장 수")
    ap.add_argument("--C", type=float, default=0.1)
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

    head = fit_head(X, y, classes, C=args.C)
    head["source"] = dict(pte=str(args.dino_pte), runner=args.runner, data=str(root))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(head))
    np.savez(Path(args.out).with_suffix(".npz"), X=X, y=np.array(y), classes=np.array(classes))
    print(f"saved {args.out} (fit={head['fit']}, train acc {head['train_acc'] * 100:.1f}%)")


if __name__ == "__main__":
    main()
