"""Collect training crops from the board camera (Controller /api/frame) — same 640x480 frames and
same YOLO pad crop as real inference.

The Controller holds the camera open, so we fetch /api/frame instead of opening it directly.
Pass --labels in the left-to-right order the glasses are placed. YOLO boxes are sorted left to right and labeled;
if the box count differs from the label count, the frame is skipped (only a preview is kept in frames/).

  python -m ml.tools.board_collect --bundle models/board/vision/<bundle> --runner-bin $QNN_RUNNER \
      --labels water__low water__mid water__full --shots 10 --interval 2 --out ~/ml-work/data/board_crops
  → <out>/<label>/<session>_<shot>_<i>.jpg   (crops ready for make_head --data)
    <out>_frames/<session>_<shot>.jpg         (preview with boxes and labels drawn)

While shooting, vary glass position/angle a little but keep the left-to-right order.
"""

import argparse
import io
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

from services.vision.pipeline import VisionPipeline
from services.vision.preprocess import pad_crop


def grab(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return Image.open(io.BytesIO(r.read())).convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bundle", required=True, help="Vision bundle to read the YOLO .pte and det_conf/crop_scale from"
    )
    ap.add_argument("--runner-bin")
    ap.add_argument(
        "--labels",
        nargs="+",
        required=True,
        help="classes of the glasses from left to right (e.g. water__low water__mid)",
    )
    ap.add_argument("--shots", type=int, default=10)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--frame-url", default="http://127.0.0.1:8080/api/frame")
    ap.add_argument("--out", default="data/board_crops")
    args = ap.parse_args()

    pipe = VisionPipeline(args.bundle, args.runner_bin)
    if pipe.mode != "yolo":
        raise SystemExit("bundle boxes.mode must be yolo")
    margin = pipe.boxes_cfg.get("crop_scale", 1.15)
    out, frames = Path(args.out), Path(args.out + "_frames")
    frames.mkdir(parents=True, exist_ok=True)
    session = time.strftime("%H%M%S")
    saved, skipped = 0, 0
    for shot in range(args.shots):
        if shot:
            time.sleep(args.interval)
        img = grab(args.frame_url)
        boxes = sorted((xyxy for _, xyxy in pipe.boxes(img)), key=lambda b: b[0])
        ok = len(boxes) == len(args.labels)
        view = img.copy()
        d = ImageDraw.Draw(view)
        for i, b in enumerate(boxes):
            d.rectangle(b, outline=(0, 255, 0) if ok else (255, 0, 0), width=3)
            d.text((b[0] + 3, b[1] + 3), args.labels[i] if ok else str(i), fill=(255, 255, 0))
        view.save(frames / f"{session}_{shot:02d}.jpg", quality=85)
        if not ok:
            skipped += 1
            print(
                f"shot {shot}: {len(boxes)} boxes ≠ {len(args.labels)} labels → skipped", flush=True
            )
            continue
        for i, (label, b) in enumerate(zip(args.labels, boxes)):
            (out / label).mkdir(parents=True, exist_ok=True)
            pad_crop(img, b, margin).save(out / label / f"{session}_{shot:02d}_{i}.jpg", quality=95)
            saved += 1
        print(
            f"shot {shot}: "
            + " ".join(f"{label}@x{round(b[0])}" for label, b in zip(args.labels, boxes)),
            flush=True,
        )
    pipe.close()
    print(f"session {session}: saved {saved} crops, skipped {skipped} frames → {out}")


if __name__ == "__main__":
    main()
