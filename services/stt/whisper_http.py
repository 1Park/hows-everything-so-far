"""Contract adapter for an existing whisper.cpp server, with no model/preprocessing."""

import httpx

from common.api import ApiError
from common.config import load_settings
from common.contracts import STTResult


class WhisperHTTP:
    def __init__(self, settings=None):
        self.settings = settings or load_settings()

    async def ready(self):
        async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
            response = await client.get(str(self.settings.stt_whisper_url).rstrip("/") + "/health")
            return response.status_code == 200

    async def infer(self, data, content_type):
        async with httpx.AsyncClient(
            timeout=self.settings.inference_timeout, trust_env=False
        ) as client:
            try:
                response = await client.post(
                    str(self.settings.stt_whisper_url).rstrip("/") + "/inference",
                    files={"file": ("request.wav", data, content_type)},
                    data={"language": "en", "response_format": "json", "temperature": "0"},
                )
                response.raise_for_status()
                text = response.json()["text"].strip()
            except httpx.TimeoutException:
                raise ApiError("stt_timeout", "Speech recognition timed out", 504, True) from None
            except (httpx.HTTPError, ValueError, KeyError, AttributeError):
                raise ApiError(
                    "stt_unavailable", "Speech recognition returned an invalid response", 502, True
                ) from None
        if not text:
            raise ApiError(
                "no_speech",
                "No speech was recognized. Please retry or type your request",
                422,
                True,
            )
        return STTResult(text=text, source="external")


def create_backend():
    return WhisperHTTP()
