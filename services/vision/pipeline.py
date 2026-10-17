"""이미지 1장 → 컵 박스 → 컵별 정사각 crop → DINOv2 .pte → head → 공개 계약 objects.

bundle (VISION_MODEL_PATH 디렉터리, ml/export/make_bundle.py 가 생성) 의 bundle.json:
{
  "version": 1,
  "boxes": {"mode": "yolo" | "rois" | "center",
            "pte": "detector.pte", "runner": "py" | "cli",           # mode=yolo
            "det_conf": 0.25, "crop_scale": 1.35, "max_objects": 6,
            "rois": [[x, y, w, h], ...]},                               # mode=rois, 이미지 대비 비율
  "dino": {"pte": "dino.pte", "runner": "py" | "cli", "out_shape": [1, 384]},
  "head": "head.json",
  "fill_ratio": {"full": 0.85, "mid": 0.5, "low": 0.18, "empty": 0.02},
  "provenance": {...}                                                   # 모델 출처·SDK·target 기록 (읽지 않음)
}
cli runner 바이너리는 보드마다 경로가 달라 bundle에 넣지 않고 VISION_RUNNER_BIN 으로 준다.
"""

import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from services.vision.head import Head
from services.vision.labels import to_observation
from services.vision.preprocess import center_box, dino_input, letterbox, square_crop_box
from services.vision.runners import make_runner


class VisionPipeline:
    def __init__(self, bundle_dir, runner_bin=None, runners=None):
        """runners: 테스트용 주입 {"detector": obj, "dino": obj} (obj.run(list[np.ndarray]) -> list[np.ndarray])."""
        self.dir = Path(bundle_dir)
        cfg_path = self.dir / "bundle.json"
        if not cfg_path.is_file():
            raise FileNotFoundError(f"bundle.json 없음: {cfg_path}")
        self.cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        self.boxes_cfg = self.cfg["boxes"]
        self.mode = self.boxes_cfg["mode"]
        if self.mode not in ("yolo", "rois", "center"):
            raise ValueError(f"unknown boxes.mode {self.mode}")
        runners = runners or {}
        self.head = Head(self.dir / self.cfg["head"])
        dino = self.cfg["dino"]
        self.dino = runners.get("dino") or self._runner(dino["runner"], dino["pte"], dino.get("out_shape", [1, 384]),
                                                        runner_bin)
        self.detector = None
        if self.mode == "yolo":
            b = self.boxes_cfg
            self.detector = runners.get("detector") or self._runner(b.get("runner", "py"), b["pte"], [1, 84, 8400],
                                                                    runner_bin)
        self.timing = {}

    def _runner(self, kind, pte, out_shape, runner_bin):
        path = self.dir / pte
        if not path.is_file():
            raise FileNotFoundError(f".pte 없음: {path}")
        if kind == "cli" and not runner_bin:
            raise ValueError("cli runner 는 VISION_RUNNER_BIN (예: qnn_executor_runner 경로) 이 필요")
        return make_runner(kind, path, binary=runner_bin, out_shape=out_shape)

    def boxes(self, img):
        """→ [(정사각 crop (x, y, side), 컵 박스 xyxy 픽셀)], 왼쪽부터."""
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
        return [(square_crop_box(d[0], (w, h), b.get("crop_scale", 1.35)), d[0]) for d in dets]

    def analyze(self, img: Image.Image):
        """→ 계약 objects (bbox는 원본 전체 이미지 기준 normalized xyxy)."""
        img = img.convert("RGB")
        w, h = img.size
        t0 = time.perf_counter()
        bx = self.boxes(img)
        t1 = time.perf_counter()
        xs = [dino_input(img.crop((x, y, x + s, y + s))) for (x, y, s), _ in bx]
        feats = self.dino.run(xs) if xs else []
        t2 = time.perf_counter()
        objects = []
        if feats:
            probs = self.head.predict_proba(np.stack([f.reshape(-1) for f in feats]))
            for i, ((_, (x0, y0, x1, y1)), p) in enumerate(zip(bx, probs)):
                bbox = dict(x1=x0 / w, y1=y0 / h, x2=x1 / w, y2=y1 / h)
                bbox = {k: round(min(max(v, 0.0), 1.0), 5) for k, v in bbox.items()}
                if bbox["x2"] <= bbox["x1"] or bbox["y2"] <= bbox["y1"]:
                    continue
                objects.append(dict(object_id=f"cup-{i}", bbox=bbox,
                                    **to_observation(p, self.head.classes, self.cfg.get("fill_ratio"))))
        self.timing = dict(boxes_ms=(t1 - t0) * 1000, dino_ms=(t2 - t1) * 1000, total_ms=(time.perf_counter() - t0) * 1000)
        return objects

    def close(self):
        for r in (self.dino, self.detector):
            if r is not None and hasattr(r, "close"):
                r.close()
