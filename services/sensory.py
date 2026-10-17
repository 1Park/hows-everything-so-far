"""Vision/STT service layer only. External backends own all model-specific processing."""

from contextlib import asynccontextmanager

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from common.api import ApiError, InferenceGate, create_api
from common.backends import external_adapter
from common.config import ROOT, load_settings
from common.contracts import STTResult, VisionResult
from common.media import read_upload, validate_audio, validate_image


class FixtureVision:
    async def ready(self):
        return True

    async def infer(self, data: bytes, content_type: str, scene_id: str, scenario: str):
        import json

        value = json.loads((ROOT / "fixtures/vision.json").read_text(encoding="utf-8"))
        value["scene_id"] = scene_id
        if scenario == "enough":
            for item in value["objects"]:
                item["fill_ratio"] = 0.85
        elif scenario == "uncertain":
            for item in value["objects"]:
                item["confidence"] = 0.2
        return VisionResult.model_validate(value)


class FixtureSTT:
    async def ready(self):
        return True

    async def infer(self, data: bytes, content_type: str):
        return STTResult(text="A little water, please", source="fixture")


def create_sensory_app(kind: str, settings=None, backend=None):
    settings = settings or load_settings()
    mode = getattr(settings, f"{kind}_model_backend")
    backend = backend or (
        external_adapter(getattr(settings, f"{kind}_adapter"))
        if mode == "external"
        else {"vision": FixtureVision, "stt": FixtureSTT}[kind]()
    )
    source = "external" if mode == "external" else "fixture"
    gate = InferenceGate(settings.queue_limit, settings.inference_timeout)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if hasattr(backend, "close"):
            await backend.close()

    app = create_api(kind.upper(), lifespan)

    @app.get("/ready")
    async def ready():
        try:
            import asyncio

            ok = bool(await asyncio.wait_for(backend.ready(), timeout=4))
        except Exception:
            ok = False
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"ready": ok, "source": source, "pending": gate.pending},
        )

    if kind == "vision":

        @app.post("/v1/analyze", response_model=VisionResult)
        async def analyze(
            file: UploadFile = File(...),
            scene_id: str = Form(..., min_length=1, max_length=100),
            scenario: str = Form("normal", pattern="^(normal|enough|uncertain)$"),
        ):
            content_type = file.content_type or ""
            data = await read_upload(file, settings.max_image_bytes)
            validate_image(data, content_type)
            async with gate.slot():
                try:
                    result = VisionResult.model_validate(
                        await backend.infer(data, content_type, scene_id, scenario)
                    )
                except ValidationError:
                    raise ApiError(
                        "invalid_backend_output", "Vision returned an invalid response", 502
                    ) from None
                except ApiError:
                    raise
                except Exception:
                    raise ApiError(
                        "backend_error", "Vision backend failed. Please retry", 502, True
                    ) from None
            if result.scene_id != scene_id or result.source != source:
                raise ApiError(
                    "invalid_backend_output",
                    "Vision response identity or source does not match",
                    502,
                )
            return result
    else:

        @app.post("/v1/transcribe", response_model=STTResult)
        async def transcribe(file: UploadFile = File(...)):
            content_type = file.content_type or ""
            data = await read_upload(file, settings.max_audio_bytes)
            validate_audio(data, content_type)
            async with gate.slot():
                try:
                    result = STTResult.model_validate(await backend.infer(data, content_type))
                except ValidationError:
                    raise ApiError(
                        "invalid_backend_output", "STT returned an invalid response", 502
                    ) from None
                except ApiError:
                    raise
                except Exception:
                    raise ApiError(
                        "backend_error", "STT backend failed. Please retry", 502, True
                    ) from None
            if result.source != source:
                raise ApiError("invalid_backend_output", "STT response source does not match", 502)
            return result

    return app
