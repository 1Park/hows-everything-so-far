"""One image → cup boxes → square crop per cup → DINOv2 .pte → head → public contract objects.

bundle.json in the bundle (the VISION_MODEL_PATH directory, built by ml/export/make_bundle.py):
{
  "version": 1,
  "boxes": {"mode": "yolo" | "rois" | "center",
            "pte": "detector.pte", "runner": "py" | "cli",           # mode=yolo
            "det_conf": 0.25, "crop_mode": "pad" | "square", "crop_scale": 1.15, "max_objects": 6,
            "rois": [[x, y, w, h], ...]},                               # mode=rois, fractions of the image
  "dino": {"pte": "dino.pte", "runner": "py" | "cli", "out_shape": [1, 384]},
  "head": "head.json",
  "fill_ratio": {"full": 0.85, "mid": 0.5, "low": 0.18, "empty": 0.02},
  "provenance": {...}                                                   # model source/SDK/target record (not read)
}
The cli runner binary path differs per board, so it is not in the bundle; pass it via
VISION_RUNNER_BIN.
"""

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from services.vision.head import Head
from services.vision.labels import split_other, to_observation
from services.vision.preprocess import center_box, dino_input, letterbox, pad_crop, square_crop_box
from services.vision.runners import make_runner


class VisionPipeline:
    def __init__(self, bundle_dir, runner_bin=None, runners=None, *, resident=False,
                 worker_bin=None, timeout=20):
        """runners: test injection {"detector": obj, "dino": obj} (obj.run(list[np.ndarray]) -> list[np.ndarray])."""
        self.dir = Path(bundle_dir)
        self.resident_mode, self.worker_bin, self.timeout = resident, worker_bin, timeout
        cfg_path = self.dir / "bundle.json"
        if not cfg_path.is_file():
            raise FileNotFoundError(f"bundle.json not found: {cfg_path}")
        self.cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.boxes_cfg = self.cfg["boxes"]
        self.mode = self.boxes_cfg["mode"]
        if self.mode not in ("yolo", "rois", "center"):
            raise ValueError(f"unknown boxes.mode {self.mode}")
        runners = runners or {}
        self.head = Head(self.dir / self.cfg["head"])
        dino = self.cfg["dino"]
        self.dino = None
        self.detector = None
        try:
            self.dino = runners.get("dino") or self._runner(
                dino["runner"], dino["pte"], dino.get("out_shape", [1, 384]), runner_bin)
            if self.mode == "yolo":
                b = self.boxes_cfg
                self.detector = runners.get("detector") or self._runner(
                    b.get("runner", "py"), b["pte"], [1, 84, 8400], runner_bin)
        except BaseException:
            self.close()
            raise
        self.timing = {}

    def _runner(self, kind, pte, out_shape, runner_bin):
        path = self.dir / pte
        if not path.is_file():
            raise FileNotFoundError(f".pte not found: {path}")
        if self.resident_mode and kind == "cli":
            kind = "resident"
        if kind == "resident":
            return make_runner(kind, path, binary=self.worker_bin, out_shape=out_shape,
                               timeout=self.timeout)
        if kind == "cli" and not runner_bin:
            raise ValueError("cli runner requires VISION_RUNNER_BIN (e.g. path to qnn_executor_runner)")
        return make_runner(kind, path, binary=runner_bin, out_shape=out_shape)

    @property
    def resident(self):
        return all(getattr(r, "resident", True) for r in (self.dino, self.detector) if r is not None)

    @property
    def status(self):
        return {name: getattr(r, "status", {"resident": getattr(r, "resident", True),
                                           "runner": getattr(r, "name", "injected")})
                for name, r in (("dino", self.dino), ("detector", self.detector)) if r is not None}

    def abort(self):
        for r in (self.dino, self.detector):
            if r is not None and hasattr(r, "abort"):
                r.abort()

    def boxes(self, img):
        """→ [(square crop (x, y, side), cup box xyxy in pixels)], left to right."""
        w, h = img.size
        b = self.boxes_cfg
        if self.mode == "center":
            x, y, s = center_box((w, h))
            return [((x, y, s), (x, y, x + s, y + s))]
        if self.mode == "rois":
            out = []
            for rx, ry, rw, rh in b["rois"]:
                xyxy = (rx * w, ry * h, (rx + rw) * w, (ry + rh) * h)
                out.append((square_crop_box(xyxy, (w, h), b.get("crop_scale", 1.0)), xyxy))
            return out
        from services.vision.yolo import postprocess

        x, meta = letterbox(img)
        dets = postprocess(self.detector.run([x])[0], meta, (w, h), conf=b.get("det_conf", 0.25))
        dets = sorted(dets[: b.get("max_objects", 6)], key=lambda d: d[0][0])
        if b.get("crop_mode", "pad") == "pad":  # None → pad_crop in analyze()
            return [(None, d[0]) for d in dets]
        return [(square_crop_box(d[0], (w, h), b.get("crop_scale", 1.35)), d[0]) for d in dets]

    def crop(self, img, square, xyxy):
        if square is None:
            return pad_crop(img, xyxy, self.boxes_cfg.get("crop_scale", 1.15))
        x, y, s = square
        return img.crop((x, y, x + s, y + s))

    def analyze(self, img: Image.Image):
        """→ contract objects (bbox is normalized xyxy relative to the full original image)."""
        img = img.convert("RGB")
        w, h = img.size
        t0 = time.perf_counter()
        bx = self.boxes(img)
        t1 = time.perf_counter()
        xs = [dino_input(self.crop(img, sq, xyxy)) for sq, xyxy in bx]
        feats = self.dino.run(xs) if xs else []
        t2 = time.perf_counter()
        objects = []
        self.dropped = 0  # boxes dropped as other (cans, bottles)
        if feats:
            probs = self.head.predict_proba(np.stack([f.reshape(-1) for f in feats]))
            for (_, (x0, y0, x1, y1)), p in zip(bx, probs):
                not_cup, p, classes = split_other(p, self.head.classes)
                if not_cup:  # cans, bottles, etc. — not cups, so left out of the scene result
                    self.dropped += 1
                    continue
                bbox = dict(x1=x0 / w, y1=y0 / h, x2=x1 / w, y2=y1 / h)
                bbox = {k: round(min(max(v, 0.0), 1.0), 5) for k, v in bbox.items()}
                if bbox["x2"] <= bbox["x1"] or bbox["y2"] <= bbox["y1"]:
                    continue
                objects.append(dict(object_id=f"cup-{len(objects)}", bbox=bbox,
                                    **to_observation(p, classes, self.cfg.get("fill_ratio"))))
        self.timing = dict(dropped=self.dropped, boxes_ms=(t1 - t0) * 1000, dino_ms=(t2 - t1) * 1000, total_ms=(time.perf_counter() - t0) * 1000)
        return objects

    def close(self):
        for r in (self.dino, self.detector):
            if r is not None and hasattr(r, "close"):
                r.close()
