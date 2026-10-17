"""YOLO11n / DINOv2(CLS 임베딩) → QCS8275 QNN HTP .pte (A단계, NPU).

QNN Python 바인딩(PyQnnManagerAdaptor)이 x86-64 전용 → Mac에선 Docker linux/amd64 컨테이너에서 실행한다.
컨테이너 안 ExecuTorch 1.5.1 이 QAIRT SDK를 자동으로 받는다 (ml/Dockerfile, ml/docker-run.sh).

  ml/docker-run.sh python -m ml.export.export_qnn --model yolo   --soc_model QCS8275 --build_folder /tmp --compile_only
  ml/docker-run.sh python -m ml.export.export_qnn --model dinov2 --quant fp16 --soc_model QCS8275 --build_folder /tmp --compile_only
  → models/experiments/vision/qnn/<soc>_<quant>/{yolo11n,dinov2_small_cls}_qnn.pte (+ *_io.json 입출력 규격)

- 일반 ExecuTorch 1.5.1 에는 QCS8275 타깃이 없다 → 주최 측 보드 checkout/SDK 로 실행해야 한다 (ml/export/README.md).
  같은 HTP v75 인 SM8650 으로 export 하면 파이프라인 리허설만 된다 (보드 배포용 아님).
- 양자화: YOLO 16a8w 기본. DINOv2 는 16a8w에서 fp32 대비 cosine 0.58 → fp16 우선 (cosine 0.9992), 16a16w 는 망가짐.
- 만든 .pte 는 컨테이너의 HTP 시뮬레이터로 보드 없이 검증: python -m ml.evaluation.qnn_sim_check
- 가이드 DINOv2 예제(examples/qualcomm/oss_scripts/dino_v2.py)와 같은 build_executorch_binary 경로.
  예제는 Dinov2ForImageClassification(ImageNet 1000 logits), 여기선 CLS 임베딩(384) 출력.

Mac 네이티브(Docker 없이)는 --dry-run 만: torch.export 캡처 + XNNPACK int8 근사로 양자화 민감도 확인.
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
    """ultralytics Exporter와 같은 준비: fuse + Detect.export=True → 출력 (1,84,8400) 단일 텐서."""
    from ultralytics import YOLO
    from ultralytics.nn.modules import Detect

    model = YOLO(weights).model.float().eval().fuse()
    for m in model.modules():
        if isinstance(m, Detect):
            m.export, m.dynamic, m.format = True, False, "executorch"
    # 640 고정 입력으로 한 번 실행 → Detect가 anchors/strides를 캐시(self.shape 일치)해서 export 그래프엔 상수로만 남는다.
    # 안 하면 make_anchors의 torch.full(fill_value=stride Node)이 그래프에 남아 QNN partitioner가 실패.
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
    """HF Dinov2Embeddings를 224 고정 입력용으로 바꾼 것 (export 전용, 출력은 원본과 동일).

    - 위치 임베딩 bicubic 보간(37x37 → 16x16)을 미리 계산해 상수로 → 그래프에서 interpolate 제거 (HTP 미지원 가능)
    - cls_token.expand → repeat : expand는 stride 0 텐서라 ExecuTorch가 거부함
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
    """export용 DINOv2: embeddings → 레이어 12개 → layernorm → CLS.

    Dinov2Model.forward를 거치지 않는 이유: transformers 5는 마스크가 없어도 그래프 안에서
    (1,1,257,257) 어텐션 마스크를 expand(stride 0)로 만들고, ExecuTorch가 이를 거부한다.
    """

    def __init__(self, backbone):
        super().__init__()
        self.embeddings = FixedEmbeddings(backbone.embeddings)
        self.layers = backbone.encoder.layer
        self.layernorm = backbone.layernorm

    def forward(self, pixel_values):
        h = self.embeddings(pixel_values)
        for layer in self.layers:
            # transformers 5.15(보드)는 forward(hidden_states)만, 5.20(Mac)은 attention_mask 선택 인자 — 위치 인자 1개로 호출
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
    assert diff < 1e-4, f"export용 DINOv2 출력이 원본과 다름: {diff}"
    return model


def calib_inputs(model_kind, dirs, n, seed=0):
    """양자화 calibration용 실제 입력. 데모 환경과 비슷한 사진일수록 좋다 (평가용과 분리 권장)."""
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
        raise SystemExit(f"calibration 이미지 없음: {dirs}")
    return out


def dry_run(model, data, kind):
    """Mac: torch.export 캡처 확인 + XNNPACK int8 PTQ로 양자화 민감도 근사 (QNN 8a8w와 같지는 않음)."""
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
        print("          (박스 좌표 0~640과 점수 0~1이 한 텐서라 8bit에선 점수 해상도가 떨어짐 → 16a8w 권장)")
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
                    help="16a8w(기본) / 16a16w(정확도 우선) / 8a8w(가장 빠름) / fp16(SoC가 지원할 때만)")
    ap.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    ap.add_argument("--dinov2", default="facebook/dinov2-small")
    ap.add_argument("--calib", nargs="+", default=["data/real", "data/synthetic"])
    ap.add_argument("--n-calib", type=int, default=64)
    ap.add_argument("--artifact", help="기본: models/experiments/vision/qnn/<soc>_<quant>")
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
        raise SystemExit(f"이 checkout에 {args.soc_model} 타깃이 없음 — 보드 지원 checkout/SDK를 써야 함 (가이드 Troubleshooting)")
    Path(args.artifact).mkdir(parents=True, exist_ok=True)
    quant_dtype = {"16a8w": QuantDtype.use_16a8w, "16a16w": QuantDtype.use_16a16w, "8a8w": QuantDtype.use_8a8w,
                   "fp16": None}[args.quant]
    qnn_config = QnnConfig.load_config(args.config_file if args.config_file else args)
    Path(args.artifact, f"{name}_io.json").write_text(json.dumps(io, indent=2, ensure_ascii=False))
    # compile_only면 build_executorch_binary 안에서 .pte 저장 후 sys.exit(0)
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
