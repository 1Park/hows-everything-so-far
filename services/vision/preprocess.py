"""Vision 전처리 — numpy + Pillow만 사용 (보드 서비스에 torch/OpenCV 불필요).

ml/ 의 export·calibration·평가 코드도 이 함수를 그대로 import 한다 → 학습/양자화/보드 추론 전처리가 항상 같다.
"""

import numpy as np
from PIL import Image

# DINOv2: 짧은 변 256 bicubic → 224 center crop → ImageNet mean/std, NCHW float32
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)
DINO_SIZE = 224
# YOLO11n export 입력 (ultralytics letterbox와 같은 규칙: 비율 유지 + 회색 114 패딩, RGB 0~1)
YOLO_SIZE = 640


def dino_input(img: Image.Image) -> np.ndarray:
    """PIL → (1,3,224,224) float32, 연속 메모리 (stride 0이면 ExecuTorch export/raw 파일이 깨진다)."""
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
    """PIL → (1,3,640,640) float32 RGB 0~1, 그리고 원본 좌표 복원용 (scale, pad_x, pad_y)."""
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
    """가운데 정사각형 (x, y, side) — ml/tools/camera.py collect 의 학습 crop 규칙."""
    w, h = size_wh
    s = int(min(h, w) * frac)
    return (w - s) // 2, (h - s) // 2, s


def square_crop_box(xyxy, size_wh, scale):
    """박스 → 중심이 같은 정사각형으로 scale배 확장 (x, y, side). 학습 crop처럼 컵 주변 여백을 남긴다.

    scale 1.35 = 학습 crop 크기 / 컵 검출 박스 크기의 중앙값 (실사 jar 사진에서 측정).
    """
    x0, y0, x1, y1 = xyxy
    w, h = size_wh
    s = min(max(x1 - x0, y1 - y0) * scale, h, w)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    x = int(np.clip(cx - s / 2, 0, w - s))
    y = int(np.clip(cy - s / 2, 0, h - s))
    return x, y, int(s)
