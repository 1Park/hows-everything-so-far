import asyncio
import importlib
import json
import re
from typing import Protocol

import httpx

from common.api import ApiError, request_id
from common.contracts import Generation, uid


class TextBackend(Protocol):
    source: str

    async def ready(self) -> bool: ...
    async def generate(self, body: Generation) -> dict: ...


class MLXBackend:
    source = "mlx"

    def __init__(self, url: str, model: str, timeout: float):
        self.url, self.model = url.rstrip("/"), model
        self.client = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def ready(self) -> bool:
        try:
            response = await self.client.get(f"{self.url}/v1/models", timeout=4)
            response.raise_for_status()
            data = response.json()["data"]
            return isinstance(data, list) and any(
                isinstance(row, dict) and row.get("id") == self.model for row in data
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False

    async def generate(self, body: Generation) -> dict:
        payload = body.model_dump()
        payload["chat_template_kwargs"] = {"enable_thinking": False}
        try:
            response = await self.client.post(
                f"{self.url}/v1/chat/completions",
                json=payload,
                headers={"x-request-id": request_id.get() if request_id.get() != "-" else uid()},
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result["choices"][0]["message"]["content"], str):
                raise ValueError()
            return result
        except httpx.TimeoutException:
            raise ApiError("model_timeout", "The model endpoint timed out", 504, True) from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise ApiError(
                "model_unavailable",
                "The model endpoint returned an invalid response or is unavailable",
                502,
                True,
            ) from None

    async def close(self):
        await self.client.aclose()


class FixtureTextBackend:
    """Deterministic simulator. Explicit mode, never used as a fallback for MLX errors."""

    source = "fixture"

    async def ready(self):
        return True

    async def generate(self, body: Generation):
        await asyncio.sleep(0.04)
        try:
            data = json.loads(body.messages[-1].content)
            utterance = data["utterance"].lower().strip()
            current = data["current_request"]
        except (ValueError, KeyError, TypeError):
            raise ApiError(
                "fixture_input", "Fixture expects a current_request and utterance", 422
            ) from None
        intent, item, portion = "refill", current["item"], current["portion"]
        if re.search(r"\b(cancel|stop|never mind)\b", utterance):
            intent = "cancel"
        elif re.search(r"\b(no|nope|fine|don't need)\b", utterance):
            intent = "decline"
        else:
            drinks = [d for d in ("water", "coke", "coffee") if re.search(rf"\b{d}\b", utterance)]
            if len(drinks) > 1 or re.search(
                r"\b(juice|tea|time|maybe|whatever|not sure|ignore)\b", utterance
            ):
                intent = "clarify"
            elif drinks:
                item = drinks[0]
            elif not re.search(
                r"yes|please|same|small|little|less|half|regular|normal|full", utterance
            ):
                intent = "clarify"
            if re.search(r"small|little|less|half", utterance):
                portion = "small"
            elif re.search(r"regular|normal|full", utterance):
                portion = "regular"
        result = {
            "intent": intent,
            "item": item if intent == "refill" else None,
            "portion": portion if intent == "refill" else None,
        }
        return {
            "model": body.model,
            "source": "fixture",
            "choices": [
                {
                    "message": {"role": "assistant", "content": json.dumps(result)},
                    "finish_reason": "stop",
                }
            ],
        }


class ExecuTorchBackend:
    source = "executorch"

    async def ready(self):
        return False

    async def generate(self, body: Generation):
        raise ApiError(
            "backend_not_configured", "ExecuTorch requires the board runtime adapter", 503
        )


def external_adapter(path: str):
    """Explicit trusted module:factory, invoked once. Factory returns an async backend."""
    module, factory = path.split(":", 1)
    return getattr(importlib.import_module(module), factory)()
