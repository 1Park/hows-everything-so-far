import asyncio
import random

import pytest
from fastapi.testclient import TestClient

from app.capture import AutoCapture, StableWindow, overlap_area
from app.clients import ModelClients
from app.controller import Controller
from app.server import create_app
from common.api import ApiError
from common.config import ROOT, Settings
from common.contracts import BBox, ObservedObject, VisionResult

IMAGE = (ROOT / "docs/assets/cups-example.jpg").read_bytes()


def obj(item="water", box=(0, 0, .5, .5), identity="cup-0"):
    return ObservedObject(object_id=identity, item=item,
                          bbox=BBox(x1=box[0], y1=box[1], x2=box[2], y2=box[3]),
                          fill_ratio=.1, confidence=.95)


def scene(*objects, identity="scene", source="external"):
    return VisionResult(scene_id=identity, source=source, objects=list(objects))


def test_overlap_exact_union_including_triple_overlap():
    assert overlap_area([]) == 0
    assert overlap_area([obj()]) == 0
    assert overlap_area([obj(), obj(box=(.5, 0, 1, .5))]) == 0
    assert overlap_area([obj(), obj(box=(.25, .25, .75, .75))]) == pytest.approx(.0625)
    # Three identical boxes have the same overlap union as two, not 3x area.
    assert overlap_area([obj(), obj(), obj()]) == pytest.approx(.25)


def test_overlap_sweep_matches_small_independent_grid_oracle():
    rng = random.Random(42)
    for _ in range(100):
        boxes = []
        for _ in range(rng.randrange(2, 15)):
            x1, x2 = sorted(rng.sample(range(11), 2))
            y1, y2 = sorted(rng.sample(range(11), 2))
            boxes.append((x1, y1, x2, y2))
        expected = sum(sum(x1 <= x < x2 and y1 <= y < y2 for x1, y1, x2, y2 in boxes) >= 2
                       for x in range(10) for y in range(10)) / 100
        objects = [obj(box=tuple(v/10 for v in b)) for b in boxes]
        assert overlap_area(objects) == pytest.approx(expected)


def test_window_types_counts_order_gap_and_empty():
    window = StableWindow(seconds=5, max_gap=2)
    a = scene(obj(), obj("coffee", identity="other"))
    reordered = scene(obj("coffee", identity="new-1"), obj(identity="new-2"))
    assert window.add(0, b"first", "image/jpeg", a) is None
    assert window.add(1, b"new", "image/jpeg", reordered) is None
    assert window.samples == 2  # IDs/order are not object tracking.
    window.add(2, b"changed-count", "image/jpeg", scene(obj()))
    assert window.samples == 1 and window.started == 2
    window.add(3, b"unknown", "image/jpeg", scene(obj("unknown")))
    assert window.started == 3
    window.add(6, b"gap", "image/jpeg", scene(obj("unknown")))
    assert window.started == 6 and window.samples == 1
    window.add(7, b"none", "image/jpeg", scene())
    assert window.best is None and window.samples == 0


def test_best_frame_within_five_seconds_is_kept_with_its_result():
    window = StableWindow(seconds=5, max_gap=2)
    overlap = scene(obj(), obj("coffee", identity="2"))
    separated = scene(obj(), obj("coffee", box=(.6, 0, 1, .5), identity="2"), identity="best")
    for t in range(6):
        candidate = separated if t == 2 else overlap
        best = window.add(t, f"jpeg-{t}".encode(), "image/jpeg", candidate)
        if t < 5:
            assert best is None
    assert best.data == b"jpeg-2" and best.result is separated and best.score == 0


class Camera:
    def __init__(self):
        self.index = 0

    def frame(self):
        self.index += 1
        return IMAGE + str(self.index).encode(), "image/jpeg"


async def test_scan_selects_analyzed_frame_once_pauses_and_latches():
    settings = Settings(qwen_backend="fixture", capture_mode="auto")
    clients = ModelClients(settings)
    calls = []

    async def vision(data, mime, scene_id, scenario):
        calls.append(data)
        index = len(calls)
        return scene(obj(), obj("coffee", box=((.6, 0, 1, .5) if index == 3 else
                                               (0, 0, .5, .5)), identity="cup-1"),
                     identity=scene_id)

    clients.vision = vision
    controller = Controller(settings, clients)
    clock = [0]
    capture = AutoCapture(controller, Camera(), clock=lambda: clock[0])
    try:
        for t in range(11):
            clock[0] = t*.5
            await capture.scan_once()
        assert controller.phase == "offered" and len(calls) == 11
        assert controller.snapshot[0] == calls[2]
        assert controller.scene.objects[1].bbox.x1 == .6
        # The winning analysis is reused; no 12th Vision invoke on start.
        await capture.scan_once()
        assert len(calls) == 11
        token = controller.token
        await controller.cancel(controller.session_id)
        for t in range(12, 25):
            clock[0] = t*.5
            await capture.scan_once()
        assert controller.phase == "cancelled" and controller.token == token+1
        assert controller.capture_status["status"] == "waiting"
    finally:
        await controller.close()


@pytest.mark.parametrize("change", ["mode", "manual", "cancel"])
async def test_late_background_result_cannot_start_after_user_action(change):
    clients = ModelClients(Settings(qwen_backend="fixture"))
    settings = Settings(qwen_backend="fixture", capture_mode="auto", auto_capture_stable_seconds=.1)
    controller = Controller(settings, clients)
    clock = [0]
    capture = AutoCapture(controller, Camera(), clock=lambda: clock[0])
    entered, release = asyncio.Event(), asyncio.Event()
    count = 0

    async def vision(data, mime, scene_id, scenario):
        nonlocal count
        count += 1
        if count == 2:
            entered.set()
            await release.wait()
        return scene(obj(), identity=scene_id)

    clients.vision = vision
    task = None
    try:
        await capture.scan_once()
        clock[0] = .2
        task = asyncio.create_task(capture.scan_once())
        await asyncio.wait_for(entered.wait(), 1)
        if change == "mode":
            capture.set_mode("manual")
        elif change == "cancel":
            await controller.cancel(controller.session_id)
        else:
            await controller.start(IMAGE, "image/jpeg", "normal",
                                   preanalyzed=scene(obj(), identity="manual-scene"))
        session = controller.session_id
        release.set()
        await task
        assert controller.session_id == session
        assert controller.phase == {"mode": "idle", "cancel": "cancelled", "manual": "offered"}[change]
    finally:
        release.set()
        if task:
            await task
        await controller.close()


async def test_capture_error_resets_stability_and_recovers():
    settings = Settings(qwen_backend="fixture", capture_mode="auto")
    clients = ModelClients(settings)
    controller = Controller(settings, clients)
    capture = AutoCapture(controller, Camera())
    original = clients.vision

    async def failure(*args):
        raise ApiError("service_timeout", "Vision timed out", 504, True)

    clients.vision = failure
    try:
        await capture.scan_once()
        assert controller.phase == "idle" and controller.capture_status["status"] == "error"
        clients.vision = original
        await capture.scan_once()
        assert controller.capture_status["status"] == "stabilizing"
        assert capture.window.samples == 1
    finally:
        await controller.close()


def test_capture_mode_http_validation_and_no_button_autostart():
    settings = Settings(qwen_backend="fixture", auto_capture_interval_seconds=.1,
                        auto_capture_stable_seconds=.2)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/capture").json()["mode"] == "manual"
        assert client.post("/api/capture", json={"mode": "wrong"}).status_code == 422
        assert client.post("/api/capture", json={"mode": "auto"}).status_code == 200
        import time
        for _ in range(100):
            state = client.get("/api/state").json()
            if state["phase"] == "offered":
                break
            time.sleep(.01)
        assert state["phase"] == "offered"
        assert state["scene"]["source"] == "fixture"
        session = state["session_id"]
        client.post("/api/capture", json={"mode": "manual"}).raise_for_status()
        assert client.get("/api/state").json()["session_id"] == session
        assert client.get(state["snapshot_url"]).content == IMAGE
