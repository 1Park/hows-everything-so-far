"""Train the head on the board: run training photos (data/real/<class>/*.jpg) through the **board .pte**,
extract features, and save the head JSON.

A head trained on Mac fp32 features does not match the quantized .pte, so run this on the board.
Falls back to numpy gradient descent if sklearn is missing (logistic only; --model lda needs sklearn).

  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner py --out models/experiments/vision/heads/head_board.json
  python -m ml.training.make_head --data data/real --dino-pte dino.pte --runner cli \
      --runner-bin $QNN_RUNNER --dino-out-shape 1 384 --out models/experiments/vision/heads/head_board.json

For a YOLO-mode bundle, first turn the training photos into the same crops as inference (ml/training/make_crops.py):
  python -m ml.training.make_crops --data data/real --bundle <bundle> --runner-bin $QNN_RUNNER --out data/crops
  python -m ml.training.make_head --data data/crops --class-weight balanced ...

Board bundle v6/v7 head (LDA + x4 augmentation; board-camera crops sorted into <class>/ folders the same way):
  python -m ml.training.make_head --data data/crops data/board_crops --model lda --augment 4 \
      --dino-pte dino.pte --runner cli --runner-bin $QNN_RUNNER --out head_board_lda.json
"""

import argparse
import io
import json
import random
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from services.vision.head import fit_head
from services.vision.runners import make_runner
from services.vision.preprocess import dino_input as preprocess

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def augment(im, rng):
    """One augmented copy of a crop: flip, 85–100% shift/scale, brightness/contrast/saturation, and
    usually a board-quality degradation (640x480 camera: downscale, JPEG, light blur). Hue is left
    alone because it separates the drinks."""
    w, h = im.size
    if rng.random() < 0.5:
        im = ImageOps.mirror(im)
    s = rng.uniform(0.85, 1.0)
    cw, ch = int(w * s), int(h * s)
    x0, y0 = rng.randint(0, w - cw), rng.randint(0, h - ch)
    im = im.crop((x0, y0, x0 + cw, y0 + ch))
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.75, 1.25))
    im = ImageEnhance.Contrast(im).enhance(rng.uniform(0.8, 1.2))
    im = ImageEnhance.Color(im).enhance(rng.uniform(0.8, 1.2))
    if rng.random() < 0.7:
        f = rng.uniform(0.3, 0.6)
        small = im.resize((max(16, int(im.width * f)), max(16, int(im.height * f))), Image.BILINEAR)
        buf = io.BytesIO()
        small.save(buf, "JPEG", quality=rng.randint(55, 85))
        im = Image.open(buf).convert("RGB").resize(im.size, Image.BILINEAR)
        if rng.random() < 0.5:
            im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
    return im


def list_images(roots):
    """<root>/<class>/*.jpg over several roots → (paths, labels, classes); same class name = same class."""
    by_class = {}
    for root in map(Path, roots):
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            by_class.setdefault(d.name, []).extend(sorted(p for p in d.iterdir() if p.suffix.lower() in EXTS))
    classes = sorted(c for c, fs in by_class.items() if fs)
    paths, y = [], []
    for ci, c in enumerate(classes):
        paths += by_class[c]
        y += [ci] * len(by_class[c])
    return paths, y, classes


def inputs(path, n_aug):
    """The crop plus n_aug augmented copies (seeded by path, so reruns give the same features)."""
    im = Image.open(path).convert("RGB")
    rng = random.Random(str(path))
    return [preprocess(im)] + [preprocess(augment(im, rng)) for _ in range(n_aug)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", nargs="+", default=["data/real"], help="one or more <dir>/<class>/*.jpg roots")
    ap.add_argument("--dino-pte", required=True)
    ap.add_argument("--runner", choices=["py", "cli"], default="py")
    ap.add_argument("--runner-bin")
    ap.add_argument("--dino-out-shape", type=int, nargs="+", default=[1, 384])
    ap.add_argument("--batch", type=int, default=16, help="images per cli runner call")
    ap.add_argument("--model", choices=["logistic", "lda"], default="logistic")
    ap.add_argument("--augment", type=int, default=0, help="augmented copies per training image (v6/v7: 4)")
    ap.add_argument("--C", type=float, default=0.1)
    ap.add_argument("--class-weight", choices=["balanced"], help="correct for per-class image count imbalance (logistic)")
    ap.add_argument("--out", default="models/experiments/vision/heads/head_board.json")
    args = ap.parse_args()

    paths, y, classes = list_images(args.data)
    print(f"{len(paths)} images (x{1 + args.augment} with augmentation), classes {classes}")

    runner = make_runner(args.runner, args.dino_pte, binary=args.runner_bin, out_shape=args.dino_out_shape)
    t0 = time.perf_counter()
    feats = []
    per_batch = max(1, args.batch // (1 + args.augment))
    for i in range(0, len(paths), per_batch):
        xs = [x for p in paths[i : i + per_batch] for x in inputs(p, args.augment)]
        feats += [o.reshape(-1) for o in runner.run(xs)]
    F = np.stack(feats).reshape(len(paths), 1 + args.augment, -1)
    X = F[:, 0]
    print(f"features {F.shape} in {time.perf_counter() - t0:.1f}s via {runner.name}")
    if hasattr(runner, "close"):
        runner.close()

    head = fit_head(F.reshape(-1, F.shape[2]), np.repeat(y, 1 + args.augment), classes, C=args.C,
                    class_weight=args.class_weight, model=args.model)
    head["source"] = dict(pte=str(args.dino_pte), runner=args.runner, data=[str(d) for d in args.data],
                          model=args.model, augment=args.augment, class_weight=args.class_weight)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(head))
    np.savez(Path(args.out).with_suffix(".npz"), X=X, XA=F[:, 1:], y=np.array(y), classes=np.array(classes))
    print(f"saved {args.out} (fit={head['fit']}, train acc {head['train_acc'] * 100:.1f}%)")


if __name__ == "__main__":
    main()
