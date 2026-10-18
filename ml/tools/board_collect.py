"""보드 카메라(Controller /api/frame)로 학습 crop 수집 — 실제 추론과 같은 640x480 프레임 + 같은 YOLO pad crop.

카메라는 Controller가 열고 있으므로 직접 열지 않고 /api/frame 을 받는다.
잔을 왼쪽부터 놓은 순서대로 --labels 를 준다. YOLO 박스를 왼쪽부터 정렬해 라벨을 붙이고,
박스 수가 라벨 수와 다르면 그 프레임은 저장하지 않고 건너뛴다 (frames/ 에 미리보기만 남김).

  python -m ml.tools.board_collect --bundle models/board/vision/<bundle> --runner-bin $QNN_RUNNER \
      --labels water__low water__mid water__full --shots 10 --interval 2 --out ~/ml-work/data/board_crops
  → <out>/<label>/<session>_<shot>_<i>.jpg   (make_head --data 에 바로 쓰는 crop)
    <out>_frames/<session>_<shot>.jpg         (박스·라벨 그린 미리보기)

찍는 동안 잔 위치·각도를 조금씩 바꾸되 왼쪽→오른쪽 순서는 유지한다.
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
        "--bundle", required=True, help="YOLO .pte와 det_conf/crop_scale을 읽을 Vision bundle"
    )
    ap.add_argument("--runner-bin")
    ap.add_argument(
        "--labels",
        nargs="+",
        required=True,
        help="왼쪽부터 놓은 잔의 클래스 (예: water__low water__mid)",
    )
    ap.add_argument("--shots", type=int, default=10)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--frame-url", default="http://127.0.0.1:8080/api/frame")
    ap.add_argument("--out", default="data/board_crops")
    args = ap.parse_args()

    pipe = VisionPipeline(args.bundle, args.runner_bin)
    if pipe.mode != "yolo":
        raise SystemExit("bundle boxes.mode 가 yolo 여야 함")
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
                f"shot {shot}: 박스 {len(boxes)}개 ≠ 라벨 {len(args.labels)}개 → 건너뜀", flush=True
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
    print(f"session {session}: crop {saved}장 저장, 프레임 {skipped}개 건너뜀 → {out}")


if __name__ == "__main__":
    main()
