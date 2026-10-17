import asyncio
import time
from collections import deque

from app.hardware.io import BridgeHardware, MockHardware
from app.audio import BoardMicrophone
from common.api import ApiError, log
from common.contracts import CurrentRequest, RequestCard, StateEvent, uid

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
    "clarify": AMBER,
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

    def state(self):
        return {
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
            "audio_seconds": self.settings.audio_seconds,
            "transcript": self.transcript,
            "stt_source": self.stt_source,
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

    def emit(self, phase, message):
        self.phase, self.message = phase, message
        self.sequence += 1
        self.show_phase_led(phase)
        event = StateEvent(sequence=self.sequence, state=self.state()).model_dump()
        self.events.append(event)
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
                and self.phase in ("offered", "card", "clarify")
            ):
                self.token += 1
                self.deadline = None
                self.emit("expired", "The request expired. Inspect the scene again to retry.")

    async def start(self, data: bytes, content_type: str, scenario: str, automatic=False):
        async with self.lock:
            if automatic and self.phase not in ("idle", "skipped"):
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
            async with asyncio.timeout(self.settings.inference_timeout):
                result = await self.clients.vision(data, content_type, scene_id, scenario)
            async with self.lock:
                if token != self.token:
                    return
                self.scene = result
                eligible = [
                    o
                    for o in result.objects
                    if o.item != "unknown"
                    and o.fill_ratio is not None
                    and o.confidence >= self.settings.min_confidence
                    and o.fill_ratio <= self.settings.low_fill_threshold
                ]
                if not eligible:
                    self.emit(
                        "skipped",
                        "No confident low-fill cup was found. No refill will be suggested.",
                    )
                    return
                self.target = min(eligible, key=lambda o: (o.fill_ratio, o.object_id))
                # A proposal is NOT a confirmable card. A customer utterance is required.
                self.arm_deadline()
                self.emit("offered", self.offer_message(self.target))
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

    def offer_message(self, target):
        """Name the observed drink, or ask which one when Vision is unsure between look-alikes.

        Coke and coffee look alike in the same glass. The guess still seeds the request card,
        so the customer sees and can correct the drink before the explicit Confirm.
        """
        uncertain = (
            target.item in ("coke", "coffee")
            and target.item_confidence is not None
            and target.item_confidence < self.settings.item_confirm_threshold
        )
        if uncertain:
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
            if self.phase not in ("offered", "card", "clarify", "error"):
                raise ApiError(
                    "invalid_state", "A request cannot be edited in the current state", 409
                )
            self.begin_interpret(body.utterance)
            return self.state()

    def begin_interpret(self, utterance):
        """Caller holds self.lock; shared by typed input and board STT."""
        current = CurrentRequest(
            item=self.card.item if self.card else self.target.item,
            portion=self.card.portion if self.card else "regular",
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
                or self.phase not in ("offered", "clarify", "error")
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

    async def hear(self, token):
        try:
            audio = await self.microphone.capture()
            async with self.lock:
                if token != self.token:
                    return
                self.emit("transcribing", "Transcribing your request… You can cancel at any time.")
            async with asyncio.timeout(self.settings.inference_timeout):
                result = await self.clients.stt(audio, "audio/wav")
            async with self.lock:
                if token != self.token:
                    return
                self.transcript, self.stt_source = result.text, result.source
                self.begin_interpret(result.text)
        except TimeoutError:
            await self.fail(
                token,
                ApiError("stt_timeout", "Speech recognition timed out. Please retry", 504, True),
            )
        except ApiError as error:
            await self.fail(token, error)
        except Exception:
            log.exception("Board voice input failed")
            await self.fail(
                token, ApiError("voice_error", "Voice input failed. Please retry", 502, True)
            )

    async def interpret(self, token, current, utterance):
        try:
            async with asyncio.timeout(self.settings.inference_timeout):
                result, source = await self.clients.language(current, utterance)
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
                elif result.intent == "clarify":
                    # Keep previous card as edit context, but phase blocks all confirmation.
                    self.arm_deadline()
                    self.emit(
                        "clarify", "Please choose water, coke, or coffee, and small or regular."
                    )
                else:
                    self.card = RequestCard(
                        request_id=self.card.request_id if self.card else uid(),
                        revision=self.card.revision + 1 if self.card else 1,
                        scene_id=self.scene.scene_id,
                        object_id=self.target.object_id,
                        item=result.item,
                        portion=result.portion,
                    )
                    self.arm_deadline()
                    self.emit(
                        "card",
                        "Review your request, then press Confirm to start the mock sequence.",
                    )
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
