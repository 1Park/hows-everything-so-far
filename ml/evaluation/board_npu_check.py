"""Runs a QNN .pte on the board (VENTUNO Q) with qnn_executor_runner (NPU), compares it with fp32 PyTorch, and reports latency.

Run from the repo root inside the organizers' ExecuTorch venv on the board (docs/board-installation-20261017.md "Board ExecuTorch installation record"):
  source ~/git/executorch/.venv/bin/activate
  PYTHONPATH=$HOME/git:$PWD python -m ml.evaluation.board_npu_check dinov2 --pte ~/model_output/vision/dinov2_small_cls_qnn.pte --images data/calib
  PYTHONPATH=$HOME/git:$PWD python -m ml.evaluation.board_npu_check yolo   --pte ~/model_output/vision/yolo11n_qnn.pte --images data/calib/scenes

Measured 2026-10-17: DINOv2 fp16 5.8 ms, cosine 0.9994 vs fp32 / YOLO11n 16a8w 16.3 ms, 19/21 fp32 boxes matched (IoU>0.8).
"""

import argparse
import os
import re
import subprocess
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ml.export.export_qnn import build_dinov2, build_yolo
from services.vision.preprocess import dino_input, letterbox
from services.vision.yolo import postprocess

ET = Path(os.environ.get("EXECUTORCH_ROOT", Path.home() / "git/executorch"))
RUNNER = Path(os.environ.get("QNN_EXECUTOR_RUNNER", ET / "build-x86/examples/qualcomm/executor_runner/qnn_executor_runner"))


def run_npu(pte, xs, work):
    """xs (list of NCHW float32) -> one runner call (one input_list line = one inference) -> output list, log."""
    work.mkdir(parents=True, exist_ok=True)
    out = work / "outputs"
    out.mkdir(exist_ok=True)
    for f in out.glob("*.raw"):
        f.unlink()
    lines = []
    for i, x in enumerate(xs):
        f = work / f"input_{i}_0.raw"
        np.ascontiguousarray(x, dtype=np.float32).tofile(f)
        lines.append(str(f))
    (work / "input_list.txt").write_text("\n".join(lines) + "\n")
    env = dict(os.environ, LD_LIBRARY_PATH=f"{ET}/build-x86/backends/qualcomm:/usr/lib", ADSP_LIBRARY_PATH="/usr/lib")
    r = subprocess.run([str(RUNNER), "--model_path", str(pte), "--input_list_path", str(work / "input_list.txt"),
                        "--output_folder_path", str(out)], cwd=work, env=env, capture_output=True, text=True)
    log = r.stdout + r.stderr
    if r.returncode != 0:
        raise SystemExit(f"runner failed (exit {r.returncode})\n{log[-2000:]}")
    total = [m.group(0) for m in re.finditer(r"Total \d+ inference took [\d.]+ ms, avg [\d.]+ ms", log)]
    return [np.fromfile(out / f"output_{i}_0.raw", np.float32) for i in range(len(xs))], (total[-1] if total else "")


def box_iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def images(root, limit):
    ps = sorted(p for p in Path(root).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    return ps[:: max(1, len(ps) // limit)][:limit]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=["dinov2", "yolo"])
    ap.add_argument("--pte", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    ap.add_argument("--work", default=str(Path.home() / "model_output/npu-check"))
    args = ap.parse_args()
    ps = images(args.images, args.limit)
    pil = [Image.open(p).convert("RGB") for p in ps]
    if args.model == "dinov2":
        xs = [dino_input(im) for im in pil]
        Q, timing = run_npu(args.pte, xs, Path(args.work) / "dinov2")
        ref = build_dinov2("facebook/dinov2-small")
        with torch.no_grad():
            R = [ref(torch.from_numpy(x)).numpy().reshape(-1) for x in xs]
        Q, R = np.stack(Q), np.stack(R)
        cos = (Q * R).sum(1) / (np.linalg.norm(Q, axis=1) * np.linalg.norm(R, axis=1))
        print(f"{len(xs)} imgs | {timing} | NPU vs fp32 cosine mean {cos.mean():.4f}, min {cos.min():.4f}")
        return
    lb = [letterbox(im) for im in pil]
    Q, timing = run_npu(args.pte, [x for x, _ in lb], Path(args.work) / "yolo")
    ref = build_yolo(args.weights)
    same = matched = total = 0
    for im, (x, meta), q in zip(pil, lb, Q):
        with torch.no_grad():
            f = ref(torch.from_numpy(x)).numpy()
        qb = [d[0] for d in postprocess(q.reshape(1, 84, -1), meta, im.size)]
        fb = [d[0] for d in postprocess(f, meta, im.size)]
        same += len(qb) == len(fb)
        for b in fb:
            total += 1
            matched += any(box_iou(b, g) > 0.8 for g in qb)
    print(f"{len(pil)} imgs | {timing} | same box count {same}/{len(pil)} | fp32 boxes matched (IoU>0.8) {matched}/{total}")


if __name__ == "__main__":
    main()
