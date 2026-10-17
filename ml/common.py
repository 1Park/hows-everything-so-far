from pathlib import Path

import numpy as np
import torch

# 전처리는 보드 Vision 서비스와 공유 (services/vision/preprocess.py)
from services.vision.preprocess import DINO_SIZE as IMG_SIZE, MEAN, STD  # noqa: F401
from services.vision.preprocess import dino_input as preprocess  # noqa: F401

MODELS = {
    "small": "facebook/dinov2-small",  # ViT-S/14, 22M, dim 384
    "base": "facebook/dinov2-base",  # ViT-B/14, 86M, dim 768
}


def load_dataset(root: str):
    """root/<class>/*.{png,jpg} → (paths, labels, class_names)"""
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = {
        d.name: sorted(p for p in d.iterdir() if p.suffix.lower() in exts)
        for d in Path(root).iterdir()
        if d.is_dir()
    }
    classes = sorted(c for c, fs in files.items() if fs)  # 빈 폴더(아직 안 찍은 클래스)는 제외
    paths, labels = [], []
    for ci, c in enumerate(classes):
        paths += files[c]
        labels += [ci] * len(files[c])
    return paths, np.array(labels), classes


def load_model(name: str, device: str):
    from transformers import AutoModel

    model = AutoModel.from_pretrained(MODELS[name]).eval().to(device)
    return model


class EmbeddingHead(torch.nn.Module):
    """백본 → 임베딩. ONNX/ExecuTorch export에도 이 래퍼를 쓴다.

    pool="cls": CLS 토큰 (D)  — 합성 데이터 실험에서 가장 좋았음
    pool="cls_mean": [CLS ; mean(patch)] (2D)
    """

    def __init__(self, backbone, pool: str = "cls"):
        super().__init__()
        self.backbone = backbone
        self.pool = pool

    def forward(self, pixel_values):
        h = self.backbone(pixel_values=pixel_values).last_hidden_state  # (B, 1+N, D), layernorm 적용됨
        if self.pool == "cls":
            return h[:, 0]
        return torch.cat([h[:, 0], h[:, 1:].mean(1)], dim=-1)
