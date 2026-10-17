"""B단계/CPU 기준선: DINOv2 CLS 임베딩을 XNNPACK(CPU) .pte로 export + PyTorch와 출력 비교.

YOLO는 ultralytics 내장 export 사용:  (cd models && ../python -c "from ultralytics import YOLO; YOLO('yolo11n.pt').export(format='executorch')")
DINOv2:                              python -m ml.export.export_xnnpack
  → models/local/vision/dinov2_small_cls_xnnpack.pte  (입력 (1,3,224,224) common.preprocess, 출력 (1,384), fp32)

Mac에서 만든 XNNPACK .pte는 보드(Linux aarch64)에서도 그대로 쓸 수 있다. 단 보드 runner가 XNNPACK 백엔드를
포함해 빌드돼 있어야 한다 (qnn_executor_runner엔 없을 수 있음 → executor_runner 또는 Python 바인딩 확인).
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
