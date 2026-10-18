"""Application-level frame selection. No detector/crop/model preprocessing.

Only the winning JPEG and its VisionResult are retained. Rectangle overlap is
the UNION covered by >=2 boxes, not a pair sum that overcounts triple overlap.
"""

import asyncio
import logging
import time
from collections import Counter
from dataclasses import dataclass

from app.controller import TERMINAL
from common.api import ApiError
from common.contracts import CaptureStatus, VisionResult, uid
from common.media import validate_image

log = logging.getLogger("controller.capture")


def overlap_area(objects) -> float:
    """Normalized intersection-union area, O(n log n) time / O(n) memory.

    Sweep x; a y segment tree tracks lengths covered at least once and twice.
    Contract caps n at 50, with at most 100 events and 99 elementary y segments.
    """
    if len(objects) < 2:
        return 0.0
    boxes = [o.bbox for o in objects]
    ys = sorted({y for b in boxes for y in (b.y1, b.y2)})
    indices = {y: i for i, y in enumerate(ys)}
    events = sorted((x, delta, indices[b.y1], indices[b.y2])
                    for b in boxes for x, delta in ((b.x1, 1), (b.x2, -1)))
    n = len(ys) - 1
    cover, once, twice = [0] * (4*n), [0.0] * (4*n), [0.0] * (4*n)

    def update(node, lo, hi, left, right, delta):
        if left <= lo and hi <= right:
            cover[node] += delta
        else:
            mid = (lo+hi)//2
            if left < mid:
                update(node*2, lo, mid, left, right, delta)
            if right > mid:
                update(node*2+1, mid, hi, left, right, delta)
        child_once = once[node*2] + once[node*2+1] if hi-lo > 1 else 0.0
        child_twice = twice[node*2] + twice[node*2+1] if hi-lo > 1 else 0.0
        once[node] = ys[hi]-ys[lo] if cover[node] else child_once
        twice[node] = (ys[hi]-ys[lo] if cover[node] >= 2 else
                       child_once if cover[node] == 1 else child_twice)

    area, previous = 0.0, events[0][0]
    for x, delta, lo, hi in events:
        area += (x-previous) * twice[1]
        update(1, 0, n, lo, hi, delta)
        previous = x
    return max(0.0, area)


def signature(result):
    # IDs/order can change each frame. Counts must match, including unknown.
    return result.source, tuple(sorted(Counter(o.item for o in result.objects).items()))


@dataclass
class Candidate:
    data: bytes
    mime: str
    result: VisionResult
    score: float


class StableWindow:
    def __init__(self, seconds=3, max_gap=1):
        self.seconds, self.max_gap = seconds, max_gap
        self.reset()

    def reset(self):
        self.key = self.best = None
        self.started = self.last = 0.0
        self.samples = 0

    def add(self, now, data, mime, result):
        key = signature(result)
        if not result.objects:
            self.reset()
            return None
        if key != self.key or now-self.last > self.max_gap:
            self.reset()
            self.key, self.started = key, now
        self.last = now
        self.samples += 1
        score = overlap_area(result.objects)
        # Equal overlap prefers the freshest frame.
        if self.best is None or score <= self.best.score:
            self.best = Candidate(data, mime, result, score)
        return self.best if now-self.started >= self.seconds and self.samples >= 2 else None


class AutoCapture:
    def __init__(self, controller, video, clock=time.monotonic):
        self.controller, self.video, self.clock = controller, video, clock
        settings = controller.settings
        self.interval = settings.observe_interval_seconds or settings.auto_capture_interval_seconds
        self.window = StableWindow(settings.auto_capture_stable_seconds, max(1, self.interval*3))
        self.mode = "auto" if settings.observe_interval_seconds else settings.capture_mode
        self.epoch = self.revision = 0
        self.blocked = None
        self.last_token = controller.token
        self.restart_enabled = settings.auto_capture_restart_enabled
        self.restart_seconds = settings.auto_capture_restart_seconds
        self.restart_deadline = self.restart_session = None
        self.publish("scanning" if self.mode == "auto" else "manual")

    def publish(self, status, **kwargs):
        self.revision += 1
        state = CaptureStatus(mode=self.mode, status=status, revision=self.revision,
                              required_seconds=self.window.seconds,
                              restart_enabled=self.restart_enabled,
                              restart_seconds=self.restart_seconds,
                              restart_remaining_seconds=(max(0, self.restart_deadline-self.clock())
                                                         if self.restart_deadline is not None else None),
                              **kwargs).model_dump()
        self.controller.capture_status = state
        # A separate event avoids invalidating an offer's sequence/voice ACK.
        for queue in self.controller.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait({"type": "capture", "capture": state,
                              "instance_id": self.controller.instance_id})
        return state

    def set_mode(self, mode):
        self.mode = mode
        self.epoch += 1  # Invalidate in-flight inference even on auto -> auto rearm.
        self.window.reset()
        self.blocked = None
        self.restart_deadline = self.restart_session = None
        return self.publish("scanning" if mode == "auto" else "manual")

    def configure_restart(self, enabled, seconds):
        self.epoch += 1
        self.window.reset()
        self.restart_enabled, self.restart_seconds = enabled, seconds
        self.restart_session = None
        self.restart_deadline = None
        status = self.controller.capture_status["status"]
        return self.publish("scanning" if status == "cooldown" else status)

    async def scan_once(self):
        c = self.controller
        if self.mode != "auto":
            return
        if c.phase not in TERMINAL:
            self.restart_deadline = self.restart_session = None
            self.window.reset()
            if c.scene:
                self.blocked = signature(c.scene)
            if c.capture_status["status"] != "paused":
                self.publish("paused")
            return
        now = self.clock()
        if self.restart_enabled and c.phase != "idle":
            if self.restart_session != c.session_id:
                self.restart_session = c.session_id
                self.restart_deadline = now+self.restart_seconds
            if now < self.restart_deadline:
                self.window.reset()
                self.publish("cooldown")
                return
            # Same operation as Restart auto capture, with no browser click or microphone action.
            self.set_mode("auto")
            await c.restart_session()
            self.last_token = c.token
            return
        if self.last_token != c.token:
            self.window.reset()
            self.last_token = c.token
        epoch, token = self.epoch, c.token
        try:
            data, mime = self.video.frame()
            validate_image(data, mime)
            if len(data) > c.settings.max_image_bytes:
                raise ApiError("invalid_size", "Captured image exceeds the size limit", 413)
            async with asyncio.timeout(c.settings.inference_timeout):
                result = await c.clients.vision(data, mime, uid(), "normal")
            if epoch != self.epoch or token != c.token or c.phase not in TERMINAL:
                return
            key = signature(result)
            if self.blocked == key:
                self.window.reset()
                self.publish("waiting", source=result.source)
                return
            self.blocked = None
            best = self.window.add(now, data, mime, result)
            if best is not None:
                # start() rechecks token/phase under the Controller lock.
                state = await c.start(best.data, best.mime, "normal", automatic=True,
                                      preanalyzed=best.result, expected_token=token)
                if state["scene"] and state["scene"]["scene_id"] == best.result.scene_id:
                    self.blocked = self.window.key
                    self.window.reset()
                    self.publish("paused" if c.phase not in TERMINAL else "waiting",
                                 source=best.result.source, overlap_area=best.score)
                return
            self.publish("stabilizing" if result.objects else "scanning",
                         source=result.source, samples=self.window.samples,
                         stable_seconds=round(now-self.window.started, 2) if result.objects else 0,
                         overlap_area=self.window.best.score if self.window.best else None)
        except (ApiError, TimeoutError) as error:
            if epoch == self.epoch and token == c.token:
                self.window.reset()
                self.publish("error", error=(error.message if isinstance(error, ApiError)
                                             else "Scene analysis timed out. Retrying."))
        except Exception:
            log.exception("Automatic capture failed")
            if epoch == self.epoch and token == c.token:
                self.window.reset()
                self.publish("error", error="Automatic capture failed. Retrying.")

    async def run(self):
        while True:
            started = self.clock()
            await self.scan_once()
            await asyncio.sleep(max(0.05, self.interval-(self.clock()-started)))
