"""Explicit process supervisor: no inference about ownership from URLs."""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.config import load_settings  # noqa: E402


def supervise(args):
    settings = load_settings(args.env_file)
    lockfile = (
        ROOT
        / "tmp"
        / ("board.lock" if args.mode == "board" else f"dev-{settings.controller_port}.lock")
    )
    stopfile = lockfile.with_suffix(".stop")
    readyfile = lockfile.with_suffix(".ready")
    if args.stop:
        if not lockfile.exists():
            print("No managed supervisor lock found")
            return
        stopfile.write_text(lockfile.read_text())
        print("Shutdown requested. Wait for the supervisor lock to disappear.")
        return
    env = os.environ.copy()
    if args.env_file:
        env["REFILL_ENV_FILE"] = str(Path(args.env_file).resolve())
    env["PYTHONUNBUFFERED"] = "1"
    if args.mode == "fixture":
        env.update(
            QWEN_BACKEND="fixture",
            VISION_BACKEND="fixture",
            STT_BACKEND="fixture",
            HARDWARE_BACKEND="mock",
        )
    services = []
    if args.mode in ("proxy", "integration", "board"):
        services.append(
            ("qwen", settings.qwen_host, settings.qwen_port, "services.qwen.server:create_app")
        )
        env["QWEN_BACKEND"] = "http"
        env["QWEN_BASE_URL"] = f"http://127.0.0.1:{settings.qwen_port}"
    if args.mode in ("integration", "board"):
        for name in ("vision", "stt"):
            services.append(
                (
                    name,
                    getattr(settings, f"{name}_host"),
                    getattr(settings, f"{name}_port"),
                    f"services.{name}.server:create_app",
                )
            )
            env[f"{name.upper()}_BACKEND"] = "http"
            env[f"{name.upper()}_BASE_URL"] = (
                f"http://127.0.0.1:{getattr(settings, f'{name}_port')}"
            )
    services.append(
        ("controller", settings.controller_host, settings.controller_port, "app.server:create_app")
    )
    ports = [service[2] for service in services]
    if len(set(ports)) != len(ports):
        raise RuntimeError("Managed services must use distinct ports")
    for name, host, port, factory in services:
        with socket.socket() as probe:
            try:
                probe.bind((host, port))
            except OSError:
                raise RuntimeError(f"Cannot start {name}: {host}:{port} is in use") from None
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "tmp").mkdir(exist_ok=True)
    lockfile = (
        ROOT
        / "tmp"
        / ("board.lock" if args.mode == "board" else f"dev-{settings.controller_port}.lock")
    )
    try:
        lock = os.open(lockfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        raise RuntimeError(
            f"Supervisor lock exists: {lockfile}. Check the recorded PID before removing a stale lock"
        ) from None
    os.write(lock, str(os.getpid()).encode())
    os.close(lock)
    processes, logs = [], []
    child_stop = ROOT / "tmp" / f"children-{uuid4()}.stop"
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        for name, host, port, factory in services:
            logfile = open(ROOT / "logs" / f"{name}.log", "ab", buffering=0)
            logs.append(logfile)
            process = subprocess.Popen(
                [
                    sys.executable,
                    "scripts/serve.py",
                    "--factory",
                    factory,
                    "--host",
                    host,
                    "--port",
                    str(port),
                    "--stop-file",
                    str(child_stop),
                ],
                cwd=ROOT,
                env=env,
                stdout=logfile,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
            processes.append((name, process))
            end = time.monotonic() + 20
            while time.monotonic() < end:
                if stopping or process.poll() is not None:
                    raise RuntimeError(f"{name} did not start. See logs/{name}.log")
                try:
                    with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError(f"{name} startup timed out. See logs/{name}.log")
        print(
            f"Refill Assist: http://127.0.0.1:{settings.controller_port} · mode={args.mode}",
            flush=True,
        )
        print("Ctrl+C stops all managed processes. Logs: logs/ · Readiness: /ready", flush=True)
        readyfile.write_text(str(os.getpid()))
        while not stopping:
            if stopfile.exists() and stopfile.read_text() == str(os.getpid()):
                stopping = True
                continue
            for name, process in processes:
                if process.poll() is not None:
                    raise RuntimeError(f"{name} exited unexpectedly. See logs/{name}.log")
            time.sleep(0.15)
    finally:
        child_stop.touch()
        for name, process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        for logfile in logs:
            logfile.close()
        lockfile.unlink(missing_ok=True)
        stopfile.unlink(missing_ok=True)
        readyfile.unlink(missing_ok=True)
        child_stop.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["direct", "fixture", "proxy", "integration", "board"], default="direct"
    )
    parser.add_argument("--env-file")
    parser.add_argument(
        "--stop", action="store_true", help="Ask the matching managed supervisor to stop"
    )
    args = parser.parse_args()
    try:
        supervise(args)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
