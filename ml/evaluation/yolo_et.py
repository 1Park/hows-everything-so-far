"""YOLO11n ExecuTorch(.pte) 추론 — ultralytics 없이 numpy + cv2만으로 전처리/후처리.

보드에서 그대로 쓰기 위한 모듈. .pte 출력 형식 (ultralytics export, 디코드 포함):
  (1, 84, 8400) = [cx, cy, w, h (640 입력 픽셀 기준), COCO 80클래스 점수(sigmoid 적용됨)] × 앵커 8400개

사용 예 (Mac 검증):
  python -m ml.evaluation.yolo_et --pte models/local/vision/yolo11n_xnnpack/model.pte --compare
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from services.vision.preprocess import YOLO_SIZE as IMG, letterbox  # noqa: F401 (보드와 공유)
from services.vision.yolo import GLASS_IDS, nms, postprocess  # noqa: F401


def to_pil(frame_bgr):
    return Image.fromarray(np.ascontiguousarray(frame_bgr[..., ::-1]))


class YoloET:
    """ExecuTorch Python 런타임으로 .pte 실행. 보드에 Python 바인딩이 없으면 run()만 runner 호출로 바꾸면 된다."""

    def __init__(self, pte_path):
        import torch  # executorch.runtime 입력이 torch.Tensor
        from executorch.runtime import Runtime

        self.torch = torch
        self.method = Runtime.get().load_program(Path(pte_path)).load_method("forward")

    def run(self, x: np.ndarray) -> np.ndarray:
        return self.method.execute([self.torch.from_numpy(x)])[0].numpy()

    def __call__(self, frame_bgr, conf=0.25, iou=0.7):
        x, meta = letterbox(to_pil(frame_bgr))
        return postprocess(self.run(x), meta, (frame_bgr.shape[1], frame_bgr.shape[0]), conf, iou)


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def compare(args):
    """ultralytics(PyTorch) vs .pte(XNNPACK) + numpy 후처리: 원출력 차이, 박스 일치, 속도."""
    import random

    import torch
    from ultralytics import YOLO

    yolo = YOLO(args.weights)
    et = YoloET(args.pte)
    paths = sorted(Path(args.data).glob("*/*.jpg"))
    rng = random.Random(0)

    # 1) 원출력 비교 (같은 letterbox 입력)
    frame = cv2.imread(str(paths[0]))
    x, _ = letterbox(to_pil(frame))
    with torch.no_grad():
        ref = yolo.model.float().eval()(torch.from_numpy(x))
    ref = (ref[0] if isinstance(ref, (list, tuple)) else ref).numpy()
    got = et.run(x)
    print(f"raw output {got.shape} | max|diff| vs PyTorch {np.abs(ref - got).max():.2e}")

    # 2) 박스 비교: 단일 잔 사진 + 2~3잔 이어붙인 프레임
    frames = [cv2.imread(str(p)) for p in paths[::4]]
    for _ in range(10):
        picks = rng.sample(paths, rng.choice([2, 3]))
        frames.append(np.concatenate([cv2.resize(cv2.imread(str(p)), (420, 420)) for p in picks], 1))
    same_n = matched = total = 0
    for f in frames:
        r = yolo.predict(f, conf=args.conf, agnostic_nms=True, imgsz=IMG, verbose=False)[0]
        ref_boxes = [b.xyxy[0].tolist() for b in r.boxes if int(b.cls) in GLASS_IDS]
        got_boxes = [d[0] for d in et(f, args.conf)]
        same_n += len(ref_boxes) == len(got_boxes)
        for rb in ref_boxes:
            total += 1
            matched += any(box_iou(rb, gb) > 0.9 for gb in got_boxes)
    print(f"frames {len(frames)}: same box count {same_n}/{len(frames)} | ref boxes matched (IoU>0.9) {matched}/{total}")

    # 3) 속도 (Mac CPU, XNNPACK)
    f = frames[-1]
    for _ in range(5):
        et(f)
    ts = {"pre": [], "infer": [], "post": []}
    for _ in range(30):
        t0 = time.perf_counter()
        x, meta = letterbox(to_pil(f))
        t1 = time.perf_counter()
        out = et.run(x)
        t2 = time.perf_counter()
        postprocess(out, meta, (f.shape[1], f.shape[0]))
        t3 = time.perf_counter()
        for k, v in zip(ts, [t1 - t0, t2 - t1, t3 - t2]):
            ts[k].append(v * 1000)
    print("latency p50 (Mac CPU XNNPACK): " + " | ".join(f"{k} {sorted(v)[15]:.1f} ms" for k, v in ts.items()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pte", default="models/local/vision/yolo11n_xnnpack/model.pte")
    ap.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    ap.add_argument("--data", default="data/real")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--image", help="이미지 1장 검출 결과 출력")
    args = ap.parse_args()
    if args.compare:
        compare(args)
    elif args.image:
        for d in YoloET(args.pte)(cv2.imread(args.image), args.conf):
            print(d)


if __name__ == "__main__":
    main()
