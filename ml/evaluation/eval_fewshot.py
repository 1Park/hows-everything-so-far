"""Evaluate few-shot classification accuracy on DINOv2 embeddings.

Class folder naming: <drink>__<level> or empty
  joint accuracy: the 7 classes as-is
  fill accuracy: compare only the level part of prediction/label (empty included)
  drink accuracy: only samples whose label is not empty; compare predicted drink (predicting empty is wrong)
  conf gate: coverage when only predictions >= the spec's CONF_MIN are accepted, and accuracy within them

Usage:
  python -m ml.evaluation.eval_fewshot --data data/synthetic --model small --shots 1 3 5 10
"""

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ml.common import EmbeddingHead, load_dataset, load_model, preprocess


def split_name(c):
    return ("-", "empty") if c == "empty" else tuple(c.split("__"))


@torch.no_grad()
def embed_all(paths, model_name, pool, device, cache: Path):
    if cache.exists():
        z = np.load(cache)
        if len(z["emb"]) == len(paths):
            return z["emb"]
    head = EmbeddingHead(load_model(model_name, device), pool)
    embs = []
    t0 = time.perf_counter()
    for i in range(0, len(paths), 32):
        x = np.concatenate([preprocess(Image.open(p)) for p in paths[i : i + 32]])
        embs.append(head(torch.from_numpy(x).to(device)).float().cpu().numpy())
    print(f"embedded {len(paths)} imgs in {time.perf_counter() - t0:.1f}s on {device}")
    emb = np.concatenate(embs)
    np.savez(cache, emb=emb)
    return emb


def l2n(x):
    return x / np.linalg.norm(x, axis=1, keepdims=True)


def predict(method, Xtr, ytr, Xte, n_cls):
    """returns (pred, prob) — prob is (N, n_cls) softmax/probabilities"""
    if method == "proto":
        sc = StandardScaler().fit(Xtr)  # fit on train only
        Xtr, Xte = sc.transform(Xtr), sc.transform(Xte)
        protos = l2n(np.stack([Xtr[ytr == c].mean(0) for c in range(n_cls)]))
        sim = l2n(Xte) @ protos.T
        logits = sim / 0.05  # temperature: makes cosine similarity read like a probability (tunable)
    elif method == "logreg":
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=0.1))
        clf.fit(Xtr, ytr)
        return clf.predict(Xte), clf.predict_proba(Xte)
    else:
        raise ValueError(method)
    p = np.exp(logits - logits.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    return p.argmax(1), p


def metrics(y, pred, prob, classes, conf_min):
    parts = [split_name(c) for c in classes]
    joint = (pred == y).mean()
    fill = np.mean([parts[a][1] == parts[b][1] for a, b in zip(y, pred)])
    nonempty = [i for i in range(len(y)) if parts[y[i]][1] != "empty"]
    drink = np.mean([parts[y[i]][0] == parts[pred[i]][0] for i in nonempty])
    conf = prob.max(1)
    keep = conf >= conf_min
    gated = (pred[keep] == y[keep]).mean() if keep.any() else float("nan")
    return dict(joint=joint, fill=fill, drink=drink, coverage=keep.mean(), gated_acc=gated)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--model", default="small", choices=["small", "base"])
    ap.add_argument("--pool", default="cls", choices=["cls", "cls_mean"])
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--shots", type=int, nargs="+", default=[1, 3, 5, 10, 20])
    ap.add_argument("--test-frac", type=float, default=0.5)
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--conf-min", type=float, default=0.70)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    paths, y, classes = load_dataset(args.data)
    out_dir = Path("models/experiments/vision")
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{Path(args.data).name}_{args.model}_{args.pool}"
    X = embed_all(paths, args.model, args.pool, args.device, out_dir / f"emb_{tag}.npz")
    print(f"{len(paths)} images, {len(classes)} classes, emb dim {X.shape[1]}")

    # fixed per-class test split; sample k-shot from the remaining pool
    rng = np.random.default_rng(args.seed)
    test_idx, pool = [], {}
    for c in range(len(classes)):
        idx = rng.permutation(np.where(y == c)[0])
        n_te = int(len(idx) * args.test_frac)
        test_idx += list(idx[:n_te])
        pool[c] = idx[n_te:]
    test_idx = np.array(test_idx)

    report = {"data": args.data, "model": args.model, "pool": args.pool, "classes": classes, "n_test": len(test_idx), "results": []}
    print(f"\ntest set: {len(test_idx)} imgs | trials={args.trials} | CONF_MIN={args.conf_min}")
    print(f"{'method':7} {'shot':>4} | {'joint':>12} {'fill':>12} {'drink':>12} | {'coverage':>9} {'gated_acc':>9}")
    last_cm = None
    for method in ["proto", "logreg"]:
        for k in args.shots:
            if any(len(pool[c]) < k for c in pool):
                continue
            ms = []
            for _ in range(args.trials):
                tr = np.concatenate([rng.choice(pool[c], k, replace=False) for c in pool])
                pred, prob = predict(method, X[tr], y[tr], X[test_idx], len(classes))
                ms.append(metrics(y[test_idx], pred, prob, classes, args.conf_min))
                last_cm = (method, k, confusion_matrix(y[test_idx], pred, labels=range(len(classes))))
            agg = {}
            for m in ms[0]:
                v = np.array([d[m] for d in ms], dtype=float)
                v = v[~np.isnan(v)]
                agg[m] = (float(v.mean()), float(v.std())) if len(v) else (float("nan"), float("nan"))
            report["results"].append({"method": method, "shots": k, **{m: v[0] for m, v in agg.items()}})
            def f(m, agg=agg):
                return f"{agg[m][0]*100:5.1f}±{agg[m][1]*100:4.1f}"

            print(
                f"{method:7} {k:>4} | {f('joint'):>12} {f('fill'):>12} {f('drink'):>12} | "
                f"{agg['coverage'][0]*100:8.1f}% {agg['gated_acc'][0]*100:8.1f}%"
            )

    method, k, cm = last_cm
    print(f"\nconfusion matrix ({method}, {k}-shot, last trial) — rows=true, cols=pred")
    w = max(len(c) for c in classes)
    print(" " * (w + 1) + " ".join(f"{i:>3}" for i in range(len(classes))))
    for i, c in enumerate(classes):
        print(f"{c:>{w}} " + " ".join(f"{v:>3}" for v in cm[i]) + f"   [{i}]")

    (out_dir / f"fewshot_{tag}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nsaved models/experiments/vision/fewshot_{tag}.json")


if __name__ == "__main__":
    main()
