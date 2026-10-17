"""YOLO11n .pte 후처리 — numpy만 (ultralytics 불필요).

.pte 출력 (ultralytics Detect export 모드, 디코드 포함):
  (1, 84, 8400) = [cx, cy, w, h (640 입력 픽셀), COCO 80클래스 점수(sigmoid)] × 앵커 8400
"""

import numpy as np

# COCO에서 컵으로 인정할 클래스. 실사 jar는 cup/vase/bowl로 섞여 나와 이름은 믿지 않고 "컵 비슷하면 컵"으로 본다.
GLASS_IDS = {39: "bottle", 40: "wine glass", 41: "cup", 45: "bowl", 75: "vase"}


def nms(boxes, scores, iou_th):
    """클래스 무시(agnostic) NMS. boxes xyxy (N,4) → 남길 index."""
    order = scores.argsort()[::-1]
    keep = []
    area = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    while order.size:
        i = order[0]
        keep.append(i)
        xx0 = np.maximum(boxes[i, 0], boxes[order[1:], 0])
        yy0 = np.maximum(boxes[i, 1], boxes[order[1:], 1])
        xx1 = np.minimum(boxes[i, 2], boxes[order[1:], 2])
        yy1 = np.minimum(boxes[i, 3], boxes[order[1:], 3])
        inter = np.clip(xx1 - xx0, 0, None) * np.clip(yy1 - yy0, 0, None)
        iou = inter / (area[i] + area[order[1:]] - inter + 1e-9)
        order = order[1:][iou < iou_th]
    return keep


def postprocess(out, meta, size_wh, conf=0.25, iou=0.7, glass_only=True):
    """(1,84,8400) → [(xyxy 원본 픽셀, score, class_name)], score 내림차순.

    NMS는 모든 클래스 박스로 먼저 하고 컵 클래스는 그 뒤에 거른다 (= ultralytics agnostic_nms).
    같은 컵에 cup/vase 이중 박스가 나오는 것을 막는다.
    """
    p = np.asarray(out).reshape(84, -1).T  # (8400, 84)
    cls_scores = p[:, 4:]
    cls = cls_scores.argmax(1)
    score = cls_scores[np.arange(len(p)), cls]
    m = score >= conf
    p, cls, score = p[m], cls[m], score[m]
    if not len(p):
        return []
    cx, cy, w, h = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1)
    s, px, py = meta
    fw, fh = size_wh
    dets = []
    for i in nms(boxes, score, iou):
        if glass_only and int(cls[i]) not in GLASS_IDS:
            continue
        x0, y0, x1, y1 = boxes[i]
        x0, x1 = np.clip([(x0 - px) / s, (x1 - px) / s], 0, fw)
        y0, y1 = np.clip([(y0 - py) / s, (y1 - py) / s], 0, fh)
        if x1 > x0 and y1 > y0:
            dets.append(((float(x0), float(y0), float(x1), float(y1)), float(score[i]),
                         GLASS_IDS.get(int(cls[i]), str(int(cls[i])))))
    return dets
