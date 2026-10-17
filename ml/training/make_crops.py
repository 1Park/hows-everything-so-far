"""학습 사진을 실제 추론과 같은 YOLO 박스 crop으로 바꾼다 → make_head 입력.

추론은 YOLO 박스 ×1.15 회색 패딩 crop(pad_crop)만 보는데, 학습은 배경까지 든 사진 전체로 하면
배경 물체를 같이 배운다 (실측: coke__full 사진 약 절반에 콜라캔이 옆에 있어 캔 crop → coke__full).

사진마다 가운데 물체(수집 화면 가운데 ROI에 놓고 찍음)의 박스를 라벨 박스로 쓴다:
이미지 중심을 포함하는 박스가 정확히 1개일 때만. 0개(투명 잔을 YOLO가 놓침)나 2개 이상(뒤에 캔이 겹침)이면
건너뛴다 — 중심에 가까운 박스로 대신 고르면 캔이 컵 라벨로 들어간다 (실측 15장 중 12장).
나머지 박스는 <out>_extra/ 에 따로 저장 (라벨 없음, 눈으로 보고 other 등에 추가할 후보).

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
    """이미지 중심을 포함하는 박스가 정확히 1개면 그 박스, 아니면 None."""
    cx, cy = size[0] / 2, size[1] / 2
    inside = [d for d in dets if d[0][0] <= cx <= d[0][2] and d[0][1] <= cy <= d[0][3]]
    return inside[0] if len(inside) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/real")
    ap.add_argument(
        "--bundle", required=True, help="YOLO .pte와 det_conf/crop_scale을 읽을 Vision bundle"
    )
    ap.add_argument("--runner-bin")
    ap.add_argument("--out", default="data/crops")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument(
        "--exclude", nargs="*", default=[], help="눈으로 확인한 잘못된 사진 (<class>/<file>)"
    )
    args = ap.parse_args()

    pipe = VisionPipeline(args.bundle, args.runner_bin)
    cfg = pipe.boxes_cfg
    if pipe.mode != "yolo":
        raise SystemExit("bundle boxes.mode 가 yolo 여야 함")
    margin, conf = cfg.get("crop_scale", 1.15), cfg.get("det_conf", 0.25)
    root, out = Path(args.data), Path(args.out)
    extra = out.with_name(out.name + "_extra")  # out 안에 두면 make_head가 클래스로 읽는다
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
