"""Vision external backend — `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=services.vision.backend:create_backend`.

Settings (common.config.Settings — the selected env file, process env vars take precedence;
see models/README.md):
  VISION_MODEL_PATH  bundle directory (contains bundle.json). Relative paths are from the repo root.
                     e.g. models/local/vision/<name> (Mac, XNNPACK .pte) /
                     models/board/vision/<name> (board, QNN .pte)
  VISION_RUNNER_BIN  only when the bundle uses the cli runner: path to qnn_executor_runner or similar

Models and runners are loaded once and reused; inference runs serially on one dedicated thread so it
never blocks the event loop. A missing or unloadable bundle gives ready=False with an explicit error.
No automatic fixture/remote fallback.
"""

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from common.api import ApiError
from common.config import ROOT, load_settings

log = logging.getLogger("vision.backend")


class DinoVisionBackend:
    source = "external"

    def __init__(self, bundle_path=None, runner_bin=None, runners=None, settings=None):
        # .env.board values reach Settings only through REFILL_ENV_FILE and never land in os.environ,
        # so read them from Settings
        if bundle_path is None or runner_bin is None:
            settings = settings or load_settings()
        raw = str(bundle_path or settings.vision_model_path)
        self.path = (Path(raw) if Path(raw).is_absolute() else ROOT / raw) if raw else None
        self.runner_bin = runner_bin or (settings.vision_runner_bin if settings else "") or None
        worker = settings.vision_worker_bin if settings else ""
        self.worker_bin = str((ROOT / worker).resolve()) if worker else None
        self.timeout = settings.inference_timeout if settings else 20
        self._runners = runners
        self.pipeline = None
        self.error = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vision-infer")
        self._loading = None

    def _load(self):
        from services.vision.pipeline import VisionPipeline

        if self.path is None:
            raise FileNotFoundError("VISION_MODEL_PATH is not set")
        return VisionPipeline(self.path, runner_bin=self.runner_bin, runners=self._runners,
                              resident=True, worker_bin=self.worker_bin, timeout=self.timeout)

    async def _ensure(self):
        if self.pipeline is not None:
            return True
        if self._loading is None:
            self._loading = asyncio.get_running_loop().run_in_executor(self.pool, self._load)
        try:
            self.pipeline = await asyncio.shield(self._loading)
            self.error = None
            log.info("vision bundle loaded: %s", self.path)
            return True
        except Exception as e:  # retry on the next call
            self.error = f"{type(e).__name__}: {e}"
            log.error("vision bundle load failed: %s", self.error)
            self._loading = None
            return False

    @property
    def status(self):
        return self.pipeline.status if self.pipeline is not None else {}

    async def startup(self):
        if not await self._ensure():
            raise ApiError("vision_not_ready", f"Vision startup failed ({self.error})", 503)

    async def ready(self):
        return self.pipeline is not None and self.pipeline.resident

    def _infer(self, data):
        img = Image.open(io.BytesIO(data))
        img.load()
        objects = self.pipeline.analyze(img)
        log.info("vision analyze: %d objects, %s", len(objects),
                 {k: round(v, 1) for k, v in self.pipeline.timing.items()})
        return objects

    async def infer(self, data: bytes, content_type: str, scene_id: str, scenario: str):
        # scenario is fixture-only (ignored by external)
        if not await self._ensure():
            raise ApiError("vision_not_ready", f"Vision model is not loaded ({self.error})", 503, True)
        try:
            objects = await asyncio.get_running_loop().run_in_executor(self.pool, self._infer, data)
        except asyncio.CancelledError:
            self.pipeline.abort()
            raise
        return {"scene_id": scene_id, "source": self.source, "objects": objects}

    async def close(self):
        try:
            if self.pipeline is not None:
                self.pipeline.abort()
                await asyncio.get_running_loop().run_in_executor(self.pool, self.pipeline.close)
            elif self._loading is not None:
                # Loading on the single model thread may outlive a cancelled startup.
                try:
                    pipeline = await asyncio.shield(self._loading)
                    await asyncio.get_running_loop().run_in_executor(self.pool, pipeline.close)
                except Exception:
                    pass
        finally:
            self.pool.shutdown(wait=False, cancel_futures=True)


def create_backend():
    return DinoVisionBackend()
