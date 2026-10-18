import asyncio
import json
import time

import httpx
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import File, Form, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.clients import ModelClients
from app.capture import AutoCapture
from app.controller import Controller
from app.events import EventLog
from app.media import VideoSource
from common.api import ApiError, create_api
from common.config import ROOT, load_settings
from common.vision_categories import VISION_CATEGORY_GROUPS
from common.contracts import (
    CancelInput,
    ConfirmInput,
    UtteranceInput,
    StateSnapshot,
    StateEvent,
    Heartbeat,
    ListenInput,
    SttTake,
    CaptureModeInput,
    CaptureStatus,
    DemoFeaturesInput,
)
from services.stt.normalize import normalize
from common.media import read_upload, validate_audio, validate_image


def create_app(settings=None, clients=None, hardware=None):
    settings = settings or load_settings()
    clients = clients or ModelClients(settings)
    controller = Controller(settings, clients, hardware)
    video = VideoSource(settings.camera_source, settings.camera_fps, settings.video_stream_fps)
    capture = AutoCapture(controller, video)

    @asynccontextmanager
    async def lifespan(app):
        video.start()

        watcher = asyncio.create_task(capture.run())
        try:
            yield
        finally:
            if watcher:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)
            video.close()
            await controller.close()

    app = create_api("Controller", lifespan)
    app.state.controller, app.state.video, app.state.capture = controller, video, capture

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

        def is_not_modified(self, *args, **kwargs):
            # no-store alone was not enough: a copy cached before the header existed
            # still revalidated into a 304, so the tablet kept running old code.
            return False

    app.mount("/ui", FreshStaticFiles(directory=ROOT / "app/ui"), name="ui")

    @app.get("/dashboard")
    async def dashboard():
        return FileResponse(ROOT / "app/ui/dashboard.html", headers=no_store)

    mock_events = EventLog(ROOT / "fixtures/mock_events.jsonl")

    @app.get("/api/events")
    async def events_history():
        # The week of mock history plus whatever this board has really recorded;
        # mock rows carry "mock": true so the dashboard can tell them apart.
        return {"events": mock_events.read() + controller.event_log.read()}

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

    @app.get("/api/vision-categories")
    async def vision_categories():
        return {"groups": VISION_CATEGORY_GROUPS, "editable": False,
                "scope": "DINO classifier post-processing"}

    @app.post("/api/demo-features", response_model=StateSnapshot)
    async def demo_features(body: DemoFeaturesInput):
        return await controller.set_demo_features(body.untrained_categories)

    @app.get("/api/capture", response_model=CaptureStatus)
    async def capture_status():
        return controller.capture_status

    @app.post("/api/capture", response_model=CaptureStatus)
    async def capture_mode(body: CaptureModeInput):
        return capture.set_mode(body.mode)

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

    # One file so a take survives a refresh, a new tab, or someone else's browser.
    # Kept under docs/ because these numbers are the evidence for the write-up.
    takes_file = Path(settings.stt_takes_file)
    if not takes_file.is_absolute():
        takes_file = ROOT / takes_file

    def read_takes():
        try:
            return json.loads(takes_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def write_takes(takes):
        takes_file.parent.mkdir(parents=True, exist_ok=True)
        takes_file.write_text(json.dumps(takes, ensure_ascii=False, indent=2), encoding="utf-8")

    @app.get("/api/stt/results")
    async def stt_results():
        return {"takes": read_takes()}

    @app.post("/api/stt/results")
    async def stt_add_result(take: SttTake):
        takes = read_takes()
        takes.append(take.model_dump(mode="json"))
        write_takes(takes)
        return {"takes": takes}

    @app.delete("/api/stt/results")
    async def stt_delete_results(
        index: int = Query(default=-1, ge=-1),
        take_id: str = Query(default="", max_length=40),
    ):
        takes = read_takes()
        if take_id:
            # One recording produced a row per model; discarding it drops them all.
            takes = [take for take in takes if take.get("take_id") != take_id]
        elif index < 0:
            takes = []
        elif index < len(takes):
            takes.pop(index)
        write_takes(takes)
        return {"takes": takes}

    def compare_targets():
        """Extra models to transcribe the same audio with, as label=url pairs."""
        targets = []
        for entry in settings.stt_compare.split(","):
            label, _, url = entry.partition("=")
            if label.strip() and url.strip():
                targets.append((label.strip(), url.strip().rstrip("/")))
        return targets

    async def transcribe_with(label, url, audio):
        started = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=settings.inference_timeout, trust_env=False
            ) as http:
                response = await http.post(
                    url + "/inference",
                    files={"file": ("request.wav", audio, "audio/wav")},
                    data={"language": "en", "response_format": "json", "temperature": "0"},
                )
                response.raise_for_status()
                text = normalize(response.json()["text"]).text
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            return {"model": label, "error": type(error).__name__, "text": "", "stt_ms": 0}
        return {
            "model": label,
            "text": text,
            "stt_ms": round((time.perf_counter() - started) * 1000),
        }

    @app.post("/api/stt/check")
    async def stt_check(seconds: int = Query(default=0, ge=0, le=15)):
        """Record from the board microphone and transcribe it, outside the demo flow.

        The refill path only listens while an offer is on screen and moves the
        controller through phases, which makes it useless for measuring the model.
        This records and transcribes and changes nothing else.
        """
        length = seconds or settings.audio_seconds
        started = time.perf_counter()
        audio = await controller.microphone.capture(length)
        recorded = time.perf_counter()
        try:
            async with asyncio.timeout(settings.inference_timeout):
                result = await clients.stt(audio, "audio/wav")
        except TimeoutError:
            raise ApiError(
                "stt_timeout", "Audio transcription timed out. Please retry", 504, True
            ) from None
        done = time.perf_counter()
        # Every model hears the identical recording, so a difference between them is
        # the model and not a difference in how the sentence happened to be spoken.
        extra = await asyncio.gather(
            *(transcribe_with(label, url, audio) for label, url in compare_targets())
        )
        # Transcription is a near-fixed cost here, so it is reported apart from the
        # take length: shortening the recording does not shorten the wait.
        return {
            "text": result.text,
            "source": result.source,
            "seconds": length,
            "bytes": len(audio),
            "record_ms": round((recorded - started) * 1000),
            "stt_ms": round((done - recorded) * 1000),
            "others": list(extra),
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
