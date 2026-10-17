"""Public transport contract v1. Model-internal tensors/preprocessing are not specified."""

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Drink = Literal["water", "coke", "coffee"]
Portion = Literal["small", "regular"]
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
    portion: Portion


class Interpretation(Contract):
    intent: Literal["refill", "decline", "cancel", "clarify"]
    item: Drink | None
    portion: Portion | None

    @model_validator(mode="after")
    def coherent(self):
        if self.intent == "refill" and (self.item is None or self.portion is None):
            raise ValueError("Refill requires item and portion")
        if self.intent != "refill" and (self.item is not None or self.portion is not None):
            raise ValueError("Non-refill fields must be null")
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


class ErrorBody(Contract):
    code: str
    message: str
    request_id: str
    retryable: bool


Phase = Literal[
    "idle",
    "observing",
    "offered",
    "interpreting",
    "clarify",
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


class StateEvent(Contract):
    type: Literal["state"] = "state"
    version: Literal[1] = 1
    sequence: int = Field(ge=0)
    state: StateSnapshot


class Heartbeat(Contract):
    type: Literal["heartbeat"] = "heartbeat"
    sequence: int = Field(ge=0)
