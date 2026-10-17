"""Vision external backend — `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=services.vision.backend:create_backend`.

설정 (프로세스 환경변수, models/README.md 규칙):
  VISION_MODEL_PATH  bundle 디렉터리 (bundle.json 포함). 상대 경로는 레포 루트 기준.
                     예) models/local/vision/<name> (Mac, XNNPACK .pte) / models/board/vision/<name> (보드, QNN .pte)
  VISION_RUNNER_BIN  bundle이 cli runner를 쓸 때만: qnn_executor_runner 등 실행 파일 경로

모델·runner를 한 번 로드해 재사용하고, 추론은 전용 스레드 1개에서 직렬로 돌려 event loop를 막지 않는다.
bundle이 없거나 로드에 실패하면 ready=False + 명시적 오류. fixture/원격 자동 전환 없음.
"""

import asyncio
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from common.api import ApiError
from common.config import ROOT

log = logging.getLogger("vision.backend")


class DinoVisionBackend:
    source = "external"

    def __init__(self, bundle_path=None, runner_bin=None, runners=None):
        raw = bundle_path or os.environ.get("VISION_MODEL_PATH", "")
        self.path = (Path(raw) if Path(raw).is_absolute() else ROOT / raw) if raw else None
        self.runner_bin = runner_bin or os.environ.get("VISION_RUNNER_BIN") or None
        self._runners = runners
        self.pipeline = None
        self.error = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vision-infer")
        self._loading = None

    def _load(self):
        from services.vision.pipeline import VisionPipeline

        if self.path is None:
            raise FileNotFoundError("VISION_MODEL_PATH 가 설정되지 않음")
        return VisionPipeline(self.path, runner_bin=self.runner_bin, runners=self._runners)

    async def _ensure(self):
        if self.pipeline is not None:
            return True
        if self._loading is None:
            self._loading = asyncio.get_running_loop().run_in_executor(self.pool, self._load)
        try:
            self.pipeline = await self._loading
            self.error = None
            log.info("vision bundle loaded: %s", self.path)
            return True
        except Exception as e:  # 다음 호출에서 다시 시도
            self.error = f"{type(e).__name__}: {e}"
            log.error("vision bundle load failed: %s", self.error)
            self._loading = None
            return False

    async def ready(self):
        return await self._ensure()

    def _infer(self, data):
        img = Image.open(io.BytesIO(data))
        img.load()
        objects = self.pipeline.analyze(img)
        log.info("vision analyze: %d objects, %s", len(objects),
                 {k: round(v, 1) for k, v in self.pipeline.timing.items()})
        return objects

    async def infer(self, data: bytes, content_type: str, scene_id: str, scenario: str):
        # scenario 는 fixture 전용 (external 은 무시)
        if not await self._ensure():
            raise ApiError("vision_not_ready", f"Vision model is not loaded ({self.error})", 503, True)
        objects = await asyncio.get_running_loop().run_in_executor(self.pool, self._infer, data)
        return {"scene_id": scene_id, "source": self.source, "objects": objects}

    async def close(self):
        if self.pipeline is not None:
            await asyncio.get_running_loop().run_in_executor(self.pool, self.pipeline.close)
        self.pool.shutdown(wait=False)


def create_backend():
    return DinoVisionBackend()
