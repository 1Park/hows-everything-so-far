"""Native QC runners. No model preprocessing, labels, or automatic fallback."""

import asyncio
import os
import tempfile
from pathlib import Path

from common.api import ApiError
from common.config import ROOT


def asset(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def available(runner: str, *files: str) -> bool:
    return (
        bool(runner and all(files))
        and os.access(asset(runner), os.X_OK)
        and all(asset(name).is_file() and asset(name).stat().st_size > 0 for name in files)
    )


async def execute(command: list[str], cwd: Path, timeout: float):
    """No shell. Reap native inference on timeout and caller cancellation."""
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=cwd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise ApiError("runner_unavailable", "Native model runner could not start", 503) from None
    try:
        await asyncio.wait_for(process.wait(), timeout)
    except (TimeoutError, asyncio.CancelledError) as error:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()
        if isinstance(error, asyncio.CancelledError):
            raise
        raise ApiError("model_timeout", "Native model runner timed out", 504, True) from None
    if process.returncode:
        raise ApiError(
            "runner_failed", "Native model runner failed; verify bundle compatibility", 502
        )


class DinoRunner:
    """Vision owner's building block: exact prepared tensors -> raw output files.

    Not an image backend: detection/crops/normalization/output interpretation remain
    owned by the Vision adapter. Filenames and tensor bytes carry no inferred layout.
    """

    def __init__(self, runner: str, model: str, timeout: float = 20):
        self.runner, self.model, self.timeout = runner, model, timeout
        self.lock = asyncio.Lock()

    async def ready(self):
        return available(self.runner, self.model)

    async def infer(self, tensors: list[bytes]) -> dict[str, bytes]:
        if not tensors or any(not isinstance(t, bytes) or not t for t in tensors):
            raise ApiError("invalid_tensors", "Supply nonempty prepared tensor bytes", 422)
        if not await self.ready():
            raise ApiError("not_ready", "DINOv2 runner or model is missing", 503)
        async with self.lock:
            with tempfile.TemporaryDirectory(prefix="refill-dino-") as directory:
                work = Path(directory)
                names = []
                for index, data in enumerate(tensors):
                    name = f"input-{index}.raw"
                    (work / name).write_bytes(data)
                    names.append(name)
                (work / "input_list.txt").write_text(" ".join(names) + "\n", encoding="utf-8")
                (work / "outputs").mkdir()
                await execute(
                    [
                        str(asset(self.runner)),
                        "--model_path",
                        str(asset(self.model)),
                        "--input_list_path",
                        str(work / "input_list.txt"),
                        "--output_folder_path",
                        str(work / "outputs"),
                    ],
                    work,
                    self.timeout,
                )
                outputs = {
                    p.relative_to(work / "outputs").as_posix(): p.read_bytes()
                    for p in (work / "outputs").rglob("*.raw")
                    if p.is_file()
                }
                if not outputs or any(not data for data in outputs.values()):
                    raise ApiError(
                        "invalid_backend_output", "DINOv2 produced no tensor output", 502
                    )
                return outputs
