import asyncio
import time
from collections import deque

from app.hardware.io import BridgeHardware, MockHardware
from common.api import ApiError, log
from common.contracts import CurrentRequest, RequestCard, StateEvent, uid

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
        self.scene = None
        self.target = None
        self.card = None
        self.snapshot = None
        self.qwen_source = None
        self.deadline = None
        self.last_error = None

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
        }

    def emit(self, phase, message):
        self.phase, self.message = phase, message
        self.sequence += 1
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

    async def start(self, data: bytes, content_type: str, scenario: str):
        async with self.lock:
            if self.phase in ("loading", "returning"):
                raise ApiError(
                    "sequence_running", "Cancel the sequence before observing another scene", 409
                )
            self.token += 1
            token = self.token
            self.session_id, self.scene, self.target, self.card = uid(), None, None, None
            self.snapshot = (data, content_type)
            self.deadline, self.last_error, self.qwen_source = None, None, None
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
            current = CurrentRequest(
                item=self.card.item if self.card else self.target.item,
                portion=self.card.portion if self.card else "regular",
            )
            self.token += 1
            token = self.token
            self.deadline, self.last_error = None, None
            self.emit("interpreting", "Understanding your request… You can cancel at any time.")
            self.launch(self.interpret(token, current, body.utterance))
            return self.state()

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
