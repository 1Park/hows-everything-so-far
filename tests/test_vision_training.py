import builtins

import numpy as np
import pytest
from PIL import Image

from ml.training.make_crops import main_box
from ml.training.make_head import inputs, list_images
from services.vision.head import fit_head, softmax


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


def test_lda_head_matches_sklearn_posteriors():
    LinearDiscriminantAnalysis = pytest.importorskip("sklearn.discriminant_analysis").LinearDiscriminantAnalysis

    rng = np.random.default_rng(1)
    X = np.vstack([rng.normal(m, 1, (40, 6)) for m in (0, 1.5, 3)])
    y = np.repeat([0, 1, 2], 40)
    h = fit_head(X, y, ["a", "b", "c"], model="lda")
    assert h["fit"] == "sklearn-lda-shrinkage"
    Z = (X - np.array(h["mean"])) / np.array(h["scale"])
    ref = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto").fit(Z, y).predict_proba(Z)
    assert np.allclose(softmax(Z @ np.array(h["W"]).T + np.array(h["b"])), ref, atol=1e-6)
    two = fit_head(X[:80], y[:80], ["a", "b"], model="lda")  # 2 classes still save one row per class
    assert np.array(two["W"]).shape == (2, 6)


def test_training_images_merge_roots_and_augment_reproducibly(tmp_path):
    for root, cls in (("real", "water__low"), ("real", "other"), ("board", "water__low")):
        (tmp_path / root / cls).mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (80, 120), (40, 90, 200)).save(tmp_path / root / cls / f"{root}.jpg")
    paths, y, classes = list_images([tmp_path / "real", tmp_path / "board"])
    assert classes == ["other", "water__low"] and y == [0, 1, 1] and len(paths) == 3
    a, b = inputs(paths[1], 2), inputs(paths[1], 2)
    assert len(a) == 3 and all(np.array_equal(x, z) for x, z in zip(a, b))
    assert not np.array_equal(a[0], a[1])
