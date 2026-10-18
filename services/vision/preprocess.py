"""Vision preprocessing — numpy + Pillow only (the board service needs no torch/OpenCV).

Export, calibration and evaluation code under ml/ imports these same functions, so training,
quantization and board inference always share one preprocessing.
"""

import numpy as np
from PIL import Image

# DINOv2: short side 256 bicubic → 224 center crop → ImageNet mean/std, NCHW float32
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
DINO_SIZE = 224
# YOLO11n export input (same rule as ultralytics letterbox: keep aspect + gray 114 padding, RGB 0~1)
YOLO_SIZE = 640


def dino_input(img: Image.Image) -> np.ndarray:
    """PIL → (1,3,224,224) float32, contiguous (stride 0 breaks ExecuTorch export/raw files)."""
    img = img.convert("RGB")
    w, h = img.size
    s = 256 / min(w, h)
    img = img.resize((round(w * s), round(h * s)), Image.BICUBIC)
    w, h = img.size
    left, top = (w - DINO_SIZE) // 2, (h - DINO_SIZE) // 2
    img = img.crop((left, top, left + DINO_SIZE, top + DINO_SIZE))
    x = (np.asarray(img, np.float32) / 255.0 - MEAN) / STD
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None])


def letterbox(img: Image.Image, size: int = YOLO_SIZE):
    """PIL → (1,3,640,640) float32 RGB 0~1, plus (scale, pad_x, pad_y) to map back to original coordinates."""
    img = img.convert("RGB")
    w, h = img.size
    s = min(size / h, size / w)
    nw, nh = round(w * s), round(h * s)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (px, py))
    x = np.asarray(canvas, np.float32).transpose(2, 0, 1)[None] / 255.0
    return np.ascontiguousarray(x), (s, px, py)


def center_box(size_wh, frac=0.7):
    """Center square (x, y, side) — the training crop rule from ml/tools/camera.py collect."""
    w, h = size_wh
    s = int(min(h, w) * frac)
    return (w - s) // 2, (h - s) // 2, s


def pad_crop(img: Image.Image, xyxy, margin=1.15, fill=(114, 114, 114)) -> Image.Image:
    """Crop the box widened by margin only, and fill the rest of the square with gray (YOLO mode
    default).

    Widening to a square pulls neighboring cups into the crop for tall cans/bottles or objects at the
    frame edge, and classification follows the neighbor (measured: coffee cup next to a can → can
    classified as coffee). Padding puts gray there instead, and pinning the box center to the
    square's center keeps it from shifting at the edges too.
    """
    x0, y0, x1, y1 = xyxy
    W, H = img.size
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w2, h2 = (x1 - x0) * margin, (y1 - y0) * margin
    left, top = max(0, int(cx - w2 / 2)), max(0, int(cy - h2 / 2))
    right, bottom = min(W, int(cx + w2 / 2)), min(H, int(cy + h2 / 2))
    side = max(1, int(max(w2, h2)))
    canvas = Image.new("RGB", (side, side), fill)
    canvas.paste(img.crop((left, top, right, bottom)), (int(side / 2 - (cx - left)), int(side / 2 - (cy - top))))
    return canvas


def square_crop_box(xyxy, size_wh, scale):
    """Box → concentric square scaled by scale (x, y, side). Leaves a margin around the cup, like
    the training crops.

    scale 1.35 = median of training crop size / detected cup box size (measured on real jar photos).
    """
    x0, y0, x1, y1 = xyxy
    w, h = size_wh
    s = min(max(x1 - x0, y1 - y0) * scale, h, w)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x = int(np.clip(cx - s / 2, 0, w - s))
    y = int(np.clip(cy - s / 2, 0, h - s))
    return x, y, int(s)
