"""TTS 서비스: POST /v1/speak {"text"} → audio/wav. 기본 127.0.0.1:8003, 보드 전용 (Piper + NPU 디코더)."""

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import Response
from fastapi.responses import JSONResponse

from common.api import ApiError, InferenceGate, create_api
from common.config import load_settings
from common.contracts import SpeechRequest


def create_app(settings=None, backend=None):
    settings = settings or load_settings()
    gate = InferenceGate(settings.queue_limit, settings.inference_timeout)
    state = {"backend": backend, "error": None}

    @asynccontextmanager
    async def lifespan(app):
        if state["backend"] is None:
            try:
                from services.tts.backend import PiperTTS

                state["backend"] = await asyncio.to_thread(
                    PiperTTS, settings.tts_voice_path, settings.tts_decoder_dir,
                    settings.tts_worker_bin or settings.vision_worker_bin,
                )
            except Exception as error:  # 준비 실패는 /ready 503으로 알린다 (fixture 대체 없음)
                state["error"] = f"{type(error).__name__}: {error}"
        try:
            yield
        finally:
            if hasattr(state["backend"], "close"):
                state["backend"].close()

    app = create_api("TTS", lifespan)

    @app.get("/ready")
    async def ready():
        tts = state["backend"]
        ok = tts is not None
        return JSONResponse(status_code=200 if ok else 503, content={
            "ready": ok, "pending": gate.pending, "error": state["error"],
            **({"tts": tts.status} if ok and hasattr(tts, "status") else {}),
        })

    @app.post("/v1/speak")
    async def speak(body: SpeechRequest):
        tts = state["backend"]
        if tts is None:
            raise ApiError("tts_not_ready", f"TTS is not ready ({state['error']})", 503, True)
        async with gate.slot():
            try:
                wav = await asyncio.to_thread(tts.synthesize, body.text)
            except ValueError as error:
                raise ApiError("invalid_text", str(error), 422) from None
        timing = getattr(tts, "last", {})
        return Response(wav, media_type="audio/wav", headers={"x-tts-timing": json.dumps(timing)})

    return app
