"""YOLO11n / DINOv2 (CLS embedding) -> QCS8275 QNN HTP .pte (stage A, NPU).

The QNN Python binding (PyQnnManagerAdaptor) is x86-64 only -> on the Mac, run in a Docker linux/amd64 container.
ExecuTorch 1.5.1 inside the container downloads the QAIRT SDK automatically (ml/Dockerfile, ml/docker-run.sh).

  ml/docker-run.sh python -m ml.export.export_qnn --model yolo   --soc_model QCS8275 --build_folder /tmp --compile_only
  ml/docker-run.sh python -m ml.export.export_qnn --model dinov2 --quant fp16 --soc_model QCS8275 --build_folder /tmp --compile_only
  → models/experiments/vision/qnn/<soc>_<quant>/{yolo11n,dinov2_small_cls}_qnn.pte (+ *_io.json I/O spec)

- Stock ExecuTorch 1.5.1 has no QCS8275 target -> run with the organizers' board checkout/SDK (ml/export/README.md).
  Exporting for SM8650 (same HTP v75) only rehearses the pipeline (not for board deployment).
- Quantization: YOLO defaults to 16a8w. DINOv2 at 16a8w gets cosine 0.58 vs fp32 -> prefer fp16 (cosine 0.9992); 16a16w breaks it.
- Check the resulting .pte without the board on the container's HTP simulator: python -m ml.evaluation.qnn_sim_check
- Same build_executorch_binary path as the guide's DINOv2 example (examples/qualcomm/oss_scripts/dino_v2.py).
  The example uses Dinov2ForImageClassification (ImageNet 1000 logits); here we output the CLS embedding (384).

Native Mac (no Docker) supports --dry-run only: torch.export capture + XNNPACK int8 approximation to gauge quantization sensitivity.
  python -m ml.export.export_qnn --model dinov2 --dry-run
"""

import argparse
import json
import random
import sys
from pathlib import Path

import torch
from PIL import Image

from ml.common import EmbeddingHead, preprocess

QUANT = ["16a8w", "16a16w", "8a8w", "fp16"]


def build_yolo(weights):
    """Same prep as the ultralytics Exporter: fuse + Detect.export=True -> single (1,84,8400) output tensor."""
    from ultralytics import YOLO
    from ultralytics.nn.modules import Detect

    model = YOLO(weights).model.float().eval().fuse()
    for m in model.modules():
        if isinstance(m, Detect):
            m.export, m.dynamic, m.format = True, False, "executorch"
    # Run once with a fixed 640 input -> Detect caches anchors/strides (self.shape matches),
    # so they stay constants in the export graph. Otherwise make_anchors' torch.full
    # (fill_value=stride Node) stays in the graph and the QNN partitioner fails.
    with torch.no_grad():
        model(torch.zeros(1, 3, 640, 640))

    class Wrap(torch.nn.Module):
        def __init__(self, m):
            super().__init__()
            self.m = m

        def forward(self, x):
            y = self.m(x)
            return y[0] if isinstance(y, (list, tuple)) else y

    return Wrap(model).eval()


class FixedEmbeddings(torch.nn.Module):
    """HF Dinov2Embeddings adapted for a fixed 224 input (export only, output identical to the original).

    - Precompute the bicubic position-embedding interpolation (37x37 -> 16x16) as a constant
      -> no interpolate in the graph (HTP may not support it)
    - cls_token.expand -> repeat: expand yields a stride-0 tensor, which ExecuTorch rejects
    """

    def __init__(self, emb, size=224):
        super().__init__()
        self.patch_embeddings = emb.patch_embeddings
        self.cls_token = emb.cls_token
        n = (size // emb.patch_size) ** 2
        with torch.no_grad():
            dummy = torch.zeros(1, 1 + n, emb.cls_token.shape[-1])
            self.register_buffer("pos", emb.interpolate_pos_encoding(dummy, size, size).clone())

    def forward(self, pixel_values, bool_masked_pos=None):
        x = self.patch_embeddings(pixel_values)
        cls = self.cls_token.repeat(x.shape[0], 1, 1)
        return torch.cat([cls, x], dim=1) + self.pos


class Dinov2CLS(torch.nn.Module):
    """DINOv2 for export: embeddings -> 12 layers -> layernorm -> CLS.

    Why we skip Dinov2Model.forward: even without a mask, transformers 5 builds a (1,1,257,257)
    attention mask with expand (stride 0) inside the graph, and ExecuTorch rejects it.
    """

    def __init__(self, backbone):
        super().__init__()
        self.embeddings = FixedEmbeddings(backbone.embeddings)
        self.layers = backbone.encoder.layer
        self.layernorm = backbone.layernorm

    def forward(self, pixel_values):
        h = self.embeddings(pixel_values)
        for layer in self.layers:
            # transformers 5.15 (board) takes forward(hidden_states) only, 5.20 (Mac) adds an optional
            # attention_mask — call with one positional arg
            out = layer(h)
            h = out[0] if isinstance(out, tuple) else out
        return self.layernorm(h)[:, 0]


def build_dinov2(name):
    from transformers import AutoModel

    backbone = AutoModel.from_pretrained(name, attn_implementation="eager").eval()
    x = torch.randn(2, 3, 224, 224, generator=torch.Generator().manual_seed(0))
    model = Dinov2CLS(backbone).eval()
    with torch.no_grad():
        diff = (model(x) - EmbeddingHead(backbone)(x)).abs().max().item()
    assert diff < 1e-4, f"export DINOv2 output differs from the original: {diff}"
    return model


def calib_inputs(model_kind, dirs, n, seed=0):
    """Real inputs for quantization calibration. Photos closer to the demo setting work better
    (keep them separate from eval data)."""
    from services.vision.preprocess import letterbox

    paths = [p for d in dirs for p in sorted(Path(d).glob("*/*")) if p.suffix.lower() in {".jpg", ".png", ".jpeg"}]
    random.Random(seed).shuffle(paths)
    out = []
    for p in paths[:n]:
        if model_kind == "yolo":
            x, _ = letterbox(Image.open(p))
        else:
            x = preprocess(Image.open(p))
        out.append((torch.from_numpy(x),))
    if not out:
        raise SystemExit(f"no calibration images: {dirs}")
    return out


def dry_run(model, data, kind):
    """Mac: check torch.export capture + approximate quantization sensitivity with XNNPACK int8 PTQ (not the same as QNN 8a8w)."""
    from executorch.backends.xnnpack.quantizer.xnnpack_quantizer import (
        XNNPACKQuantizer,
        get_symmetric_quantization_config,
    )
    from torchao.quantization.pt2e.quantize_pt2e import convert_pt2e, prepare_pt2e

    sample = data[0]
    ep = torch.export.export(model, sample, strict=False)
    print(f"[dry-run] torch.export OK: {len(ep.graph.nodes)} nodes, output {tuple(model(*sample).shape)}")

    q = XNNPACKQuantizer().set_global(get_symmetric_quantization_config(is_per_channel=True))
    m = prepare_pt2e(ep.module(), q)
    for d in data:
        m(*d)
    m = convert_pt2e(m)
    with torch.no_grad():
        ref = torch.cat([model(*d) for d in data])
        got = torch.cat([m(*d) for d in data])
    if kind == "dinov2":
        cos = torch.nn.functional.cosine_similarity(ref, got, dim=1)
        print(f"[dry-run] int8 sim vs fp32 embedding cosine: mean {cos.mean():.4f}, min {cos.min():.4f}")
    else:
        box_err = (ref[:, :4] - got[:, :4]).abs().mean().item()
        score_err = (ref[:, 4:] - got[:, 4:]).abs().max().item()
        print(f"[dry-run] int8 sim: box coord mean|diff| {box_err:.2f}px, class score max|diff| {score_err:.3f}")
        print("          (box coords 0-640 and scores 0-1 share one tensor, so 8-bit loses score resolution -> use 16a8w)")
    return m


def main():
    from_qnn = "--dry-run" not in sys.argv
    if from_qnn:
        from executorch.backends.qualcomm.export_utils import (
            QnnConfig,
            build_executorch_binary,
            setup_common_args_and_variables,
        )

        ap = setup_common_args_and_variables()
    else:
        ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["yolo", "dinov2"], required=True)
    ap.add_argument("--quant", choices=QUANT, default="16a8w",
                    help="16a8w (default) / 16a16w (accuracy first) / 8a8w (fastest) / fp16 (only if the SoC supports it)")
    ap.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    ap.add_argument("--dinov2", default="facebook/dinov2-small")
    ap.add_argument("--calib", nargs="+", default=["data/real", "data/synthetic"])
    ap.add_argument("--n-calib", type=int, default=64)
    ap.add_argument("--artifact", help="default: models/experiments/vision/qnn/<soc>_<quant>")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    model = build_yolo(args.weights) if args.model == "yolo" else build_dinov2(args.dinov2)
    data = calib_inputs(args.model, args.calib, args.n_calib)
    name = "yolo11n_qnn" if args.model == "yolo" else "dinov2_small_cls_qnn"
    io = dict(
        model=args.model, quant=args.quant, input_shape=list(data[0][0].shape), input_dtype="float32",
        preprocess="services.vision.preprocess.letterbox (RGB 0~1, 114 pad, 640)" if args.model == "yolo"
        else "services.vision.preprocess.dino_input (short side 256 bicubic → center crop 224 → ImageNet mean/std)",
        output="(1,84,8400) cx,cy,w,h + 80 COCO scores" if args.model == "yolo" else "(1,384) CLS embedding",
    )

    if not args.dry_run and not args.artifact:
        args.artifact = f"models/experiments/vision/qnn/{args.soc_model}_{args.quant}"
    if args.dry_run:
        dry_run(model, data, args.model)
        return

    from executorch.backends.qualcomm.quantizer.quantizer import QuantDtype
    from executorch.backends.qualcomm.utils.utils import get_soc_to_chipset_map

    if args.soc_model not in get_soc_to_chipset_map():
        raise SystemExit(f"no {args.soc_model} target in this checkout — use a checkout/SDK with board support (guide Troubleshooting)")
    Path(args.artifact).mkdir(parents=True, exist_ok=True)
    quant_dtype = {"16a8w": QuantDtype.use_16a8w, "16a16w": QuantDtype.use_16a16w, "8a8w": QuantDtype.use_8a8w,
                   "fp16": None}[args.quant]
    qnn_config = QnnConfig.load_config(args.config_file if args.config_file else args)
    Path(args.artifact, f"{name}_io.json").write_text(json.dumps(io, indent=2, ensure_ascii=False))
    # with compile_only, build_executorch_binary saves the .pte and calls sys.exit(0)
    build_executorch_binary(
        model=model,
        qnn_config=qnn_config,
        file_name=f"{args.artifact}/{name}",
        dataset=data,
        quant_dtype=quant_dtype,
    )
    print(f"saved {args.artifact}/{name}.pte")


if __name__ == "__main__":
    main()
