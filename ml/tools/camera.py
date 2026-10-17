"""맥북(또는 USB) 카메라로 실사 데이터 수집 / 실시간 추론 + 지연시간 측정.

화면 가운데 정사각형 박스 = ROI (스펙의 primary ROI). 잔을 박스 안에 두고 찍는다.

1) 수집:  python -m ml.tools.camera collect --drinks water coke coffee
   키: 1~9,0 클래스 선택 (10번째 = 0) | space 저장 | q 종료   → data/real/<class>/NNNN.jpg
2) 정확도: python -m ml.evaluation.eval_fewshot --data data/real --shots 1 3 5
3) 실시간: python -m ml.tools.camera live --train data/real            (가운데 ROI 1개)
          python -m ml.tools.camera live --train data/real --detect   (YOLO로 잔 여러 개 찾아서 잔마다 분류)
          python -m ml.tools.camera rois                              (잔 놓을 자리를 마우스로 지정 → rois.json)
          python -m ml.tools.camera live --train data/real --rois rois.json   (고정 ROI 여러 개, 검출기 없음)
   키: q 종료   → models/experiments/vision/live_latency_*.json (프레임별 단계 ms 통계)

macOS: iTerm/터미널.app에서 실행해야 권한 팝업이 뜬다 (Claude 앱 터미널 패널 X).
카메라 여러 대면: python -m ml.tools.camera probe
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
    """cv2 프레임 → 가운데 정사각형 (x, y, side). 서비스의 center_box 와 같은 규칙."""
    return center_box((frame.shape[1], frame.shape[0]), frac)


def square_crop_box(xyxy, frame, scale):
    return _square_crop_box(xyxy, (frame.shape[1], frame.shape[0]), scale)


def load_rois(path):
    """rois.json: {"rois": [[x, y, w, h], ...]} 프레임 대비 비율(0~1)."""
    return json.loads(Path(path).read_text())["rois"]


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Tracks:
    """live 화면용: 프레임 간 같은 컵을 IoU로 짝지어 확률을 지수이동평균 → 라벨 깜빡임 방지.
    (Vision 서비스는 장면 단위라 추적하지 않는다)"""

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
KEYS = "1234567890"  # 클래스 선택 키 (최대 10클래스 = 3 drinks × 3 levels + empty)
GLASS_LIKE = {"cup", "wine glass", "bottle", "bowl", "vase"}  # COCO에서 잔으로 인정할 클래스


def crop_roi(frame):
    x, y, s = roi_box(frame)
    return frame[y : y + s, x : x + s]


def put(img, text, y, color=(255, 255, 255), scale=0.7, x=12):
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


CAM_HELP = """카메라를 열 수 없음.
  1) 터미널.app/iTerm에서 실행했는지 확인 (Claude 앱 터미널 패널에서는 macOS 권한 팝업이 안 뜸)
     → Finder에서 collect.command 더블클릭하면 터미널.app으로 실행됨
  2) 시스템 설정 > 개인정보 보호 및 보안 > 카메라 에서 터미널 켜기 → 터미널 재시작
  3) 카메라 여러 대(아이폰 연속성 카메라 등)면: python -m ml.tools.camera probe 로 인덱스 확인 후 --cam N"""


def open_cam(idx, retries=10):
    # macOS: 첫 실행 시 권한 요청이 비동기라 첫 open은 실패한다 → 팝업 허용을 기다리며 재시도
    for i in range(retries):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        if cap.isOpened() and cap.read()[0]:
            return cap
        cap.release()
        if i == 0:
            print("카메라 대기 중... 권한 팝업이 뜨면 '허용'을 누르세요")
        time.sleep(1)
    raise SystemExit(CAM_HELP)


def probe(args):
    for idx in range(4):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        ok, frame = cap.read() if cap.isOpened() else (False, None)
        print(f"--cam {idx}: " + (f"OK {frame.shape[1]}x{frame.shape[0]}" if ok else "없음"))
        if ok:
            cv2.imwrite(f"models/experiments/vision/probe_cam{idx}.jpg", frame)
        cap.release()
    print("models/experiments/vision/probe_cam*.jpg 로 어떤 카메라인지 확인")


def setup_rois(args):
    """카메라 한 프레임에서 잔 자리마다 박스를 드래그 → Enter/Space로 확정, 다 그렸으면 Esc."""
    cap = open_cam(args.cam)
    for _ in range(10):  # 노출 안정화
        ok, frame = cap.read()
    cap.release()
    print("잔 자리마다 드래그 → Enter. 끝나면 Esc")
    boxes = cv2.selectROIs("rois: drag + Enter, Esc to finish", frame, showCrosshair=False)
    cv2.destroyAllWindows()
    if len(boxes) == 0:
        raise SystemExit("ROI가 없음")
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
    """다음 저장 번호 = 숫자 이름 중 최댓값 + 1. 개수로 정하면 사진을 다른 폴더로 옮긴 뒤 기존 파일을 덮어쓴다."""
    nums = [int(p.stem) for p in d.glob("*.jpg") if p.stem.isdigit()]
    return max(nums) + 1 if nums else 0


def collect(args):
    classes = [f"{d}__{lv}" for d in args.drinks for lv in LEVELS] + ["empty"]
    if len(classes) > len(KEYS):
        raise SystemExit("drink는 최대 3종")
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
        if k == ord(" ") and time.time() - last_save > 0.4:  # 스페이스 누르고 있을 때 키 반복으로 연속 저장 방지
            last_save = time.time()
            d = out / classes[cur]
            n = next_index(d)
            cv2.imwrite(str(d / f"{n:04d}.jpg"), crop_roi(frame))
            print(f"saved {classes[cur]}/{n:04d}.jpg")
    cap.release()
    cv2.destroyAllWindows()


def save_head(clf, classes, path: Path):
    """학습된 head를 sklearn 없이 쓸 수 있는 JSON으로 저장 (보드: z=(x-mean)/scale → logits=z@W.T+b → softmax).
    2클래스면 sklearn이 W 1행만 두므로 [-w, w] 형태로 펼쳐 저장한다."""
    sc, lr = clf.named_steps["standardscaler"], clf.named_steps["logisticregression"]
    W, b = lr.coef_, lr.intercept_
    if len(classes) == 2:
        W, b = np.vstack([-W[0] / 2, W[0] / 2]), np.array([-b[0] / 2, b[0] / 2])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(classes=classes, mean=sc.mean_.tolist(), scale=sc.scale_.tolist(),
                                    W=W.tolist(), b=b.tolist())))
    print(f"saved head → {path}")


class Pipeline:
    """프레임 → 잔 박스들 → 잔마다 정사각 crop → DINOv2 (한 번에 batch) → head 확률."""

    def __init__(self, args):
        paths, y, self.classes = load_dataset(args.train)
        if len(paths) == 0:
            raise SystemExit(f"{args.train} 에 학습 이미지가 없음 — 먼저 collect")
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
        if self.rois is not None:  # 고정 ROI: 박스 = 잔 자리, crop = 그 박스를 정사각형으로 (detect와 같은 규칙)
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
        out.sort(key=lambda d: d[1][0])  # 왼쪽부터
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
            emb = self.head(xb).cpu().numpy()  # .cpu() 가 MPS 동기화 역할
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
            if args.detect or args.rois:  # DINOv2에 실제로 들어간 정사각 crop 영역
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
        v = sorted(v[5:]) or sorted(v)  # 처음 몇 프레임은 워밍업으로 제외
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
    c.add_argument("--out", default="data/real")
    c.add_argument("--cam", type=int, default=0)
    lv = sub.add_parser("live")
    lv.add_argument("--train", default="data/real")
    lv.add_argument("--model", default="small", choices=["small", "base"])
    lv.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    lv.add_argument("--conf-min", type=float, default=0.70)
    lv.add_argument("--cam", type=int, default=0)
    lv.add_argument("--detect", action="store_true", help="YOLO로 잔 여러 개 검출 후 잔마다 분류")
    lv.add_argument("--weights", default="models/local/vision/yolo11n.pt")
    lv.add_argument("--det-conf", type=float, default=0.25)
    lv.add_argument("--crop-scale", type=float, default=1.35,
                   help="검출 박스 대비 DINOv2 crop 크기. 학습 crop에서 잰 값 1.34 (detect 테스트)")
    lv.add_argument("--max-glasses", type=int, default=4)
    lv.add_argument("--rois", help="camera.py rois 로 만든 rois.json — 고정 자리 여러 개 (검출기 없이)")
    r = sub.add_parser("rois")
    r.add_argument("--out", default="rois.json")
    r.add_argument("--cam", type=int, default=0)
    sub.add_parser("probe")
    args = ap.parse_args()
    Path("models/experiments/vision").mkdir(parents=True, exist_ok=True)
    if args.mode == "live" and args.detect and args.rois:
        raise SystemExit("--detect 와 --rois 중 하나만")
    {"collect": collect, "live": live, "probe": probe, "rois": setup_rois}[args.mode](args)


if __name__ == "__main__":
    main()
