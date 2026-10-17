"""Single video owner. Capture/encode only; no detector, crop, or model preprocessing."""

import asyncio
import threading

from common.api import ApiError
from common.config import ROOT


class VideoSource:
    def __init__(self, source=""):
        self.source = source
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
            self.thread = threading.Thread(target=self.capture, daemon=True)
            self.thread.start()

    def capture(self):
        try:
            import cv2

            capture = cv2.VideoCapture(int(self.source) if self.source.isdigit() else self.source)
            if not capture.isOpened():
                raise RuntimeError("Camera or file cannot be opened")
            try:
                while not self.closed.is_set():
                    ok, frame = capture.read()
                    if not ok:
                        if self.latest is None:
                            raise RuntimeError("Video source returned no frames")
                        if not self.source.isdigit():
                            capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            self.closed.wait(0.05)
                            continue
                        raise RuntimeError("Camera disconnected")
                    ok, image = cv2.imencode(".jpg", frame)
                    if ok:
                        with self.lock:
                            self.latest, self.content_type = image.tobytes(), "image/jpeg"
                    self.closed.wait(0.1)
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
        while not self.closed.is_set():
            data, mime = self.frame()
            yield (
                b"--frame\r\nContent-Type: "
                + mime.encode()
                + b"\r\nContent-Length: "
                + str(len(data)).encode()
                + b"\r\n\r\n"
                + data
                + b"\r\n"
            )
            await asyncio.sleep(0.2)

    def close(self):
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=2)
