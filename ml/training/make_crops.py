"""Turn training photos into the same YOLO box crops used at inference -> make_head input.

Inference only sees the YOLO box x1.15 gray-padded crop (pad_crop); training on whole photos with background
learns the background objects too (measured: about half the coke__full photos had a coke can beside them,
so a can crop -> coke__full).

For each photo, the box of the center object (placed in the center ROI of the collect screen) is the label
box, but only when exactly 1 box contains the image center. With 0 (YOLO missed a clear glass) or 2+ (a can
overlaps behind) the photo is skipped — picking the box closest to the center instead puts cans under cup
labels (measured: 12 of 15). Other boxes are saved separately in <out>_extra/ (unlabeled; candidates to
review by eye and add to other, etc.).

  python -m ml.training.make_crops --data data/real --bundle models/board/vision/<bundle> \
      --runner-bin $QNN_RUNNER --out data/crops
  python -m ml.training.make_head --data data/crops ...
"""

import argparse
import json
from pathlib import Path

from PIL import Image

from services.vision.pipeline import VisionPipeline
from services.vision.preprocess import letterbox, pad_crop
from services.vision.yolo import postprocess

EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def main_box(dets, size):
    """The box containing the image center if exactly one does, else None."""
    cx, cy = size[0] / 2, size[1] / 2
    inside = [d for d in dets if d[0][0] <= cx <= d[0][2] and d[0][1] <= cy <= d[0][3]]
    return inside[0] if len(inside) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/real")
    ap.add_argument(
        "--bundle", required=True, help="Vision bundle to read the YOLO .pte and det_conf/crop_scale from"
    )
    ap.add_argument("--runner-bin")
    ap.add_argument("--out", default="data/crops")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument(
        "--exclude", nargs="*", default=[], help="bad photos found by eye (<class>/<file>)"
    )
    args = ap.parse_args()

    pipe = VisionPipeline(args.bundle, args.runner_bin)
    cfg = pipe.boxes_cfg
    if pipe.mode != "yolo":
        raise SystemExit("bundle boxes.mode must be yolo")
    margin, conf = cfg.get("crop_scale", 1.15), cfg.get("det_conf", 0.25)
    root, out = Path(args.data), Path(args.out)
    extra = out.with_name(out.name + "_extra")  # inside out, make_head would read it as a class
    paths = sorted(p for p in root.glob("*/*") if p.suffix.lower() in EXTS)
    manifest, missed, ambiguous = {}, [], []
    for i in range(0, len(paths), args.batch):
        chunk = paths[i : i + args.batch]
        imgs = [Image.open(p).convert("RGB") for p in chunk]
        lbs = [letterbox(im) for im in imgs]
        outs = pipe.detector.run([x for x, _ in lbs])
        for p, im, (_, meta), o in zip(chunk, imgs, lbs, outs):
            rel = f"{p.parent.name}/{p.name}"
            dets = postprocess(o.reshape(1, 84, -1), meta, im.size, conf=conf)
            if not dets:
                missed.append(rel)
                continue
            m = main_box(dets, im.size)
            if m is None or rel in args.exclude:
                ambiguous.append(rel)
                continue
            (out / p.parent.name).mkdir(parents=True, exist_ok=True)
            pad_crop(im, m[0], margin).save(out / p.parent.name / p.name, quality=95)
            extras = [d for d in dets if d is not m]
            for k, d in enumerate(extras):
                extra.mkdir(parents=True, exist_ok=True)
                pad_crop(im, d[0], margin).save(
                    extra / f"{p.parent.name}__{p.stem}__{k}.jpg", quality=95
                )
            manifest[rel] = dict(
                main=[round(v, 1) for v in m[0]],
                extras=[[round(v, 1) for v in d[0]] for d in extras],
            )
    pipe.close()
    out.mkdir(parents=True, exist_ok=True)
    (out.with_name(out.name + "_manifest.json")).write_text(
        json.dumps(dict(missed=missed, ambiguous=ambiguous, boxes=manifest), indent=1)
    )
    print(
        f"{len(paths)} images → {len(manifest)} crops, {len(missed)} no box, {len(ambiguous)} ambiguous/excluded, "
        f"{sum(len(v['extras']) for v in manifest.values())} extra boxes → {out}, {extra}"
    )
    for rel in missed:
        print("  no box:", rel)


if __name__ == "__main__":
    main()
