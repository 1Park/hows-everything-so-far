"""Run a QNN .pte on the HTP simulator in the x86 container to check quantized-model accuracy without the board.

The container's ExecuTorch Python runtime has QnnBackend registered, and x86 QAIRT's libQnnHtp.so simulates the HTP.
It is slow (~3 s per YOLO run) -> keep the sample count small.

  ml/docker-run.sh python -m ml.evaluation.qnn_sim_check yolo   models/experiments/vision/qnn/SM8650_16a8w/yolo11n_qnn.pte
  ml/docker-run.sh python -m ml.evaluation.qnn_sim_check dinov2 models/experiments/vision/qnn/SM8650_16a8w/dinov2_small_cls_qnn.pte
"""

import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from executorch.runtime import Runtime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image  # noqa: E402

from services.vision.preprocess import dino_input, letterbox  # noqa: E402
from services.vision.yolo import postprocess  # noqa: E402


def load(pte):
    t = time.time()
    m = Runtime.get().load_program(Path(pte)).load_method("forward")
    print(f"loaded {pte} in {time.time() - t:.1f}s")
    return lambda x: m.execute([torch.from_numpy(x)])[0].numpy()


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def check_yolo(pte, n):
    from ml.export.export_qnn import build_yolo

    ref = build_yolo("models/local/vision/yolo11n.pt")
    run = load(pte)
    frames = sorted(Path(os.environ.get("SIM_FRAMES", "data/board_test")).glob("*.jpg"))[:n]
    same = matched = total = 0
    score_err, ts = [], []
    for f in frames:
        img = Image.open(f).convert("RGB")
        x, meta = letterbox(img)
        t = time.time()
        q = run(x)
        ts.append(time.time() - t)
        with torch.no_grad():
            r = ref(torch.from_numpy(x)).numpy()
        score_err.append(np.abs(q[:, 4:] - r[:, 4:]).max())
        rb = [d[0] for d in postprocess(r, meta, img.size)]
        qb = [d[0] for d in postprocess(q, meta, img.size)]
        same += len(rb) == len(qb)
        for b in rb:
            total += 1
            matched += any(box_iou(b, g) > 0.8 for g in qb)
        print(f"  {f.name}: fp32 boxes {len(rb)} | qnn boxes {len(qb)}")
    print(f"YOLO QNN(sim) vs fp32: same box count {same}/{len(frames)} | fp32 boxes matched (IoU>0.8) {matched}/{total}"
          f" | class score max|diff| {max(score_err):.3f} | sim {np.mean(ts):.1f}s/run")


def check_dinov2(pte, n):
    """Quantized vs fp32 embeddings: cosine + head accuracy (head trained on quantized embeddings / on fp32)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    from ml.export.export_qnn import build_dinov2

    ref = build_dinov2("facebook/dinov2-small")
    run = load(pte)
    root = Path("data/synthetic")
    classes = sorted(d.name for d in root.iterdir() if d.is_dir())
    rng = random.Random(0)
    paths, y = [], []
    for ci, c in enumerate(classes):
        fs = sorted((root / c).glob("*.png"))
        rng.shuffle(fs)
        paths += fs[:n]
        y += [ci] * len(fs[:n])
    y = np.array(y)
    Q, R, ts = [], [], []
    for p in paths:
        x = dino_input(Image.open(p))
        t = time.time()
        Q.append(run(x).reshape(-1))
        ts.append(time.time() - t)
        with torch.no_grad():
            R.append(ref(torch.from_numpy(x)).numpy().reshape(-1))
    Q, R = np.stack(Q), np.stack(R)
    cos = (Q * R).sum(1) / (np.linalg.norm(Q, axis=1) * np.linalg.norm(R, axis=1))
    print(f"DINOv2 QNN(sim) vs fp32 embedding cosine: mean {cos.mean():.4f}, min {cos.min():.4f} | sim {np.mean(ts):.1f}s/run")
    accs = {"fp32→fp32": [], "qnn→qnn": [], "fp32 head→qnn": []}
    srng = np.random.default_rng(0)
    k = n // 2
    for _ in range(10):
        tr = np.concatenate([srng.choice(np.where(y == c)[0], k, replace=False) for c in range(len(classes))])
        te = np.setdiff1d(np.arange(len(y)), tr)
        for name, (A, B) in {"fp32→fp32": (R, R), "qnn→qnn": (Q, Q), "fp32 head→qnn": (R, Q)}.items():
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.1)).fit(A[tr], y[tr])
            accs[name].append((clf.predict(B[te]) == y[te]).mean())
    print(f"head acc ({len(classes)} cls, {k}-shot train, {n - k}/cls test): "
          + " | ".join(f"{k_} {np.mean(v) * 100:.1f}%" for k_, v in accs.items()))
    Path("models/experiments/vision").mkdir(parents=True, exist_ok=True)
    np.savez("models/experiments/vision/qnn_sim_dinov2.npz", Q=Q, R=R, y=y, classes=np.array(classes))


if __name__ == "__main__":
    kind, pte = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else (8 if kind == "yolo" else 12)
    check_yolo(pte, n) if kind == "yolo" else check_dinov2(pte, n)
