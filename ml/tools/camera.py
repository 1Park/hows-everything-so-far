"""Collect real photos / run live inference + measure latency with the MacBook (or USB) camera.

The square box in the center of the screen = ROI (the spec's primary ROI). Place the glass inside the box and shoot.

1) Collect:  python -m ml.tools.camera collect --drinks water coke coffee
          python -m ml.tools.camera collect --classes other   (non-cup objects: cans, bottles)
   keys: 1-9,0 select class (10th = 0) | space save | q quit   → data/real/<class>/NNNN.jpg
2) Accuracy: python -m ml.evaluation.eval_fewshot --data data/real --shots 1 3 5
3) Live: python -m ml.tools.camera live --train data/real            (one center ROI)
          python -m ml.tools.camera live --train data/real --detect   (YOLO finds several glasses, classify each)
          python -m ml.tools.camera rois                              (mark glass spots with the mouse → rois.json)
          python -m ml.tools.camera live --train data/real --rois rois.json   (several fixed ROIs, no detector)
   keys: q quit   → models/experiments/vision/live_latency_*.json (per-frame stage ms stats)

macOS: run from iTerm/Terminal.app so the permission popup appears (not the Claude app terminal panel).
With several cameras: python -m ml.tools.camera probe
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.common import EmbeddingHead, load_dataset, load_model, preprocess
from ml.evaluation.eval_fewshot import embed_all

from services.vision.preprocess import center_box
from services.vision.preprocess import square_crop_box as _square_crop_box


def roi_box(frame, frac=0.7):
    """cv2 frame -> center square (x, y, side). Same rule as the service's center_box."""
    return center_box((frame.shape[1], frame.shape[0]), frac)


def square_crop_box(xyxy, frame, scale):
    return _square_crop_box(xyxy, (frame.shape[1], frame.shape[0]), scale)


def load_rois(path):
    """rois.json: {"rois": [[x, y, w, h], ...]} as fractions of the frame (0-1)."""
    return json.loads(Path(path).read_text())["rois"]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Tracks:
    """For the live view: match the same cup across frames by IoU and EMA its probabilities -> no label flicker.
    (The Vision service works per scene, so it does not track)"""

    def __init__(self, alpha=0.4, iou_min=0.3, max_miss=5):
        self.alpha, self.iou_min, self.max_miss = alpha, iou_min, max_miss
        self.tracks = []
        self.next_id = 0

    def update(self, boxes, probs):
        out = []
        free = list(range(len(self.tracks)))
        for box, p in zip(boxes, probs):
            best, best_iou = None, self.iou_min
            for ti in free:
                v = iou(box, self.tracks[ti]["box"])
                if v > best_iou:
                    best, best_iou = ti, v
            if best is None:
                t = dict(id=self.next_id, box=box, prob=p, miss=0)
                self.next_id += 1
                self.tracks.append(t)
            else:
                free.remove(best)
                t = self.tracks[best]
                t.update(box=box, prob=self.alpha * p + (1 - self.alpha) * t["prob"], miss=0)
            out.append(t)
        for ti in free:
            self.tracks[ti]["miss"] += 1
        self.tracks = [t for t in self.tracks if t["miss"] <= self.max_miss]
        return out


LEVELS = ["full", "mid", "low"]
KEYS = "1234567890"  # class select keys (up to 10 classes = 3 drinks × 3 levels + empty)
GLASS_LIKE = {"cup", "wine glass", "bottle", "bowl", "vase"}  # COCO classes accepted as a glass


def crop_roi(frame):
    x, y, s = roi_box(frame)
    return frame[y : y + s, x : x + s]


def put(img, text, y, color=(255, 255, 255), scale=0.7, x=12):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


CAM_HELP = """Cannot open the camera.
  1) Make sure you ran it from Terminal.app/iTerm (the Claude app terminal panel does not show the macOS permission popup)
     → double-clicking collect.command in Finder runs it in Terminal.app
  2) System Settings > Privacy & Security > Camera: enable Terminal → restart Terminal
  3) With several cameras (e.g. iPhone Continuity Camera): find the index with python -m ml.tools.camera probe, then --cam N"""


def open_cam(idx, retries=10):
    # macOS: the permission request on first run is async, so the first open fails -> retry while waiting for the user to allow it
    for i in range(retries):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        if cap.isOpened() and cap.read()[0]:
            return cap
        cap.release()
        if i == 0:
            print("Waiting for camera... click 'Allow' when the permission popup appears")
        time.sleep(1)
    raise SystemExit(CAM_HELP)


def probe(args):
    for idx in range(4):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        print(f"--cam {idx}: " + (f"OK {frame.shape[1]}x{frame.shape[0]}" if ok else "none"))
        if ok:
            cv2.imwrite(f"models/experiments/vision/probe_cam{idx}.jpg", frame)
        cap.release()
    print("check models/experiments/vision/probe_cam*.jpg to see which camera is which")


def setup_rois(args):
    """On one camera frame, drag a box per glass spot -> Enter/Space to confirm, Esc when done."""
    cap = open_cam(args.cam)
    for _ in range(10):  # let exposure settle
        ok, frame = cap.read()
    cap.release()
    print("Drag over each glass spot → Enter. Esc when done")
    boxes = cv2.selectROIs("rois: drag + Enter, Esc to finish", frame, showCrosshair=False)
    cv2.destroyAllWindows()
    if len(boxes) == 0:
        raise SystemExit("no ROIs")
    h, w = frame.shape[:2]
    rois = [[float(x) / w, float(y) / h, float(bw) / w, float(bh) / h] for x, y, bw, bh in boxes]
    Path(args.out).write_text(json.dumps({"frame_size": [w, h], "rois": rois}, indent=2))
    view = frame.copy()
    for i, (x, y, bw, bh) in enumerate(boxes):
        cv2.rectangle(view, (int(x), int(y)), (int(x + bw), int(y + bh)), (0, 255, 0), 2)
        put(view, f"#{i}", int(y) + 24, (0, 255, 0), 0.7, int(x) + 4)
    cv2.imwrite("models/experiments/vision/rois_preview.jpg", view)
    print(f"saved {args.out} ({len(rois)} ROIs), preview → models/experiments/vision/rois_preview.jpg")


def next_index(d):
    """Next save number = max numeric name + 1. Using the file count would overwrite existing files
    after photos are moved to another folder."""
    nums = [int(p.stem) for p in d.glob("*.jpg") if p.stem.isdigit()]
    return max(nums) + 1 if nums else 0


def collect(args):
    classes = args.classes or [f"{d}__{lv}" for d in args.drinks for lv in LEVELS] + ["empty"]
    if len(classes) > len(KEYS):
        raise SystemExit("at most 3 drinks")
    out = Path(args.out)
    for c in classes:
        (out / c).mkdir(parents=True, exist_ok=True)
    cur = 0
    last_save = 0.0
    cap = open_cam(args.cam)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        view = frame.copy()
        x, y, s = roi_box(frame)
        cv2.rectangle(view, (x, y), (x + s, y + s), (0, 255, 0), 2)
        for i, c in enumerate(classes):
            n = len(list((out / c).glob("*.jpg")))
            put(view, f"{'>' if i == cur else ' '} {KEYS[i]}. {c}: {n}", 30 + 26 * i,
                (0, 255, 255) if i == cur else (255, 255, 255), 0.6)
        put(view, f"{KEYS[0]}-{KEYS[len(classes) - 1]} select | space save | q quit", view.shape[0] - 15, scale=0.6)
        cv2.imshow("collect", view)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if chr(k) in KEYS[: len(classes)]:
            cur = KEYS.index(chr(k))
        if k == ord(" ") and time.time() - last_save > 0.4:  # avoid repeated saves from key repeat while space is held
            last_save = time.time()
            d = out / classes[cur]
            n = next_index(d)
            cv2.imwrite(str(d / f"{n:04d}.jpg"), crop_roi(frame))
            print(f"saved {classes[cur]}/{n:04d}.jpg")
    cap.release()
    cv2.destroyAllWindows()


def save_head(clf, classes, path: Path):
    """Save the trained head as JSON usable without sklearn (board: z=(x-mean)/scale -> logits=z@W.T+b -> softmax).
    With 2 classes sklearn keeps only one row of W, so expand it to [-w, w] before saving."""
    sc, lr = clf.named_steps["standardscaler"], clf.named_steps["logisticregression"]
    W, b = lr.coef_, lr.intercept_
    if len(classes) == 2:
        W, b = np.vstack([-W[0] / 2, W[0] / 2]), np.array([-b[0] / 2, b[0] / 2])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(classes=classes, mean=sc.mean_.tolist(), scale=sc.scale_.tolist(),
                                    W=W.tolist(), b=b.tolist())))
    print(f"saved head → {path}")


class Pipeline:
    """Frame -> glass boxes -> square crop per glass -> DINOv2 (one batch) -> head probabilities."""

    def __init__(self, args):
        paths, y, self.classes = load_dataset(args.train)
        if len(paths) == 0:
            raise SystemExit(f"no training images in {args.train} — run collect first")
        tag = f"{Path(args.train).name}_{args.model}_cls"
        X = embed_all(paths, args.model, "cls", args.device, Path("models/experiments/vision") / f"emb_{tag}.npz")
        self.clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.1)).fit(X, y)
        save_head(self.clf, self.classes, Path("models/experiments/vision/heads") / f"head_{tag}.json")
        self.device = args.device
        self.head = EmbeddingHead(load_model(args.model, args.device)).eval()
        self.args = args
        self.yolo = None
        self.rois = load_rois(args.rois) if getattr(args, "rois", None) else None
        if args.detect:
            from ultralytics import YOLO

            self.yolo = YOLO(args.weights)
            self.yolo.predict(np.zeros((480, 640, 3), np.uint8), verbose=False)  # warmup
        with torch.no_grad():
            self.head(torch.zeros(1, 3, 224, 224, device=self.device))  # warmup

    def boxes(self, frame):
        """returns [(crop_box xywh-square, det_xyxy, det_name, det_conf)]"""
        if self.rois is not None:  # fixed ROIs: box = glass spot, crop = that box squared (same rule as detect)
            h, w = frame.shape[:2]
            out = []
            for rx, ry, rw, rh in self.rois:
                xyxy = (rx * w, ry * h, (rx + rw) * w, (ry + rh) * h)
                out.append((square_crop_box(xyxy, frame, 1.0), xyxy, "roi", 1.0))
            return out
        if self.yolo is None:
            x, y, s = roi_box(frame)
            return [((x, y, s), (x, y, x + s, y + s), "roi", 1.0)]
        r = self.yolo.predict(frame, conf=self.args.det_conf, agnostic_nms=True, imgsz=640, verbose=False)[0]
        out = []
        for b in r.boxes:
            name = r.names[int(b.cls)]
            if name not in GLASS_LIKE:
                continue
            xyxy = b.xyxy[0].tolist()
            out.append((square_crop_box(xyxy, frame, self.args.crop_scale), xyxy, name, float(b.conf)))
        out.sort(key=lambda d: d[1][0])  # left to right
        return out[: self.args.max_glasses]

    @torch.no_grad()
    def __call__(self, frame):
        t0 = time.perf_counter()
        dets = self.boxes(frame)
        t1 = time.perf_counter()
        probs = np.zeros((0, len(self.classes)))
        if dets:
            crops = [cv2.cvtColor(frame[y : y + s, x : x + s], cv2.COLOR_BGR2RGB) for (x, y, s), *_ in dets]
            xb = torch.from_numpy(np.concatenate([preprocess(Image.fromarray(c)) for c in crops])).to(self.device)
            t2 = time.perf_counter()
            emb = self.head(xb).cpu().numpy()  # .cpu() doubles as the MPS sync
            t3 = time.perf_counter()
            probs = self.clf.predict_proba(emb)
        else:
            t2 = t3 = time.perf_counter()
        t4 = time.perf_counter()
        ms = dict(det=t1 - t0, pre=t2 - t1, infer=t3 - t2, head=t4 - t3, total=t4 - t0)
        return dets, probs, {k: v * 1000 for k, v in ms.items()}


def live(args):
    Path("models/experiments/vision").mkdir(parents=True, exist_ok=True)
    pipe = Pipeline(args)
    classes = pipe.classes
    tracks = Tracks()
    cap = open_cam(args.cam)
    log = {k: [] for k in ["det", "pre", "infer", "head", "total"]}
    n_glasses = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        dets, probs, ms = pipe(frame)
        for k in log:
            log[k].append(ms[k])
        n_glasses.append(len(dets))
        tr = tracks.update([d[1] for d in dets], list(probs))

        view = frame.copy()
        for (cx, cy, s), t in zip([d[0] for d in dets], tr):
            p = t["prob"]
            ci = int(p.argmax())
            conf = float(p[ci])
            ok_gate = conf >= args.conf_min
            color = (0, 255, 0) if ok_gate else (255, 0, 255)
            x0, y0, x1, y1 = map(int, t["box"])
            cv2.rectangle(view, (x0, y0), (x1, y1), color, 2)
            if args.detect or args.rois:  # square crop region actually fed to DINOv2
                cv2.rectangle(view, (cx, cy), (cx + s, cy + s), (200, 200, 200), 1)
            put(view, f"#{t['id']} {classes[ci]} {conf:.2f}", max(20, y0 - 8), color, 0.6, x0)
        mode = "yolo+dinov2" if args.detect else ("fixed-rois+dinov2" if args.rois else "roi+dinov2")
        put(view, f"{mode} | glasses {len(dets)} | det {ms['det']:.1f} | pre {ms['pre']:.1f} | "
                  f"infer {ms['infer']:.1f} | head {ms['head']:.1f} | total {ms['total']:.1f} ms", 28, scale=0.55)
        put(view, f"q quit | conf_min {args.conf_min} (green OK / magenta UNCERTAIN)", view.shape[0] - 15, scale=0.5)
        cv2.imshow("live", view)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()

    stats = {"mean_glasses": float(np.mean(n_glasses)) if n_glasses else 0.0}
    for k, v in log.items():
        v = sorted(v[5:]) or sorted(v)  # drop the first few frames as warmup
        if v:
            stats[k] = dict(mean=statistics.mean(v), p50=v[len(v) // 2], p90=v[int(len(v) * 0.9)], n=len(v))
    tag = "detect" if args.detect else ("rois" if args.rois else "roi")
    out = Path(f"models/experiments/vision/live_latency_{tag}_{args.model}_{args.device}.json")
    out.write_text(json.dumps(stats, indent=2))
    for k, s_ in stats.items():
        if isinstance(s_, dict):
            print(f"{k:6} mean {s_['mean']:6.2f} ms | p50 {s_['p50']:6.2f} | p90 {s_['p90']:6.2f}  (n={s_['n']})")
    print(f"mean glasses/frame {stats['mean_glasses']:.2f}\nsaved {out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="mode", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--drinks", nargs="+", default=["water", "coke", "coffee"])
    c.add_argument("--classes", nargs="+",
                   help="set classes directly (e.g. other — objects like cans/bottles that YOLO mistakes for cups). ignores --drinks")
    c.add_argument("--out", default="data/real")
    c.add_argument("--cam", type=int, default=0)
    lv = sub.add_parser("live")
    lv.add_argument("--train", default="data/real")
    lv.add_argument("--model", default="small", choices=["small", "base"])
    lv.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    lv.add_argument("--conf-min", type=float, default=0.70)
    lv.add_argument("--cam", type=int, default=0)
    lv.add_argument("--detect", action="store_true", help="detect several glasses with YOLO, then classify each")
    lv.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    lv.add_argument("--det-conf", type=float, default=0.25)
    lv.add_argument("--crop-scale", type=float, default=1.35,
                   help="DINOv2 crop size relative to the detection box. 1.34 measured on training crops (detect test)")
    lv.add_argument("--max-glasses", type=int, default=4)
    lv.add_argument("--rois", help="rois.json made with camera.py rois — several fixed spots (no detector)")
    r = sub.add_parser("rois")
    r.add_argument("--out", default="rois.json")
    r.add_argument("--cam", type=int, default=0)
    sub.add_parser("probe")
    args = ap.parse_args()
    Path("models/experiments/vision").mkdir(parents=True, exist_ok=True)
    if args.mode == "live" and args.detect and args.rois:
        raise SystemExit("use only one of --detect and --rois")
    {"collect": collect, "live": live, "probe": probe, "rois": setup_rois}[args.mode](args)


if __name__ == "__main__":
    main()
