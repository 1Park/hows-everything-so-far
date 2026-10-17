"""Transport validation only: no model preprocessing, normalization or resampling."""

import io
import warnings

from fastapi import UploadFile
from PIL import Image

from common.api import ApiError


async def read_upload(file: UploadFile, maximum: int) -> bytes:
    data = await file.read(maximum + 1)
    await file.close()
    if not data or len(data) > maximum:
        raise ApiError("invalid_size", "Uploaded media is empty or exceeds the size limit", 413)
    return data


def validate_image(data: bytes, content_type: str):
    if content_type not in ("image/jpeg", "image/png"):
        raise ApiError("invalid_format", "Use a JPEG or PNG image", 415)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                expected = "JPEG" if content_type == "image/jpeg" else "PNG"
                if image.format != expected or image.width * image.height > 16_000_000:
                    raise ValueError()
                image.verify()
    except Exception:
        raise ApiError(
            "invalid_image", "Image data is invalid or has too many pixels", 422
        ) from None


def validate_audio(data: bytes, content_type: str):
    mime = content_type.split(";")[0].strip()
    allowed = {
        "audio/wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
        "audio/x-wav": data.startswith(b"RIFF") and data[8:12] == b"WAVE",
        "audio/webm": data.startswith(b"\x1aE\xdf\xa3"),
        "audio/ogg": data.startswith(b"OggS"),
        "audio/mp4": len(data) > 12 and data[4:8] == b"ftyp",
    }
    if not allowed.get(mime):
        raise ApiError(
            "invalid_audio", "Use WAV, WebM, Ogg, or MP4 audio with a matching content type", 415
        )
