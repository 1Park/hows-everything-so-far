"""Create the bundle directory the Vision service reads (bundle.json spec in services/vision/pipeline.py).

  # Mac local (XNNPACK CPU .pte, Python runner)
  python -m ml.export.make_bundle --out models/local/vision/dinov2-xnnpack \
      --dino-pte models/local/vision/dinov2_small_cls_xnnpack.pte --dino-runner py \
      --head models/experiments/vision/heads/head_real_small_cls.json \
      --boxes yolo --yolo-pte models/local/vision/yolo11n_xnnpack/model.pte --yolo-runner py

  # Board (QNN .pte, CLI runner — binary path comes from VISION_RUNNER_BIN when the service runs)
  python -m ml.export.make_bundle --out models/board/vision/dinov2-qnn \
      --dino-pte <dinov2_small_cls_qnn.pte> --dino-runner cli --head <head.json trained on board features> \
      --boxes rois --rois rois.json

Files are copied into the bundle and bundle.json stores only relative paths. provenance records source, quant, target, and SDK.
"""

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def copy(src, out, name):
    src = Path(src)
    if not src.is_file():
        raise SystemExit(f"file not found: {src}")
    shutil.copy2(src, out / name)
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dino-pte", required=True)
    ap.add_argument("--dino-runner", choices=["py", "cli"], default="py")
    ap.add_argument("--dino-out-shape", type=int, nargs="+", default=[1, 384])
    ap.add_argument("--head", required=True, help="services.vision.head JSON — trained on this .pte's features")
    ap.add_argument("--boxes", choices=["yolo", "rois", "center"], default="center")
    ap.add_argument("--yolo-pte")
    ap.add_argument("--yolo-runner", choices=["py", "cli"], default="py")
    ap.add_argument("--det-conf", type=float, default=0.25)
    ap.add_argument("--crop-mode", choices=["pad", "square"], default="pad",
                    help="yolo-mode crop: pad=box x scale + gray pad (default, hides neighbors) / square=square expand (old)")
    ap.add_argument("--crop-scale", type=float, default=None, help="default pad 1.15 / square 1.35")
    ap.add_argument("--max-objects", type=int, default=6)
    ap.add_argument("--rois", help="rois.json made with ml.tools.camera rois")
    ap.add_argument("--note", default="", help="provenance note (quant, target SoC, SDK version, etc.)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scale = args.crop_scale or (1.15 if args.crop_mode == "pad" else 1.35)
    boxes = {"mode": args.boxes, "crop_scale": scale if args.boxes == "yolo" else 1.0}
    if args.boxes == "yolo":
        boxes["crop_mode"] = args.crop_mode
    if args.boxes == "yolo":
        if not args.yolo_pte:
            raise SystemExit("--boxes yolo requires --yolo-pte")
        boxes.update(pte=copy(args.yolo_pte, out, "detector.pte"), runner=args.yolo_runner,
                     det_conf=args.det_conf, max_objects=args.max_objects)
    elif args.boxes == "rois":
        if not args.rois:
            raise SystemExit("--boxes rois requires --rois")
        boxes["rois"] = json.loads(Path(args.rois).read_text())["rois"]
    head = json.loads(Path(args.head).read_text())
    cfg = {
        "version": 1,
        "boxes": boxes,
        "dino": {"pte": copy(args.dino_pte, out, "dino.pte"), "runner": args.dino_runner,
                 "out_shape": args.dino_out_shape},
        "head": copy(args.head, out, "head.json"),
        "provenance": {
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "dino_pte": str(args.dino_pte), "yolo_pte": args.yolo_pte, "head": str(args.head),
            "head_classes": head["classes"], "head_source": head.get("source"),
            "preprocess": "services.vision.preprocess (dino_input 224, letterbox 640)",
            "note": args.note,
        },
    }
    (out / "bundle.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    print(f"bundle → {out}  (classes {head['classes']})")
    print(f"run: VISION_MODEL_BACKEND=external VISION_ADAPTER=services.vision.backend:create_backend "
          f"VISION_MODEL_PATH={out}" + (" VISION_RUNNER_BIN=<runner>" if "cli" in (args.dino_runner, args.yolo_runner) else ""))


if __name__ == "__main__":
    main()
