"""Explicit process supervisor: no inference about ownership from URLs."""

import argparse
import os
import signal
import pathlib
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


def managed_ports(settings, mode):
    """Ports this supervisor would bind, so a restart can confirm they are free."""
    ports = [(settings.controller_host, settings.controller_port)]
    if mode in ("proxy", "integration", "board"):
        ports.append(("127.0.0.1", settings.qwen_port))
    if mode in ("integration", "board"):
        ports.append(("127.0.0.1", settings.vision_port))
        ports.append(("127.0.0.1", settings.stt_port))
    return ports


def port_free(host, port):
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
            return True
        except OSError:
            return False


def wait_for_ports(ports, timeout):
    """A lock file disappearing does not mean the listeners are gone."""
    deadline = time.monotonic() + timeout
    while True:
        busy = [f"{host}:{port}" for host, port in ports if not port_free(host, port)]
        if not busy or time.monotonic() >= deadline:
            return busy
        time.sleep(0.2)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def is_our_supervisor(pid):
    # Only ever signal a process this repo started: the board is shared, and
    # whisper-server and teammates' processes must survive a restart.
    try:
        cmdline = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
    except (OSError, ValueError):
        return False
    return "scripts/dev.py" in cmdline


def escalate(owner):
    """Graceful shutdown already failed; step up rather than leave the port held."""
    try:
        pid = int(owner)
    except ValueError:
        return
    if not alive(pid) or not is_our_supervisor(pid):
        return
    for signal_number in (signal.SIGTERM, signal.SIGKILL):
        os.kill(pid, signal_number)
        for _ in range(25):
            if not alive(pid):
                return
            time.sleep(0.2)


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
        owner = lockfile.read_text()
        stopfile.write_text(owner)
        print("Shutdown requested. Waiting for managed processes to stop...", flush=True)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                if lockfile.read_text() != owner:
                    break
            except FileNotFoundError:
                break
            time.sleep(0.1)
        else:
            print(f"Supervisor PID {owner} ignored the stop file; signalling it.", flush=True)
            escalate(owner)
            lockfile.unlink(missing_ok=True)
            stopfile.unlink(missing_ok=True)
            readyfile.unlink(missing_ok=True)
        busy = wait_for_ports(managed_ports(settings, args.mode), 15)
        if busy:
            raise RuntimeError(
                f"Shutdown left {', '.join(busy)} in use. Inspect the listeners before restarting"
            )
        print("Managed shutdown complete. You can restart now.")
        return
    env = os.environ.copy()
    if args.env_file:
        env["REFILL_ENV_FILE"] = str(Path(args.env_file).resolve())
    env["PYTHONUNBUFFERED"] = "1"
    if args.mode in ("fixture", "offline"):
        env.update(
            QWEN_BACKEND="fixture" if args.mode == "offline" else "http",
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
    if args.with_stt and args.mode not in ("integration", "board"):
        if args.mode in ("fixture", "offline"):
            raise RuntimeError("Use --mode direct --with-stt for an actual STT backend")
        services.append(
            ("stt", settings.stt_host, settings.stt_port, "services.stt.server:create_app")
        )
        env["STT_BACKEND"] = "http"
        env["STT_BASE_URL"] = f"http://127.0.0.1:{settings.stt_port}"
    services.append(
        ("controller", settings.controller_host, settings.controller_port, "app.server:create_app")
    )
    ports = [service[2] for service in services]
    if len(set(ports)) != len(ports):
        raise RuntimeError("Managed services must use distinct ports")
    # A just-stopped listener can linger for a moment; wait briefly before refusing,
    # so restarting right after a stop does not need a manual retry.
    busy = wait_for_ports([(host, port) for _, host, port, _ in services], 5)
    if busy:
        raise RuntimeError(f"Cannot start: {', '.join(busy)} in use")
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
        "--mode",
        choices=["direct", "fixture", "offline", "proxy", "integration", "board"],
        default="direct",
        help="fixture mocks Vision/STT/hardware and uses real Qwen HTTP; offline mocks everything",
    )
    parser.add_argument("--env-file")
    parser.add_argument(
        "--with-stt",
        action="store_true",
        help="Also manage our STT API; keep Qwen remote in direct mode",
    )
    parser.add_argument(
        "--stop", action="store_true", help="Ask the matching managed supervisor to stop"
    )
    args = parser.parse_args()
    try:
        supervise(args)
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
