import asyncio

import httpx
from pydantic import ValidationError

from app.language import generation, parse_interpretation
from common.api import ApiError, request_id
from common.backends import FixtureTextBackend, MLXBackend
from common.contracts import STTResult, VisionResult
from services.sensory import FixtureSTT, FixtureVision


class ModelClients:
    def __init__(self, settings):
        self.settings = settings
        self.http = httpx.AsyncClient(timeout=settings.inference_timeout, trust_env=False)
        self.qwen = (
            FixtureTextBackend()
            if settings.qwen_backend == "fixture"
            else MLXBackend(
                str(settings.qwen_base_url), settings.qwen_model, settings.inference_timeout
            )
        )

    async def close(self):
        await self.http.aclose()
        if hasattr(self.qwen, "close"):
            await self.qwen.close()

    async def language(self, current, utterance):
        result = await self.qwen.generate(generation(self.settings.qwen_model, current, utterance))
        return parse_interpretation(result["choices"][0]["message"]["content"]), result.get(
            "source", "mlx"
        )

    async def media(self, kind, data, content_type, scene_id="", scenario="normal"):
        settings = self.settings
        if getattr(settings, f"{kind}_backend") == "fixture":
            if kind == "vision":
                return await FixtureVision().infer(data, content_type, scene_id, scenario)
            return await FixtureSTT().infer(data, content_type)
        endpoint = "/v1/analyze" if kind == "vision" else "/v1/transcribe"
        form = {"scene_id": scene_id, "scenario": scenario} if kind == "vision" else {}
        try:
            response = await self.http.post(
                str(getattr(settings, f"{kind}_base_url")).rstrip("/") + endpoint,
                files={"file": ("media", data, content_type)},
                data=form,
                headers={"x-request-id": request_id.get()},
            )
            response.raise_for_status()
            result = (VisionResult if kind == "vision" else STTResult).model_validate(
                response.json()
            )
            if kind == "vision" and result.scene_id != scene_id:
                raise ValueError()
            return result
        except httpx.TimeoutException:
            raise ApiError(
                "service_timeout", f"The {kind.upper()} service timed out", 504, True
            ) from None
        except (httpx.HTTPError, ValueError, ValidationError):
            raise ApiError(
                "service_unavailable",
                f"The {kind.upper()} service is unavailable or returned invalid data",
                502,
                True,
            ) from None

    async def vision(self, data, content_type, scene_id, scenario):
        return await self.media("vision", data, content_type, scene_id, scenario)

    async def stt(self, data, content_type):
        return await self.media("stt", data, content_type)

    async def ready(self):
        async def sensory(kind):
            if getattr(self.settings, f"{kind}_backend") == "fixture":
                return {"ready": True, "source": "fixture"}
            try:
                r = await self.http.get(
                    str(getattr(self.settings, f"{kind}_base_url")).rstrip("/") + "/ready",
                    timeout=4,
                )
                return {"ready": r.status_code == 200, "source": r.json().get("source", "unknown")}
            except (httpx.HTTPError, ValueError):
                return {"ready": False, "source": "unavailable"}

        vision, stt, qwen = await asyncio.gather(
            sensory("vision"), sensory("stt"), self.qwen.ready()
        )
        return {
            "vision": vision,
            "stt": stt,
            "qwen": {
                "ready": qwen,
                "source": "fixture" if self.settings.qwen_backend == "fixture" else "http",
                "endpoint": str(self.settings.qwen_base_url),
                "model": self.settings.qwen_model,
            },
        }
