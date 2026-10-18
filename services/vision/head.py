"""Classification head — embeddings (or ImageNet logits) → class probabilities. numpy only
(works without sklearn).

JSON format (same as camera.save_head): {classes, mean, scale, W, b}
  z = (x - mean) / scale ; logits = z @ W.T + b ; softmax

⚠️ Train the head on features from the .pte that will actually run on the board
   (ml/training/make_head.py). A head trained on Mac fp32 features loses a lot of accuracy
   on the quantized model (see README).
"""

import json
from pathlib import Path

import numpy as np


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


class Head:
    def __init__(self, path):
        h = json.loads(Path(path).read_text())
        self.classes = h["classes"]
        self.mean, self.scale = np.array(h["mean"]), np.array(h["scale"])
        self.W, self.b = np.array(h["W"]), np.array(h["b"])
        self.dim = self.W.shape[1]

    def predict_proba(self, X):
        X = np.asarray(X, np.float64).reshape(len(X), -1)
        if X.shape[1] != self.dim:
            raise ValueError(f"feature dim {X.shape[1]} ≠ head {self.dim} — retrain the head on this .pte's output")
        return softmax(((X - self.mean) / self.scale) @ self.W.T + self.b)


def fit_head(X, y, classes, C=0.1, iters=3000, lr=0.5, class_weight=None, model="logistic"):
    """StandardScaler + linear head. model="logistic": multinomial logistic regression, sklearn
    when available (same as on the Mac), otherwise numpy gradient descent.
    model="lda": LinearDiscriminantAnalysis (lsqr, shrinkage="auto"), needs sklearn. Its
    posteriors are softmax(coef_ · z + intercept_), so it saves in the same W/b format (board
    v6/v7 head).

    class_weight="balanced": reweights for uneven per-class image counts (e.g. many can crops in
    other). Logistic only; LDA uses class priors instead.
    """
    X = np.asarray(X, np.float64).reshape(len(X), -1)
    y = np.asarray(y)
    mean, scale = X.mean(0), X.std(0)
    scale[scale == 0] = 1.0
    Z = (X - mean) / scale
    k = len(classes)
    if model == "lda":
        try:
            from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        except ImportError:
            raise ImportError("model='lda' needs scikit-learn (pip install scikit-learn)") from None

        lda = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(Z, y)
        W, b = lda.coef_, lda.intercept_
        if k == 2:  # one row for 2 classes, as in logistic regression
            W, b = np.vstack([-W[0] / 2, W[0] / 2]), np.array([-b[0] / 2, b[0] / 2])
        acc = float((softmax(Z @ W.T + b).argmax(1) == y).mean())
        return dict(classes=list(classes), mean=mean.tolist(), scale=scale.tolist(), W=np.asarray(W).tolist(),
                    b=np.asarray(b).tolist(), fit="sklearn-lda-shrinkage", train_acc=acc, n=int(len(y)))
    try:
        from sklearn.linear_model import LogisticRegression

        lr_ = LogisticRegression(max_iter=3000, C=C, class_weight=class_weight).fit(Z, y)
        W, b = lr_.coef_, lr_.intercept_
        if k == 2:  # sklearn stores 2 classes as one W row → expand to softmax form
            W, b = np.vstack([-W[0] / 2, W[0] / 2]), np.array([-b[0] / 2, b[0] / 2])
        how = "sklearn"
    except ImportError:
        n, d = Z.shape
        W, b = np.zeros((k, d)), np.zeros(k)
        Y = np.eye(k)[y]
        sw = np.ones(n)
        if class_weight == "balanced":  # same definition as sklearn: n / (k * class count)
            sw = n / (k * np.bincount(y, minlength=k)[y])
        lam = 1.0 / (C * n)  # sklearn's objective (summed CE + ||W||²/2C) divided by n
        for _ in range(iters):
            G = (softmax(Z @ W.T + b) - Y) * sw[:, None]
            W -= lr * (G.T @ Z / n + lam * W)
            b -= lr * G.mean(0)
        how = "numpy-gd"
    acc = float((softmax(Z @ W.T + b).argmax(1) == y).mean())
    return dict(classes=list(classes), mean=mean.tolist(), scale=scale.tolist(), W=np.asarray(W).tolist(),
                b=np.asarray(b).tolist(), fit=how, train_acc=acc, n=int(len(y)))
