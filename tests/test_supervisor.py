import os
import socket
import subprocess
import sys
import time

import httpx

from common.config import ROOT


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_start_demo_stop_restart_and_duplicate():
    selected = port()
    env = {**os.environ, "CONTROLLER_PORT": str(selected)}
    command = [sys.executable, "scripts/dev.py", "--mode", "fixture"]
    lock = ROOT / f"tmp/dev-{selected}.lock"
    for _ in range(2):
        p = subprocess.Popen(
            command, cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        try:
            end = time.monotonic() + 25
            while time.monotonic() < end:
                assert p.poll() is None
                try:
                    with httpx.Client(
                        base_url=f"http://127.0.0.1:{selected}", trust_env=False, timeout=1
                    ) as c:
                        if c.get("/health").status_code == 200:
                            break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Supervisor failed to start")
            duplicate = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=10)
            assert duplicate.returncode == 1 and b"in use" in duplicate.stderr
            with httpx.Client(
                base_url=f"http://127.0.0.1:{selected}", trust_env=False, timeout=3
            ) as c:
                c.post("/api/observe").raise_for_status()
                end = time.monotonic() + 5
                while time.monotonic() < end:
                    s = c.get("/api/state").json()
                    if s["phase"] == "offered":
                        break
                    time.sleep(0.02)
                c.post(
                    "/api/utterance",
                    json={
                        "scene_id": s["scene"]["scene_id"],
                        "object_id": s["target"]["object_id"],
                        "utterance": "yes please",
                    },
                ).raise_for_status()
                while time.monotonic() < end:
                    s = c.get("/api/state").json()
                    if s["phase"] == "card":
                        break
                    time.sleep(0.02)
                c.post(
                    "/api/confirm",
                    json={k: v for k, v in s["card"].items() if k not in ("item", "portion")},
                ).raise_for_status()
                while time.monotonic() < end:
                    s = c.get("/api/state").json()
                    if s["phase"] == "done":
                        break
                    time.sleep(0.02)
                assert s["phase"] == "done"
        finally:
            if p.poll() is None:
                subprocess.run(
                    [*command, "--stop"],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                p.wait(timeout=15)
            assert not lock.exists()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", selected))


def test_startup_failure_rolls_back_children():
    ports = [port() for _ in range(4)]
    env = {
        **os.environ,
        "CONTROLLER_PORT": str(ports[0]),
        "QWEN_PORT": str(ports[1]),
        "VISION_PORT": str(ports[2]),
        "STT_PORT": str(ports[3]),
        "QWEN_MODEL_BACKEND": "fixture",
        "STT_MODEL_BACKEND": "external",
        "STT_ADAPTER": "missing_adapter_package:create_backend",
    }
    result = subprocess.run(
        [sys.executable, "scripts/dev.py", "--mode", "integration"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=40,
    )
    assert result.returncode == 1 and b"did not start" in result.stderr
    assert not (ROOT / f"tmp/dev-{ports[0]}.lock").exists()
    for selected in ports:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", selected))
