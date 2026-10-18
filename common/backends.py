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
        intent, item = "refill", current["item"]
        if re.search(r"\b(cancel|stop|never mind)\b", utterance):
            intent = "cancel"
        elif re.search(r"\b(no|nope|fine|don't need)\b", utterance):
            intent = "decline"
        else:
            utterance = re.sub(r"\b(orange juice|oj)\b", "orange_juice", utterance)
            named = utterance
            drinks = []
            for variant in ("sparkling_water", "coke_zero"):
                pattern = rf"\b{variant.replace('_', ' ')}\b"
                if re.search(pattern, named):
                    drinks.append(variant)
                    named = re.sub(pattern, "", named)
            drinks += [d for d in ("water", "coke", "coffee", "orange_juice", "soda") if re.search(rf"\b{d}\b", named)]
            if len(drinks) > 1 or re.search(
                r"\b(juice|lemonade|tea|time|maybe|whatever|not sure|ignore)\b", utterance
            ):
                intent = "not_understood"
            elif drinks:
                item = drinks[0]
            elif not re.search(
                r"yes|please|same|small|little|less|half|regular|normal|full", utterance
            ):
                intent = "not_understood"
        if intent == "refill" and item not in data.get("allowed_items", ["water", "coke", "coffee", "orange_juice"]):
            intent = "not_understood"
        result = {
            "intent": intent,
            "item": item if intent == "refill" else None,
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

    def __init__(self, settings=None):
        from common.config import load_settings

        self.settings = settings or load_settings()

    async def ready(self):
        from common.executorch import available

        s = self.settings
        return s.qwen_seq_len is not None and available(
            s.qnn_llama_runner, s.qwen_model_path, s.qwen_tokenizer_path
        )

    async def generate(self, body: Generation):
        import tempfile
        from pathlib import Path
        from common.executorch import asset, execute

        if not await self.ready():
            raise ApiError(
                "not_ready", "Configure Qwen runner, model, tokenizer and sequence limit", 503
            )
        if body.chat_template_kwargs.enable_thinking:
            raise ApiError(
                "unsupported_option", "Board runner supports non-thinking requests only", 422
            )
        # The track qwen3 runner must accept preformatted ChatML, as documented
        # in services/qwen/README.md. Do not ask the runner to wrap it a second time.
        prompt = (
            "".join(f"<|im_start|>{m.role}\n{m.content}<|im_end|>\n" for m in body.messages)
            + "<|im_start|>assistant\n<think>\n\n</think>\n\n"
        )
        s = self.settings
        with tempfile.TemporaryDirectory(prefix="refill-qwen-") as directory:
            work = Path(directory)
            await execute(
                [
                    str(asset(s.qnn_llama_runner)),
                    "--model_path",
                    str(asset(s.qwen_model_path)),
                    "--tokenizer_path",
                    str(asset(s.qwen_tokenizer_path)),
                    "--decoder_model_version",
                    "qwen3",
                    "--prompt",
                    prompt,
                    "--temperature",
                    str(body.temperature),
                    "--seq_len",
                    str(s.qwen_seq_len),
                    "--output_path",
                    str(work / "answer.txt"),
                ],
                work,
                s.inference_timeout,
            )
            path = work / "answer.txt"
            if not path.is_file() or path.stat().st_size > 1_000_000:
                raise ApiError(
                    "invalid_backend_output", "Qwen output file is missing or oversized", 502
                )
            try:
                content = path.read_text(encoding="utf-8").strip()
            except UnicodeError:
                raise ApiError(
                    "invalid_backend_output", "Qwen output is not UTF-8 text", 502
                ) from None
            if content.startswith(prompt):
                content = content[len(prompt) :].strip()
            for suffix in ("<|im_end|>", "<|endoftext|>"):
                content = content.removesuffix(suffix).strip()
            if not content:
                raise ApiError("invalid_backend_output", "Qwen produced empty output", 502)
            return {
                "model": body.model,
                "source": self.source,
                "choices": [
                    {"message": {"role": "assistant", "content": content}, "finish_reason": None}
                ],
                "runner_limits": {
                    "total_sequence_tokens": s.qwen_seq_len,
                    "completion_token_limit_enforced": False,
                },
            }


def external_adapter(path: str):
    """Explicit trusted module:factory, invoked once. Factory returns an async backend."""
    module, factory = path.split(":", 1)
    return getattr(importlib.import_module(module), factory)()
