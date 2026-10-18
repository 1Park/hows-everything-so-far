"""DINOv2 backbone (+CLS pooling) -> ONNX. Used for uploading to Qualcomm AI Hub to profile on the QCS8275 NPU.

Input: pixel_values float32 (1,3,224,224), output of common.preprocess
Output: embedding float32 (1,D)  — small: 384, base: 768

Usage:
  python -m ml.export.export_onnx --model small
"""

import argparse
from pathlib import Path

import numpy as np
import torch

from ml.common import EmbeddingHead, load_model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small", choices=["small", "base"])
    ap.add_argument("--out", default="models/experiments/vision/onnx")
    ap.add_argument("--opset", type=int, default=17)
    args = ap.parse_args()

    head = EmbeddingHead(load_model(args.model, "cpu")).eval()
    x = torch.randn(1, 3, 224, 224)
    Path(args.out).mkdir(parents=True, exist_ok=True)
    path = Path(args.out) / f"dinov2_{args.model}_cls.onnx"
    torch.onnx.export(
        head, (x,), str(path), input_names=["pixel_values"], output_names=["embedding"],
        opset_version=args.opset, dynamo=False,
    )
    print(f"saved {path} ({path.stat().st_size / 1e6:.1f} MB)")

    try:
        import onnxruntime as ort
    except ImportError:
        print("onnxruntime not installed — skipping parity check (pip install onnxruntime)")
        return
    with torch.no_grad():
        ref = head(x).numpy()
    got = ort.InferenceSession(str(path)).run(None, {"pixel_values": x.numpy()})[0]
    cos = float((ref * got).sum() / (np.linalg.norm(ref) * np.linalg.norm(got)))
    print(f"parity vs PyTorch: max|diff|={np.abs(ref - got).max():.2e}, cosine={cos:.6f}")


if __name__ == "__main__":
    main()
