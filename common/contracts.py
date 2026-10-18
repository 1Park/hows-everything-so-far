"""Public transport contract v1. Model-internal tensors/preprocessing are not specified."""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Drink = Literal["water", "coke", "coffee"]
Source = Literal["fixture", "external", "mlx", "executorch"]


def uid() -> str:
    return str(uuid4())


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BBox(Contract):
    """Normalized xyxy relative to the full input image, origin top-left."""

    x1: float = Field(ge=0, le=1)
    y1: float = Field(ge=0, le=1)
    x2: float = Field(ge=0, le=1)
    y2: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def positive(self):
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("Bounding box must have positive area")
        return self


class ObservedObject(Contract):
    object_id: str = Field(min_length=1, max_length=100)
    bbox: BBox
    item: Drink | Literal["unknown"]
    fill_ratio: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    # Optional: confidence in the drink identity alone (which drink, given there is one).
    # `confidence` above covers drink and fill together; this lets the Controller ask the
    # customer when only the drink is uncertain (e.g. coke vs coffee). None = not provided.
    item_confidence: float | None = Field(default=None, ge=0, le=1)


class VisionResult(Contract):
    scene_id: str = Field(min_length=1, max_length=100)
    objects: list[ObservedObject] = Field(max_length=50)
    source: Literal["fixture", "external"]

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [o.object_id for o in self.objects]
        if len(set(ids)) != len(ids):
            raise ValueError("Object IDs must be unique within a scene")
        return self


class STTResult(Contract):
    text: str = Field(min_length=1, max_length=1000)
    language: Literal["en"] = "en"
    source: Literal["fixture", "external"]


class CurrentRequest(Contract):
    item: Drink


class Interpretation(Contract):
    intent: Literal["refill", "decline", "cancel", "not_understood"]
    item: Drink | None

    @model_validator(mode="after")
    def coherent(self):
        if self.intent == "refill" and self.item is None:
            raise ValueError("Refill requires an item")
        if self.intent != "refill" and self.item is not None:
            raise ValueError("Non-refill item must be null")
        return self


class Message(Contract):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=16000)


class TemplateOptions(Contract):
    enable_thinking: Literal[False] = False


class Generation(Contract):
    model: str = Field(min_length=1, max_length=200)
    messages: list[Message] = Field(min_length=1, max_length=8)
    temperature: float = Field(0, ge=0, le=1)
    max_completion_tokens: int = Field(192, ge=16, le=512)
    stream: Literal[False] = False
    chat_template_kwargs: TemplateOptions = Field(default_factory=TemplateOptions)


class RequestCard(CurrentRequest):
    request_id: str
    scene_id: str
    object_id: str
    revision: int = Field(ge=1)


class TargetInput(Contract):
    scene_id: str = Field(min_length=1, max_length=100)
    object_id: str = Field(min_length=1, max_length=100)


class UtteranceInput(TargetInput):
    utterance: str = Field(min_length=1, max_length=1000)


class ConfirmInput(TargetInput):
    request_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)


class CancelInput(Contract):
    session_id: str = Field(min_length=1, max_length=100)


class ListenInput(TargetInput):
    session_id: str = Field(min_length=1, max_length=100)
    sequence: int = Field(ge=0)


class ErrorBody(Contract):
    code: str
    message: str
    request_id: str
    retryable: bool


Phase = Literal[
    "idle",
    "observing",
    "offered",
    "listening",
    "transcribing",
    "interpreting",
    "not_understood",
    "card",
    "loading",
    "returning",
    "done",
    "skipped",
    "declined",
    "cancelled",
    "expired",
    "error",
]


class StateError(Contract):
    code: str
    message: str
    retryable: bool


class CaptureModeInput(Contract):
    mode: Literal["manual", "auto"]


class CaptureStatus(Contract):
    mode: Literal["manual", "auto"] = "manual"
    status: Literal["manual", "scanning", "stabilizing", "paused", "waiting", "error"] = "manual"
    revision: int = 0
    stable_seconds: float = 0
    required_seconds: float = 5
    samples: int = 0
    source: Literal["fixture", "external"] | None = None
    overlap_area: float | None = None
    error: str | None = None


class SpeechRequest(Contract):
    text: str = Field(min_length=1, max_length=400)


class StateSnapshot(Contract):
    instance_id: str
    session_id: str
    phase: Phase
    message: str
    scene: VisionResult | None
    target: ObservedObject | None
    card: RequestCard | None
    snapshot_url: str | None
    qwen_source: Source | None
    hardware_source: Literal["mock", "bridge"]
    last_error: StateError | None
    sequence: int = Field(ge=0)
    deadline: float | None
    transcript: str | None = None
    stt_source: Literal["fixture", "external"] | None = None
    audio_input: Literal["disabled", "fixture", "alsa"] = "disabled"
    # How long board capture runs, so the page can show the time passing.
    audio_seconds: int = 6
    capture: CaptureStatus | None = None
    # What the assistant says for this state (board TTS); None = stay silent.
    speech: str | None = None


class StateEvent(Contract):
    type: Literal["state"] = "state"
    version: Literal[1] = 1
    sequence: int = Field(ge=0)
    state: StateSnapshot


class Heartbeat(Contract):
    type: Literal["heartbeat"] = "heartbeat"
    sequence: int = Field(ge=0)


class SttTake(BaseModel):
    """One accuracy-check attempt, stored so the numbers survive a page reload."""

    model_config = ConfigDict(extra="forbid")

    expected: str = Field(min_length=1, max_length=1000)
    heard: str = Field(default="", max_length=1000)
    wer: float = Field(ge=0, le=10)
    seconds: int = Field(ge=1, le=15)
    source: str = Field(default="", max_length=40)
    at: str = Field(default="", max_length=40)
    # Measured on the board. Transcription dominates and barely varies with the
    # take length, so the two are kept apart rather than summed.
    record_ms: int = Field(default=0, ge=0)
    stt_ms: int = Field(default=0, ge=0)
    # Which model produced `heard`. Several rows can share take_id: one recording
    # is transcribed by every model, so their numbers are directly comparable.
    model: str = Field(default="", max_length=60)
    take_id: str = Field(default="", max_length=40)
