"""Local latency measurement (batch 1, 224x224, fp32).

Note: Mac M4 CPU/MPS numbers differ from VENTUNO Q (Hexagon NPU). Use them for relative comparison and a rough feel.
  --threads 4 is only a rough CPU baseline matching the board's big-core count (A78 x4); M4 cores are much faster.

Usage:
  python -m ml.evaluation.bench_latency --model small --devices cpu mps --threads 1 4
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import torch
from PIL import Image

from ml.common import EmbeddingHead, load_dataset, load_model, preprocess


def sync(device):
    if device == "mps":
        torch.mps.synchronize()


@torch.no_grad()
def bench(head, device, warmup, iters):
    x = torch.randn(1, 3, 224, 224, device=device)
    for _ in range(warmup):
        head(x)
    sync(device)
    ts = []
    for _ in range(iters):
        t0 = time.perf_counter()
        head(x)
        sync(device)
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    return dict(mean=statistics.mean(ts), p50=ts[len(ts) // 2], p90=ts[int(len(ts) * 0.9)])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small", choices=["small", "base"])
    ap.add_argument("--devices", nargs="+", default=["cpu", "mps"])
    ap.add_argument("--threads", type=int, nargs="+", default=[1, 4])
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--iters", type=int, default=100)
    ap.add_argument("--data", default="data/synthetic")
    args = ap.parse_args()

    rows = []
    # Preprocessing (PIL resize/crop/normalize) — runs on the CPU on the board too
    paths, _, _ = load_dataset(args.data)
    imgs = [Image.open(p).copy() for p in paths[:50]]
    t0 = time.perf_counter()
    for im in imgs:
        preprocess(im)
    pre_ms = (time.perf_counter() - t0) * 1000 / len(imgs)
    print(f"preprocess (PIL, 320px→224): {pre_ms:.2f} ms/img")

    for device in args.devices:
        if device == "mps" and not torch.backends.mps.is_available():
            continue
        head = EmbeddingHead(load_model(args.model, device)).eval()
        for th in args.threads if device == "cpu" else [None]:
            if th:
                torch.set_num_threads(th)
            r = bench(head, device, args.warmup, args.iters)
            label = f"{device}" + (f" x{th} threads" if th else "")
            print(f"{args.model:5} {label:16} mean {r['mean']:7.2f} ms | p50 {r['p50']:7.2f} | p90 {r['p90']:7.2f}")
            rows.append(dict(model=args.model, device=device, threads=th, **r))

    Path("models/experiments/vision").mkdir(parents=True, exist_ok=True)
    out = Path(f"models/experiments/vision/latency_{args.model}.json")
    out.write_text(json.dumps(dict(preprocess_ms=pre_ms, runs=rows), indent=2))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
