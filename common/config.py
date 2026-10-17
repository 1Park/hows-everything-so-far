"""Explicit dotenv selection, then process-environment overrides. No import side effects."""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)
    app_env: Literal["development", "test", "board"] = "development"
    controller_host: str = "127.0.0.1"
    controller_port: int = Field(8080, ge=1, le=65535)
    vision_backend: Literal["fixture", "http"] = "fixture"
    vision_base_url: HttpUrl = "http://127.0.0.1:8001"
    vision_host: str = "127.0.0.1"
    vision_port: int = Field(8001, ge=1, le=65535)
    vision_model_backend: Literal["fixture", "external"] = "fixture"
    vision_adapter: str = ""
    stt_backend: Literal["fixture", "http"] = "fixture"
    stt_base_url: HttpUrl = "http://127.0.0.1:8002"
    stt_host: str = "127.0.0.1"
    stt_port: int = Field(8002, ge=1, le=65535)
    stt_model_backend: Literal["fixture", "external"] = "fixture"
    stt_adapter: str = ""
    qwen_backend: Literal["fixture", "http"] = "http"
    qwen_base_url: HttpUrl = "http://won-macmini:8000"
    qwen_host: str = "127.0.0.1"
    qwen_port: int = Field(8000, ge=1, le=65535)
    qwen_model_backend: Literal["mlx", "fixture", "executorch"] = "mlx"
    qwen_upstream_url: HttpUrl = "http://won-macmini:8000"
    qwen_model: str = "mlx-community/Qwen3-0.6B-4bit"
    inference_timeout: float = Field(20, gt=0, le=180)
    queue_limit: int = Field(4, ge=1, le=32)
    max_image_bytes: int = Field(5_000_000, ge=1024, le=20_000_000)
    max_audio_bytes: int = Field(10_000_000, ge=1024, le=25_000_000)
    min_confidence: float = Field(0.7, ge=0, le=1)
    low_fill_threshold: float = Field(0.3, ge=0, le=1)
    response_timeout: float = Field(60, gt=0, le=600)
    mock_step_seconds: float = Field(0.8, gt=0, le=20)
    hardware_backend: Literal["mock", "bridge"] = "mock"
    bridge_timeout: float = Field(3, gt=0, le=30)
    camera_source: str = ""  # empty = explicit static fixture, no implicit /dev/video0

    @model_validator(mode="after")
    def adapters_required(self):
        for name in ("vision", "stt"):
            if getattr(self, f"{name}_model_backend") == "external" and not getattr(
                self, f"{name}_adapter"
            ):
                raise ValueError(f"{name.upper()}_ADAPTER is required for external mode")
        return self


def load_settings(env_file: str | Path | None = None, **overrides) -> Settings:
    selected = Path(env_file or os.environ.get("REFILL_ENV_FILE", ROOT / ".env"))
    values = {k.lower(): v for k, v in dotenv_values(selected).items() if v is not None}
    values.update({k.lower(): v for k, v in os.environ.items()})
    values.update(overrides)
    return Settings.model_validate(values)
