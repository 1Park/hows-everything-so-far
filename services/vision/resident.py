"""Persistent native QNN tensor worker. No per-request process or model reload."""

import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

import numpy as np


class ResidentRunner:
    def __init__(self, binary, pte_path, out_shape, timeout=20, startup_timeout=120):
        self.pte = str(Path(pte_path).resolve())
        self.out_shape = tuple(out_shape)
        self.timeout = timeout
        self.work = tempfile.TemporaryDirectory(prefix="vision-resident-")
        self.workdir = Path(self.work.name)
        self.lock = threading.Lock()
        self.events = queue.Queue()
        self.process = None
        self.name = f"resident:{Path(pte_path).name}"
        started = time.perf_counter()
        try:
            self.process = subprocess.Popen(
                [str(binary), "--model_path", self.pte, "--vision_resident=true"],
                cwd=self.workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1,
            )
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            self._expect("VISION_READY", startup_timeout)
        except BaseException:
            self.close()
            raise
        self.load_seconds = time.perf_counter() - started

    def _read(self):
        try:
            for line in self.process.stdout:
                marker = line.strip()
                if marker in ("VISION_READY", "VISION_DONE"):
                    self.events.put(marker)
        finally:
            self.events.put(None)

    def _expect(self, marker, timeout):
        try:
            event = self.events.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"Vision worker timed out waiting for {marker}") from None
        if event != marker:
            raise RuntimeError(f"Vision worker stopped or violated protocol (expected {marker})")

    @property
    def resident(self):
        return self.process is not None and self.process.poll() is None

    @property
    def status(self):
        return {"resident": self.resident, "pid": self.process.pid if self.resident else None,
                "runner": "resident", "model": Path(self.pte).name}

    def run(self, xs):
        with self.lock:
            if not self.resident:
                raise RuntimeError("Vision worker is not resident; restart the service")
            if not xs:
                return []
            try:
                # A fresh request directory prevents stale output from being reused.
                with tempfile.TemporaryDirectory(dir=self.workdir, prefix="request-") as request:
                    work = Path(request)
                    inputs = []
                    for i, x in enumerate(xs):
                        path = work / f"input_{i}.raw"
                        np.ascontiguousarray(x, dtype=np.float32).tofile(path)
                        inputs.append(str(path))
                    listing = work / "inputs.txt"
                    listing.write_text("\n".join(inputs) + "\n", encoding="utf-8")
                    output = work / "outputs"
                    output.mkdir()
                    self.process.stdin.write(f"{listing}\n{output}\n")
                    self.process.stdin.flush()
                    self._expect("VISION_DONE", self.timeout)
                    results = []
                    expected = int(np.prod(self.out_shape)) * np.dtype("float32").itemsize
                    for i in range(len(xs)):
                        path = output / f"output_{i}_0.raw"
                        if not path.is_file() or path.stat().st_size != expected:
                            raise RuntimeError("Vision worker returned missing or invalid tensor output")
                        results.append(np.fromfile(path, dtype=np.float32).reshape(self.out_shape))
                    return results
            except BaseException:
                self.abort()
                raise

    def abort(self):
        # Must not acquire run's lock: HTTP cancellation has to interrupt a running child.
        proc = self.process
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            proc.wait(timeout=5)

    def close(self):
        self.abort()
        reader = getattr(self, "reader", None)
        if reader is not None:
            reader.join(timeout=5)
        if self.process is not None:
            self.process.stdin.close()
            self.process.stdout.close()
        self.work.cleanup()
