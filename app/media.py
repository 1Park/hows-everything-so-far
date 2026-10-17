"""Single video owner. Capture/encode only; no detector, crop, or model preprocessing."""

import asyncio
import threading

from common.api import ApiError
from common.config import ROOT


class VideoSource:
    def __init__(self, source="", capture_fps=20.0, stream_fps=15.0):
        self.source = source
        self.capture_interval = 1 / capture_fps
        self.stream_interval = 1 / stream_fps
        self.latest = (ROOT / "docs/assets/cups-example.jpg").read_bytes()
        if source:
            self.latest = None
        self.content_type = "image/jpeg"
        self.error = None
        self.closed = threading.Event()
        self.thread = None
        self.lock = threading.Lock()
        self.mode = "fixture-image" if not source else "camera-or-file"

    def start(self):
        if self.source:
            self.thread = threading.Thread(target=self.supervise, daemon=True)
            self.thread.start()

    def supervise(self):
        """A USB camera can drop out briefly. Keep trying instead of failing for good.

        The error stays visible while the source is down, so a camera that is really
        gone still surfaces as 503 rather than quietly serving a stale frame.
        """
        delay = 0.5
        while not self.closed.is_set():
            self.capture()
            if self.closed.is_set():
                break
            self.closed.wait(delay)
            delay = min(delay * 2, 5)

    def capture(self):
        try:
            import cv2

            live = self.source.isdigit()
            capture = cv2.VideoCapture(int(self.source) if live else self.source)
            if not capture.isOpened():
                raise RuntimeError("Camera or file cannot be opened")
            if live:
                # Keep the driver queue at one frame. read() returns the OLDEST queued
                # frame, so any backlog becomes latency that grows until frames drop.
                capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            try:
                while not self.closed.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        if self.latest is None:
                            raise RuntimeError("Video source returned no frames")
                        if not live:
                            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            self.closed.wait(0.05)
                            continue
                        raise RuntimeError("Camera disconnected")
                    ok, image = cv2.imencode(".jpg", frame)
                    if ok:
                        with self.lock:
                            self.latest, self.content_type = image.tobytes(), "image/jpeg"
                            self.error = None  # a frame arrived; the source is back
                    if not live:
                        # Files have no queue to drain, so pace them to the target rate.
                        self.closed.wait(self.capture_interval)
            finally:
                capture.release()
        except Exception as error:
            self.error = f"Video source unavailable ({type(error).__name__}). Install the camera extra and check CAMERA_SOURCE."

    def frame(self):
        if self.error:
            raise ApiError("video_unavailable", self.error, 503, True)
        with self.lock:
            if self.latest is None:
                raise ApiError("video_starting", "Video capture is still starting", 503, True)
            return self.latest, self.content_type

    async def frames(self):
        """Once streaming has begun, a gap is a gap, not the end of the stream.

        Raising here would close the response and the browser never retries an
        <img> stream on its own, so a momentary hiccup used to need a reload.
        """
        while not self.closed.is_set():
            try:
                data, mime = self.frame()
            except ApiError:
                await asyncio.sleep(self.stream_interval)
                continue
            yield (
                b"--frame\r\nContent-Type: "
                + mime.encode()
                + b"\r\nContent-Length: "
                + str(len(data)).encode()
                + b"\r\n\r\n"
                + data
                + b"\r\n"
            )
            await asyncio.sleep(self.stream_interval)

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=2)
