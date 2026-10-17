import asyncio
from contextlib import asynccontextmanager

from fastapi import File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.clients import ModelClients
from app.controller import Controller
from app.media import VideoSource
from common.api import ApiError, create_api
from common.config import ROOT, load_settings
from common.contracts import (
    CancelInput,
    ConfirmInput,
    UtteranceInput,
    StateSnapshot,
    StateEvent,
    Heartbeat,
)
from common.media import read_upload, validate_audio, validate_image


def create_app(settings=None, clients=None, hardware=None):
    settings = settings or load_settings()
    clients = clients or ModelClients(settings)
    controller = Controller(settings, clients, hardware)
    video = VideoSource(settings.camera_source)

    @asynccontextmanager
    async def lifespan(app):
        video.start()
        yield
        video.close()
        await controller.close()

    app = create_api("Controller", lifespan)
    app.state.controller, app.state.video = controller, video

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "app/ui/index.html")

    app.mount("/ui", StaticFiles(directory=ROOT / "app/ui"), name="ui")

    @app.get("/ready")
    async def ready():
        dependencies = await clients.ready()
        hardware_ready = True
        if settings.hardware_backend == "bridge":
            try:
                async with asyncio.timeout(settings.bridge_timeout):
                    await controller.hardware.read()
            except Exception:
                hardware_ready = False
        ok = (
            all(v["ready"] for v in dependencies.values())
            and not video.error
            and video.latest is not None
            and hardware_ready
        )
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "ready": ok,
                "dependencies": dependencies,
                "video": {"mode": video.mode, "error": video.error},
                "hardware": settings.hardware_backend,
                "hardware_ready": hardware_ready,
                "location": settings.app_env,
            },
        )

    @app.get("/api/state", response_model=StateSnapshot)
    async def state():
        return controller.state()

    @app.post("/api/observe", status_code=202, response_model=StateSnapshot)
    async def observe(
        scenario: str = Form("normal", pattern="^(normal|enough|uncertain)$"),
        file: UploadFile | None = File(None),
    ):
        if file:
            mime = file.content_type or ""
            data = await read_upload(file, settings.max_image_bytes)
            validate_image(data, mime)
        else:
            data, mime = video.frame()
            if len(data) > settings.max_image_bytes:
                raise ApiError("invalid_size", "Captured image exceeds the size limit", 413)
            validate_image(data, mime)
        return await controller.start(data, mime, scenario)

    @app.post("/api/utterance", status_code=202, response_model=StateSnapshot)
    async def utterance(body: UtteranceInput):
        return await controller.utterance(body)

    @app.post("/api/confirm", status_code=202, response_model=StateSnapshot)
    async def confirm(body: ConfirmInput):
        return await controller.confirm(body)

    @app.post("/api/cancel", response_model=StateSnapshot)
    async def cancel(body: CancelInput):
        return await controller.cancel(body.session_id)

    @app.post("/api/transcribe")
    async def transcribe(file: UploadFile = File(...)):
        mime = file.content_type or ""
        data = await read_upload(file, settings.max_audio_bytes)
        validate_audio(data, mime)
        try:
            async with asyncio.timeout(settings.inference_timeout):
                return await clients.stt(data, mime)
        except TimeoutError:
            raise ApiError(
                "stt_timeout", "Audio transcription timed out. Please retry", 504, True
            ) from None

    @app.get("/api/frame")
    async def frame():
        data, mime = video.frame()
        return Response(data, media_type=mime, headers={"Cache-Control": "no-store"})

    @app.get("/api/video")
    async def stream():
        video.frame()  # fail before sending headers
        return StreamingResponse(
            video.frames(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.get("/api/snapshot/{session_id}")
    async def snapshot(session_id: str):
        if session_id != controller.session_id or not controller.snapshot:
            raise ApiError("snapshot_expired", "This scene snapshot is no longer available", 404)
        data, mime = controller.snapshot
        return Response(data, media_type=mime, headers={"Cache-Control": "no-store"})

    @app.get("/api/hardware")
    async def hardware_state():
        return await controller.hardware.read()

    @app.websocket("/ws")
    async def events(websocket: WebSocket):
        await websocket.accept()
        queue = asyncio.Queue(maxsize=16)
        controller.subscribers.add(queue)
        try:
            await websocket.send_json(
                StateEvent(sequence=controller.sequence, state=controller.state()).model_dump()
            )
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    event = Heartbeat(sequence=controller.sequence).model_dump()
                await websocket.send_json(event)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            controller.subscribers.discard(queue)

    return app
