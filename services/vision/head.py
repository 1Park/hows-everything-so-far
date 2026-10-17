"""분류 head — 임베딩(또는 ImageNet logits) → 클래스 확률. numpy만 (sklearn 없어도 동작).

JSON 형식 (camera.save_head 와 동일): {classes, mean, scale, W, b}
  z = (x - mean) / scale ; logits = z @ W.T + b ; softmax

⚠️ head 는 보드에서 실제로 돌릴 .pte 가 낸 특징으로 학습해야 한다 (ml/training/make_head.py).
   Mac fp32 특징으로 학습한 head 를 양자화 모델에 쓰면 정확도가 크게 떨어진다 (README 참고).
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
            raise ValueError(f"특징 차원 {X.shape[1]} ≠ head {self.dim} — head를 이 .pte 출력으로 다시 학습할 것")
        return softmax(((X - self.mean) / self.scale) @ self.W.T + self.b)


def fit_head(X, y, classes, C=0.1, iters=3000, lr=0.5):
    """StandardScaler + 다항 로지스틱 회귀. sklearn 있으면 그것(Mac과 동일), 없으면 numpy 경사하강."""
    X = np.asarray(X, np.float64).reshape(len(X), -1)
    y = np.asarray(y)
    mean, scale = X.mean(0), X.std(0)
    scale[scale == 0] = 1.0
    Z = (X - mean) / scale
    k = len(classes)
    try:
        from sklearn.linear_model import LogisticRegression

        lr_ = LogisticRegression(max_iter=3000, C=C).fit(Z, y)
        W, b = lr_.coef_, lr_.intercept_
        if k == 2:  # sklearn 2클래스는 W 1행 → softmax 형태로 펼침
            W, b = np.vstack([-W[0] / 2, W[0] / 2]), np.array([-b[0] / 2, b[0] / 2])
        how = "sklearn"
    except ImportError:
        n, d = Z.shape
        W, b = np.zeros((k, d)), np.zeros(k)
        Y = np.eye(k)[y]
        lam = 1.0 / (C * n)  # sklearn 목적함수(합 CE + ||W||²/2C)를 n으로 나눈 것
        for _ in range(iters):
            G = softmax(Z @ W.T + b) - Y
            W -= lr * (G.T @ Z / n + lam * W)
            b -= lr * G.mean(0)
        how = "numpy-gd"
    acc = float((softmax(Z @ W.T + b).argmax(1) == y).mean())
    return dict(classes=list(classes), mean=mean.tolist(), scale=scale.tolist(), W=np.asarray(W).tolist(),
                b=np.asarray(b).tolist(), fit=how, train_acc=acc, n=int(len(y)))
