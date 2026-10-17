from contextlib import asynccontextmanager

from fastapi.responses import JSONResponse

from common.api import ApiError, InferenceGate, create_api
from common.backends import FixtureTextBackend, MLXBackend
from common.config import load_settings
from common.contracts import Generation
from services.qwen.board_llm import BoardLLMBackend


def create_app(settings=None, backend=None):
    settings = settings or load_settings()
    backend = (
        backend
        or {
            "fixture": lambda: FixtureTextBackend(),
            "executorch": lambda: BoardLLMBackend(),
            "mlx": lambda: MLXBackend(
                str(settings.qwen_upstream_url), settings.qwen_model, settings.inference_timeout
            ),
        }[settings.qwen_model_backend]()
    )
    gate = InferenceGate(settings.queue_limit, settings.inference_timeout)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if hasattr(backend, "close"):
            await backend.close()

    app = create_api("Qwen", lifespan)

    @app.get("/ready")
    async def ready():
        ok = await backend.ready()
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "ready": ok,
                "source": backend.source,
                "model": settings.qwen_model,
                "pending": gate.pending,
                "capacity": gate.capacity,
                "runner": getattr(backend, "status", None),
            },
        )

    @app.get("/v1/models")
    async def models():
        if not await backend.ready():
            raise ApiError("not_ready", "Qwen backend is not ready", 503, True)
        ids = dict.fromkeys([settings.qwen_model, *getattr(backend, "model_ids", ())])
        return {"object": "list", "source": backend.source, "data": [{"id": m} for m in ids]}

    @app.post("/v1/chat/completions")
    async def complete(body: Generation):
        if body.model != settings.qwen_model and body.model not in getattr(backend, "model_ids", ()):
            raise ApiError("unknown_model", "Requested model is not configured", 422)
        async with gate.slot():
            result = await backend.generate(body)
        return {**result, "source": backend.source}

    return app
