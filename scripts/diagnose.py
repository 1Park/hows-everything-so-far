"""Read-only host/runtime inventory. Missing board settings are reported as unknown."""

import importlib.util
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path


def report():
    fields = {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "camera_devices": [str(p) for p in Path("/dev").glob("video*")],
        "camera_source": os.environ.get("CAMERA_SOURCE", "not configured"),
        "bridge_module": importlib.util.find_spec("arduino") is not None,
        "ld_library_path": os.environ.get("LD_LIBRARY_PATH", "not configured"),
        "adsp_library_path": os.environ.get("ADSP_LIBRARY_PATH", "not configured"),
    }
    for name in (
        "QNN_EXECUTOR_RUNNER",
        "QNN_LLAMA_RUNNER",
        "VISION_MODEL_PATH",
        "QWEN_MODEL_PATH",
        "QWEN_TOKENIZER_PATH",
    ):
        value = os.environ.get(name)
        fields[name] = {"path": value, "exists": Path(value).is_file() if value else False}
        if value and Path(value).is_file() and shutil.which("ldd") and name.endswith("RUNNER"):
            result = subprocess.run(["ldd", value], capture_output=True, text=True, timeout=10)
            fields[name]["ldd"] = result.stdout + result.stderr
    if shutil.which("systemctl"):
        fields["arduino_router"] = subprocess.run(
            ["systemctl", "is-active", "arduino-router"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
    print(json.dumps(fields, indent=2))


if __name__ == "__main__":
    report()
