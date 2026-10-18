from pathlib import Path

import numpy as np
import torch

# Preprocessing is shared with the board Vision service (services/vision/preprocess.py)
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
    classes = sorted(c for c, fs in files.items() if fs)  # skip empty folders (classes not photographed yet)
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
    """Backbone -> embedding. ONNX/ExecuTorch export uses this wrapper too.

    pool="cls": CLS token (D)  — best in the synthetic-data experiments
    pool="cls_mean": [CLS ; mean(patch)] (2D)
    """

    def __init__(self, backbone, pool: str = "cls"):
        super().__init__()
        self.backbone = backbone
        self.pool = pool

    def forward(self, pixel_values):
        h = self.backbone(pixel_values=pixel_values).last_hidden_state  # (B, 1+N, D), layernorm already applied
        if self.pool == "cls":
            return h[:, 0]
        return torch.cat([h[:, 0], h[:, 1:].mean(1)], dim=-1)
