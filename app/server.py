import asyncio
from contextlib import asynccontextmanager

from fastapi import File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
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
    ListenInput,
)
from common.media import read_upload, validate_audio, validate_image


def create_app(settings=None, clients=None, hardware=None):
    settings = settings or load_settings()
    clients = clients or ModelClients(settings)
    controller = Controller(settings, clients, hardware)
    video = VideoSource(settings.camera_source, settings.camera_fps, settings.video_stream_fps)

    @asynccontextmanager
    async def lifespan(app):
        video.start()

        async def watch_scene():
            while True:
                await asyncio.sleep(max(0.2, settings.observe_interval_seconds))
                # Pause for the whole customer interaction. Never interrupt a card/sequence.
                if controller.phase in ("idle", "skipped"):
                    try:
                        data, mime = video.frame()
                        validate_image(data, mime)
                        if len(data) <= settings.max_image_bytes:
                            await controller.start(data, mime, "normal", automatic=True)
                    except ApiError:
                        pass

        watcher = asyncio.create_task(watch_scene()) if settings.observe_interval_seconds else None
        try:
            yield
        finally:
            if watcher:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            video.close()
            await controller.close()

    app = create_api("Controller", lifespan)
    app.state.controller, app.state.video = controller, video

    # The tablet kept running an older app.js after a deploy because the browser
    # revalidated into a 304. The UI is tiny and served over a direct link, so
    # always send the current bytes rather than debug a stale page mid-demo.
    no_store = {"Cache-Control": "no-store"}

    @app.get("/")
    async def index():
        return FileResponse(ROOT / "app/ui/index.html", headers=no_store)

    class FreshStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            response.headers.update(no_store)
            return response

    app.mount("/ui", FreshStaticFiles(directory=ROOT / "app/ui"), name="ui")

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
            and (settings.audio_input == "disabled" or controller.microphone.ready())
        )
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "ready": ok,
                "dependencies": dependencies,
                "video": {"mode": video.mode, "error": video.error},
                # UI가 리필 대상 박스를 Controller와 같은 기준으로 표시하도록
                "policy": {
                    "min_confidence": settings.min_confidence,
                    "low_fill_threshold": settings.low_fill_threshold,
                },
                "hardware": settings.hardware_backend,
                "hardware_ready": hardware_ready,
                "location": settings.app_env,
                "audio_input": {
                    "backend": settings.audio_input,
                    "ready": controller.microphone.ready(),
                },
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

    @app.post("/api/voice/listen", status_code=202, response_model=StateSnapshot)
    async def listen(body: ListenInput):
        return await controller.listen(body)

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

    @app.post("/api/stt/check")
    async def stt_check(seconds: int = Query(default=0, ge=0, le=15)):
        """Record from the board microphone and transcribe it, outside the demo flow.

        The refill path only listens while an offer is on screen and moves the
        controller through phases, which makes it useless for measuring the model.
        This records and transcribes and changes nothing else.
        """
        length = seconds or settings.audio_seconds
        audio = await controller.microphone.capture(length)
        try:
            async with asyncio.timeout(settings.inference_timeout):
                result = await clients.stt(audio, "audio/wav")
        except TimeoutError:
            raise ApiError(
                "stt_timeout", "Audio transcription timed out. Please retry", 504, True
            ) from None
        return {
            "text": result.text,
            "source": result.source,
            "seconds": length,
            "bytes": len(audio),
        }

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
