"""Board-owned microphone capture. No STT model or audio preprocessing."""

import asyncio
import io
import shutil
import tempfile
import wave
from pathlib import Path

from common.api import ApiError


class BoardMicrophone:
    def __init__(self, settings):
        self.settings = settings

    def ready(self):
        s = self.settings
        return s.audio_input == "fixture" or (
            s.audio_input == "alsa" and bool(s.audio_device) and bool(shutil.which("arecord"))
        )

    async def capture(self, seconds=None):
        """seconds overrides the configured length; the demo always uses the default.

        Only the accuracy check varies it, so short phrases do not sit through the
        rest of a fixed take.
        """
        s = self.settings
        seconds = s.audio_seconds if seconds is None else seconds
        if not self.ready():
            raise ApiError("microphone_unavailable", "Configure the board microphone first", 503)
        if s.audio_input == "fixture":
            await asyncio.sleep(0.05)
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)
            return output.getvalue()
        with tempfile.TemporaryDirectory(prefix="refill-audio-") as directory:
            path = Path(directory) / "request.wav"
            try:
                process = await asyncio.create_subprocess_exec(
                    "arecord",
                    "-q",
                    "-D",
                    s.audio_device,
                    "-t",
                    "wav",
                    "-f",
                    s.audio_format,
                    "-r",
                    str(s.audio_rate),
                    "-c",
                    str(s.audio_channels),
                    "-d",
                    str(seconds),
                    str(path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except OSError:
                raise ApiError(
                    "microphone_unavailable", "Board recording could not start", 503
                ) from None
            try:
                await asyncio.wait_for(process.wait(), s.audio_seconds + 3)
            except (TimeoutError, asyncio.CancelledError) as error:
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                await process.wait()
                if isinstance(error, asyncio.CancelledError):
                    raise
                raise ApiError(
                    "recording_timeout", "Board recording timed out", 504, True
                ) from None
            if (
                process.returncode
                or not path.is_file()
                or not 44 < path.stat().st_size <= s.max_audio_bytes
            ):
                raise ApiError(
                    "recording_failed", "Board recording failed; check the microphone", 503, True
                )
            return path.read_bytes()
