"""Vision 서비스가 읽는 bundle 디렉터리 생성 (services/vision/pipeline.py 의 bundle.json 규격).

  # Mac 로컬 (XNNPACK CPU .pte, Python runner)
  python -m ml.export.make_bundle --out models/local/vision/dinov2-xnnpack \
      --dino-pte models/local/vision/dinov2_small_cls_xnnpack.pte --dino-runner py \
      --head models/experiments/vision/heads/head_real_small_cls.json \
      --boxes yolo --yolo-pte models/local/vision/yolo11n_xnnpack/model.pte --yolo-runner py

  # 보드 (QNN .pte, CLI runner — 바이너리 경로는 서비스 실행 시 VISION_RUNNER_BIN)
  python -m ml.export.make_bundle --out models/board/vision/dinov2-qnn \
      --dino-pte <dinov2_small_cls_qnn.pte> --dino-runner cli --head <보드 특징으로 학습한 head.json> \
      --boxes rois --rois rois.json

파일은 bundle 안으로 복사하고 bundle.json 엔 상대 경로만 쓴다. provenance 에 출처·quant·target·SDK 를 기록한다.
"""

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def copy(src, out, name):
    src = Path(src)
    if not src.is_file():
        raise SystemExit(f"파일 없음: {src}")
    shutil.copy2(src, out / name)
    return name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dino-pte", required=True)
    ap.add_argument("--dino-runner", choices=["py", "cli"], default="py")
    ap.add_argument("--dino-out-shape", type=int, nargs="+", default=[1, 384])
    ap.add_argument("--head", required=True, help="services.vision.head JSON — 이 .pte 의 특징으로 학습한 것")
    ap.add_argument("--boxes", choices=["yolo", "rois", "center"], default="center")
    ap.add_argument("--yolo-pte")
    ap.add_argument("--yolo-runner", choices=["py", "cli"], default="py")
    ap.add_argument("--det-conf", type=float, default=0.25)
    ap.add_argument("--crop-mode", choices=["pad", "square"], default="pad",
                    help="yolo 모드 crop: pad=박스×scale + 회색 패딩(기본, 옆 물체 차단) / square=정사각형 확장(이전 방식)")
    ap.add_argument("--crop-scale", type=float, default=None, help="기본 pad 1.15 / square 1.35")
    ap.add_argument("--max-objects", type=int, default=6)
    ap.add_argument("--rois", help="ml.tools.camera rois 로 만든 rois.json")
    ap.add_argument("--note", default="", help="provenance 메모 (quant, target SoC, SDK 버전 등)")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    scale = args.crop_scale or (1.15 if args.crop_mode == "pad" else 1.35)
    boxes = {"mode": args.boxes, "crop_scale": scale if args.boxes == "yolo" else 1.0}
    if args.boxes == "yolo":
        boxes["crop_mode"] = args.crop_mode
    if args.boxes == "yolo":
        if not args.yolo_pte:
            raise SystemExit("--boxes yolo 는 --yolo-pte 필요")
        boxes.update(pte=copy(args.yolo_pte, out, "detector.pte"), runner=args.yolo_runner,
                     det_conf=args.det_conf, max_objects=args.max_objects)
    elif args.boxes == "rois":
        if not args.rois:
            raise SystemExit("--boxes rois 는 --rois 필요")
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
