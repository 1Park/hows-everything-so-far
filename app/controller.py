import asyncio
import time
from collections import deque

from app.hardware.io import BridgeHardware, MockHardware
from app.audio import BoardMicrophone
from app.events import EventLog
from app.speech import speech_for
from common.api import ApiError, log
from common.contracts import CurrentRequest, RequestCard, StateEvent, uid
from common.vision_categories import available_drinks, VISION_CATEGORY_MAP, VISION_CATEGORY_GROUPS

# What the board shows for each controller phase. Linux owns this mapping so a new
# state needs no firmware change; the MCU only applies the colour it is given.
# Few meanings only: waiting, thinking, asking, confirmed, amber while a reply is
# still being sought, and red for every way the request ends without a card.
WHITE, YELLOW, BLUE, GREEN, AMBER, RED = (
    (255, 255, 255),
    (255, 200, 0),
    (0, 80, 255),
    (0, 255, 0),
    (255, 110, 0),
    (255, 0, 0),
)
PHASE_COLOURS = {
    "idle": WHITE,
    "observing": YELLOW,
    "interpreting": YELLOW,
    "offered": BLUE,
    "listening": AMBER,
    "transcribing": YELLOW,
    "card": GREEN,
    "done": GREEN,
    "not_understood": AMBER,
    "skipped": RED,
    "declined": RED,
    "cancelled": RED,
    "expired": RED,
    "error": RED,
}

TERMINAL = {"idle", "done", "cancelled", "declined", "skipped", "expired", "error"}


class Controller:
    """One demo session at a time. Generation token invalidates ALL late work after cancel/reset."""

    def __init__(self, settings, clients, hardware=None):
        self.settings, self.clients = settings, clients
        self.hardware = hardware or (
            MockHardware()
            if settings.hardware_backend == "mock"
            else BridgeHardware(settings.bridge_timeout)
        )
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.subscribers = set()
        self.events = deque(maxlen=100)
        self.event_log = EventLog(settings.event_log_path, settings.low_fill_threshold)
        self.sequence, self.token = 0, 0
        self.instance_id = uid()
        self.session_id = uid()
        self.phase, self.message = "idle", "Start a demo to inspect the scene."
        self.led_colour = None
        self.scene = None
        self.target = None
        self.card = None
        self.snapshot = None
        self.qwen_source = None
        self.deadline = None
        self.last_error = None
        self.microphone = BoardMicrophone(settings)
        self.voice_task = None
        self.transcript = self.stt_source = None
        self.voice_retries = 0
        self.capture_status = None
        self.untrained_categories = False  # Session-only demo opt-in; never a production default.

    def state(self):
        return {
            "allowed_items": self.allowed_items(),
            "untrained_categories": self.untrained_categories,
            "instance_id": self.instance_id,
            "session_id": self.session_id,
            "phase": self.phase,
            "message": self.message,
            "scene": self.scene.model_dump() if self.scene else None,
            "target": self.target.model_dump() if self.target else None,
            "card": self.card.model_dump() if self.card else None,
            "snapshot_url": f"/api/snapshot/{self.session_id}" if self.snapshot else None,
            "qwen_source": self.qwen_source,
            "hardware_source": self.settings.hardware_backend,
            "last_error": self.last_error,
            "sequence": self.sequence,
            "deadline": self.deadline,
            "audio_input": self.settings.audio_input,
            "tts_backend": self.settings.tts_backend,
            "audio_seconds": self.settings.audio_seconds,
            "requires_confirmation": self.settings.require_confirmation,
            "transcript": self.transcript,
            "stt_source": self.stt_source,
            "capture": self.capture_status,
            "speech": (self.offer_message(self.target) if self.phase == "offered" and self.target
                       and (self.untrained_categories or self.target.item in ("coke", "coffee"))
                       else speech_for(self.phase, self.target, self.card,
                                       self.settings.item_confirm_threshold, self.allowed_items())),
        }

    def show_phase_led(self, phase):
        # Best effort only: the LED is an indicator, so a Bridge failure must never
        # interrupt the demo. The mock sequence drives its own colour on the MCU.
        colour = PHASE_COLOURS.get(phase)
        if colour is None or colour == self.led_colour:
            return
        self.led_colour = colour

        async def push():
            try:
                await self.hardware.set_color(*colour)
            except ApiError:
                pass

        try:
            self.launch(push())
        except RuntimeError:
            pass  # no running loop; nothing is watching the LED either

    def stage(self, name, started, **fields):
        """One line per pipeline step, so a slow run says which step was slow.

        The demo path had no timings at all: a long pause was visible but could
        have been the microphone, the model, or the board.
        """
        # The formatter only serialises a dict message, so fields go in the message.
        log.info(
            {
                "message": "stage",
                "stage": name,
                "elapsed_ms": round((time.perf_counter() - started) * 1000),
                **fields,
            }
        )

    def emit(self, phase, message):
        self.phase, self.message = phase, message
        self.sequence += 1
        self.show_phase_led(phase)
        event = StateEvent(sequence=self.sequence, state=self.state()).model_dump()
        self.events.append(event)
        self.event_log.record(event["state"])
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def launch(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def arm_deadline(self):
        self.deadline = time.time() + self.settings.response_timeout
        self.launch(self.expire(self.token, self.deadline))

    async def expire(self, token, deadline):
        await asyncio.sleep(max(0, deadline - time.time()))
        async with self.lock:
            if (
                token == self.token
                and self.deadline == deadline
                and self.phase in ("offered", "card", "not_understood")
            ):
                self.token += 1
                self.deadline = None
                self.emit("expired", "The request expired. Inspect the scene again to retry.")

    async def start(self, data: bytes, content_type: str, scenario: str, automatic=False,
                    preanalyzed=None, expected_token=None):
        async with self.lock:
            if automatic and (self.phase not in TERMINAL
                              or (expected_token is not None and expected_token != self.token)):
                return self.state()
            if self.phase in ("loading", "returning"):
                raise ApiError(
                    "sequence_running", "Cancel the sequence before observing another scene", 409
                )
            self.token += 1
            if self.voice_task:
                self.voice_task.cancel()
            token = self.token
            self.session_id, self.scene, self.target, self.card = uid(), None, None, None
            self.snapshot = (data, content_type)
            self.deadline, self.last_error, self.qwen_source = None, None, None
            self.transcript = self.stt_source = None
            scene_id = uid()
            self.emit("observing", "Inspecting the scene…")
            if preanalyzed is not None:
                self.apply_observation(preanalyzed)
            else:
                self.launch(self.observe(token, data, content_type, scene_id, scenario))
            return self.state()

    async def fail(self, token, error):
        async with self.lock:
            if token != self.token:
                return
            self.last_error = {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
            }
            self.deadline = None
            self.emit("error", error.message)

    async def observe(self, token, data, content_type, scene_id, scenario):
        try:
            started = time.perf_counter()
            async with asyncio.timeout(self.settings.inference_timeout):
                result = await self.clients.vision(data, content_type, scene_id, scenario)
            self.stage("vision", started, objects=len(result.objects))
            async with self.lock:
                if token != self.token:
                    return
                self.apply_observation(result)
        except TimeoutError:
            await self.fail(
                token,
                ApiError("vision_timeout", "Scene analysis timed out. Please retry", 504, True),
            )
        except ApiError as error:
            await self.fail(token, error)
        except Exception:
            log.exception("Scene analysis failed")
            await self.fail(
                token, ApiError("vision_error", "Scene analysis failed. Please retry", 502, True)
            )

    def apply_observation(self, result):
        """Caller holds lock. Keep selected frame and its exact analysis together."""
        self.scene = result
        # A new observation is a new request: it should not inherit the retry
        # budget spent on the previous one.
        self.voice_retries = 0
        eligible = [o for o in result.objects if o.item != "unknown"
                    and o.fill_ratio is not None
                    and o.confidence >= self.settings.min_confidence
                    and o.fill_ratio <= self.settings.low_fill_threshold]
        if not eligible:
            self.emit("skipped", "No confident low-fill cup was found. No refill will be suggested.")
            return
        self.target = min(eligible, key=lambda o: (o.fill_ratio, o.object_id))
        self.arm_deadline()
        self.emit("offered", self.offer_message(self.target))

    def allowed_items(self):
        return available_drinks((o.item for o in self.scene.objects), self.untrained_categories) if self.scene else []

    async def set_demo_features(self, enabled):
        async with self.lock:
            if enabled == self.untrained_categories:
                return self.state()
            if self.phase in ("observing", "interpreting", "listening", "transcribing", "loading", "returning"):
                raise ApiError("demo_feature_busy", "Wait for the current operation or cancel before changing demo features", 409)
            self.untrained_categories = enabled
            self.token += 1
            self.card = None  # A previous menu's approval cannot survive a feature change.
            if self.target and self.phase in ("offered", "card", "not_understood", "error"):
                self.arm_deadline()
                self.emit("offered", self.offer_message(self.target))
            else:
                self.emit(self.phase, self.message)
            return self.state()

    def offer_message(self, target):
        """A grouped observation always asks for the member, regardless of confidence."""
        grouped = len(VISION_CATEGORY_GROUPS.get(VISION_CATEGORY_MAP.get(target.item), ())) > 1
        if self.untrained_categories:
            options = available_drinks([target.item], demo=True)
            return "Would you like a refill? Please choose " + ", ".join(d.replace("_", " ") for d in options) + "."
        if grouped:
            return "Would you like a refill? Is that coke or coffee?"
        return f"Would you like a refill of {target.item}?"

    def check_target(self, body):
        if (
            not self.scene
            or not self.target
            or body.scene_id != self.scene.scene_id
            or body.object_id != self.target.object_id
        ):
            raise ApiError("stale_target", "This scene or target is no longer active", 409)

    async def utterance(self, body):
        if not body.utterance.strip():
            raise ApiError("empty_utterance", "Please enter a request", 422)
        async with self.lock:
            self.check_target(body)
            if self.phase not in ("offered", "card", "not_understood", "error"):
                raise ApiError(
                    "invalid_state", "A request cannot be edited in the current state", 409
                )
            self.begin_interpret(body.utterance)
            return self.state()

    def begin_interpret(self, utterance):
        """Caller holds self.lock; shared by typed input and board STT."""
        current = CurrentRequest(
            item=self.card.item if self.card else self.target.item,
            allowed_items=self.allowed_items(),
        )
        self.token += 1
        self.deadline, self.last_error = None, None
        self.emit("interpreting", "Understanding your request… You can cancel at any time.")
        self.launch(self.interpret(self.token, current, utterance))

    async def listen(self, body):
        """Tablet acknowledges finished playback; only the first current ack records."""
        async with self.lock:
            self.check_target(body)
            if (
                body.session_id != self.session_id
                or body.sequence != self.sequence
                or self.phase not in ("offered", "not_understood", "error")
            ):
                raise ApiError("stale_prompt", "This voice prompt is no longer active", 409)
            if self.deadline is not None and time.time() >= self.deadline:
                raise ApiError("expired", "This request has expired", 409)
            if not self.microphone.ready():
                raise ApiError(
                    "microphone_unavailable", "Configure the board microphone first", 503
                )
            self.token += 1
            token = self.token
            self.deadline, self.last_error = None, None
            self.transcript = self.stt_source = None
            self.emit("listening", "Listening on the board microphone. Please speak now.")
            task = asyncio.create_task(self.hear(token))
            self.voice_task = task
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            return self.state()

    # Asking again is better than failing, but only twice: the tablet records again
    # as soon as it reaches not_understood, so a microphone that hears nothing would
    # otherwise loop until the request expires.
    MAX_VOICE_RETRIES = 2

    async def retry_voice(self, token, message):
        async with self.lock:
            if token != self.token:
                return
            self.voice_retries += 1
            self.last_error = None
            self.arm_deadline()
            if self.voice_retries > self.MAX_VOICE_RETRIES:
                self.emit(
                    "error",
                    "I still couldn't hear your request. Please type it instead.",
                )
                return
            self.emit("not_understood", message)

    async def hear(self, token):
        try:
            started = time.perf_counter()
            audio = await self.microphone.capture()
            self.stage("record", started, bytes=len(audio))
            async with self.lock:
                if token != self.token:
                    return
                self.emit("transcribing", "Transcribing your request… You can cancel at any time.")
            started = time.perf_counter()
            async with asyncio.timeout(self.settings.inference_timeout):
                result = await self.clients.stt(audio, "audio/wav")
            self.stage("stt", started, source=result.source, chars=len(result.text))
            async with self.lock:
                if token != self.token:
                    return
                self.transcript, self.stt_source = result.text, result.source
                self.voice_retries = 0
                self.begin_interpret(result.text)
        except TimeoutError:
            await self.retry_voice(token, "Speech recognition took too long. Please speak again after the prompt.")
        except ApiError as error:
            if error.code in ("no_speech", "stt_timeout", "service_timeout"):
                await self.retry_voice(token, "I couldn't hear your request clearly. Please speak again after the prompt.")
            else:
                await self.fail(token, error)
        except Exception:
            log.exception("Board voice input failed")
            await self.fail(
                token, ApiError("voice_error", "Voice input failed. Please retry", 502, True)
            )

    async def interpret(self, token, current, utterance):
        try:
            started = time.perf_counter()
            async with asyncio.timeout(self.settings.inference_timeout):
                result, source = await self.clients.language(current, utterance)
            self.stage("language", started, intent=result.intent, source=source)
            async with self.lock:
                if token != self.token:
                    return
                self.qwen_source = source
                if result.intent in ("cancel", "decline"):
                    self.deadline = None
                    self.emit(
                        "cancelled" if result.intent == "cancel" else "declined",
                        "No refill will be started.",
                    )
                elif result.intent == "not_understood" or result.item not in current.allowed_items:
                    # Keep previous card as edit context, but phase blocks all confirmation.
                    self.arm_deadline()
                    self.emit(
                        "not_understood",
                        "I couldn't understand your request. Please choose "
                        + ", ".join(d.replace("_", " ") for d in current.allowed_items) + " from the observed scene.",
                    )
                else:
                    self.card = RequestCard(
                        request_id=self.card.request_id if self.card else uid(),
                        revision=self.card.revision + 1 if self.card else 1,
                        scene_id=self.scene.scene_id,
                        object_id=self.target.object_id,
                        item=result.item,
                    )
                    if self.settings.require_confirmation:
                        self.arm_deadline()
                        self.emit(
                            "card",
                            "Review your request, then press Confirm to start the mock sequence.",
                        )
                    else:
                        # Understanding the request is the approval. Invalidate earlier
                        # work the same way a press does, so a cancel that arrives first
                        # still wins and no stale task can start the sequence later.
                        self.deadline = None
                        self.token += 1
                        self.emit("loading", "Got it. Mock loading is starting…")
                        self.launch(self.run_hardware(self.token, self.card.request_id))
        except TimeoutError:
            await self.fail(
                token,
                ApiError(
                    "qwen_timeout", "Request interpretation timed out. Please retry", 504, True
                ),
            )
        except ApiError as error:
            await self.fail(token, error)
        except Exception:
            log.exception("Request interpretation failed")
            await self.fail(
                token,
                ApiError("qwen_error", "Request interpretation failed. Please retry", 502, True),
            )

    async def confirm(self, body):
        async with self.lock:
            self.check_target(body)
            if (
                self.phase != "card"
                or not self.card
                or body.request_id != self.card.request_id
                or body.revision != self.card.revision
            ):
                raise ApiError(
                    "stale_confirmation", "This request has changed or was already confirmed", 409
                )
            if self.deadline is None or time.time() >= self.deadline:
                raise ApiError("expired", "This request has expired", 409)
            self.token += 1
            token = self.token
            self.deadline = None
            self.emit("loading", "Confirmed. Mock loading is starting…")
            self.launch(self.run_hardware(token, self.card.request_id))
            return self.state()

    async def run_hardware(self, token, command_id):
        try:
            # Start is performed under the same lock as cancel. A cancelled approval cannot start later.
            async with self.lock:
                if token != self.token:
                    return
                await self.hardware.start(command_id)
            async with asyncio.timeout(30):
                while True:
                    await asyncio.sleep(self.settings.mock_step_seconds)
                    async with self.lock:
                        if token != self.token:
                            return
                        phase = await self.hardware.advance()
                        if phase == "done":
                            self.emit(
                                "done",
                                "Mock return complete. Your refill request is ready for the kitchen.",
                            )
                            return
                        if phase not in ("loading", "returning"):
                            raise ApiError(
                                "hardware_fault",
                                "The mock sequence stopped unexpectedly",
                                503,
                                True,
                            )
                        self.emit(
                            phase,
                            "Mock return to kitchen…" if phase == "returning" else "Mock loading…",
                        )
        except (ApiError, TimeoutError) as error:
            try:
                await self.hardware.cancel()
            except ApiError:
                pass
            await self.fail(
                token,
                error
                if isinstance(error, ApiError)
                else ApiError("hardware_timeout", "The sequence timed out", 504, True),
            )

    async def restart_session(self):
        """Return a finished demo to its first step.

        Re-arming automatic capture only resets the scanner, so the card,
        transcript and progress of the run that just ended stayed on screen while
        the board was already scanning for the next one.
        """
        async with self.lock:
            if self.phase not in TERMINAL:
                return self.state()
            self.token += 1
            self.session_id = uid()
            self.scene = self.target = self.card = self.snapshot = None
            self.transcript = self.stt_source = self.qwen_source = None
            self.deadline = self.last_error = None
            self.voice_retries = 0
            self.emit("idle", "Start a demo to inspect the scene.")
            return self.state()

    async def cancel(self, session_id):
        async with self.lock:
            if session_id != self.session_id:
                raise ApiError("stale_session", "This demo session is no longer active", 409)
            running = self.phase in ("loading", "returning")
            self.token += 1
            if self.voice_task:
                self.voice_task.cancel()
            self.deadline = None
            self.emit("cancelled", "Cancelled. No new action will be started.")
            if running:
                try:
                    await self.hardware.cancel()
                except ApiError as error:
                    self.last_error = {
                        "code": error.code,
                        "message": error.message,
                        "retryable": True,
                    }
                    self.emit("error", error.message)
            return self.state()

    async def close(self):
        self.token += 1
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.phase in ("loading", "returning"):
            await self.hardware.cancel()
        await self.clients.close()
