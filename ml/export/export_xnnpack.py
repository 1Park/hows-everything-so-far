"""Stage B / CPU baseline: export the DINOv2 CLS embedding to an XNNPACK (CPU) .pte + compare outputs with PyTorch.

YOLO uses ultralytics' built-in export:  (cd models && ../python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='executorch')")
DINOv2:                              python -m ml.export.export_xnnpack
  → models/local/vision/dinov2_small_cls_xnnpack.pte  (input (1,3,224,224) common.preprocess, output (1,384), fp32)

An XNNPACK .pte built on the Mac also works as-is on the board (Linux aarch64), but the board runner must be built with
the XNNPACK backend (qnn_executor_runner may lack it -> check executor_runner or the Python binding).
"""

import argparse
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from ml.common import load_dataset, preprocess
from ml.export.export_qnn import build_dinov2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dinov2", default="facebook/dinov2-small")
    ap.add_argument("--out", default="models/local/vision/dinov2_small_cls_xnnpack.pte")
    args = ap.parse_args()

    from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner
    from executorch.exir import to_edge_transform_and_lower
    from executorch.runtime import Runtime

    model = build_dinov2(args.dinov2)
    paths, _, _ = load_dataset("data/real")
    xs = [torch.from_numpy(preprocess(Image.open(p))) for p in paths[:8]]

    prog = to_edge_transform_and_lower(
        torch.export.export(model, (xs[0],)), partitioner=[XnnpackPartitioner()]
    ).to_executorch()
    Path(args.out).write_bytes(prog.buffer)
    print(f"saved {args.out} ({Path(args.out).stat().st_size / 1e6:.1f} MB)")

    method = Runtime.get().load_program(Path(args.out)).load_method("forward")
    with torch.no_grad():
        ref = torch.cat([model(x) for x in xs]).numpy()
    got = np.concatenate([method.execute([x])[0].numpy() for x in xs])
    cos = (ref * got).sum(1) / (np.linalg.norm(ref, axis=1) * np.linalg.norm(got, axis=1))
    print(f"parity vs PyTorch: max|diff| {np.abs(ref - got).max():.2e}, cosine min {cos.min():.6f}")

    for _ in range(3):
        method.execute([xs[0]])
    ts = []
    for _ in range(20):
        t = time.perf_counter()
        method.execute([xs[0]])
        ts.append((time.perf_counter() - t) * 1000)
    print(f"latency p50 (Mac CPU XNNPACK fp32): {sorted(ts)[10]:.1f} ms")


if __name__ == "__main__":
    main()
