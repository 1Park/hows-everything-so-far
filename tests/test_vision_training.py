import builtins

import numpy as np

from ml.training.make_crops import main_box
from services.vision.head import fit_head


def det(x0, y0, x1, y1, conf=0.5):
    return ((x0, y0, x1, y1), conf, 41)


def test_main_box_needs_exactly_one_box_over_center():
    size = (100, 100)
    cup, can_left = det(30, 20, 70, 90), det(0, 10, 25, 90)
    assert main_box([can_left, cup], size) is cup
    assert main_box([can_left], size) is None  # photo where YOLO missed the center cup
    assert main_box([cup, det(40, 0, 80, 60)], size) is None  # photo with a can overlapping behind


def imbalanced():
    rng = np.random.default_rng(0)
    X = np.vstack([rng.normal(0, 1, (60, 4)), rng.normal(1.2, 1, (6, 4))])
    return X, [0] * 60 + [1] * 6


def test_balanced_class_weight_raises_minority_recall(monkeypatch):
    X, y = imbalanced()
    real_import = builtins.__import__

    def no_sklearn(name, *args, **kwargs):  # use the numpy gradient-descent path, like the board
        if name.startswith("sklearn"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_sklearn)
    recall = {}
    for cw in (None, "balanced"):
        h = fit_head(X, y, ["a", "b"], C=0.01, class_weight=cw)
        assert h["fit"] == "numpy-gd"
        Z = (X - np.array(h["mean"])) / np.array(h["scale"])
        pred = (Z @ np.array(h["W"]).T + np.array(h["b"])).argmax(1)
        recall[cw] = (pred[60:] == 1).mean()
    assert recall["balanced"] > recall[None]
