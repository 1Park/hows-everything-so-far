""".pte runners — Python bindings and CLI runners behind the same interface.

  runner.run([x1, x2, ...]) -> [y1, y2, ...]
    each x is a single-input sample (e.g. (1,3,224,224) float32), y is the first output (np.ndarray).
    The .pte is exported with batch fixed at 1, so N cups = N samples.

PyRunner : loads the model once via executorch.runtime and calls it repeatedly (fastest).
CliRunner: calls a CLI such as qnn_executor_runner. One input_list.txt line = one inference, so
           N cups go into a single runner run (model load cost paid once). Outputs are
           outputs/output_{i}_0.raw.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np


class PyRunner:
    def __init__(self, pte_path):
        import torch  # executorch.runtime inputs/outputs are torch.Tensor
        from executorch.runtime import Runtime

        self.torch = torch
        self.program = Runtime.get().load_program(Path(pte_path))
        self.method = self.program.load_method("forward")
        self.name = f"py:{Path(pte_path).name}"

    def run(self, xs):
        return [self.method.execute([self.torch.from_numpy(np.ascontiguousarray(x))])[0].numpy().copy() for x in xs]

    @property
    def resident(self):
        return self.method is not None

    def close(self):
        self.method = self.program = None


class CliRunner:
    """qnn_executor_runner-compatible CLI.

    out_shape: output tensor shape (raw files carry no shape). e.g. (1,384), (1,1000), (1,84,8400)
    out_dtype: output dtype. Even quantized .pte files usually take/return float32 (QDQ is inside
               the graph).
    extra_args: e.g. ["--warm_up", "0"]. Check the flags with the board runner's --help first.
    """

    resident = False

    def __init__(self, binary, pte_path, out_shape, out_dtype="float32", workdir=None, extra_args=(), keep=False):
        # the runner runs in workdir, so make a relative binary path absolute (bare PATH names stay)
        self.binary = str(Path(binary).resolve()) if Path(binary).exists() else str(binary)
        self.pte = str(Path(pte_path).resolve())
        self.out_shape = tuple(out_shape)
        self.out_dtype = np.dtype(out_dtype)
        self.workdir = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="et_cli_"))
        self.extra_args = list(extra_args)
        self.keep = keep
        self.name = f"cli:{Path(binary).name}:{Path(pte_path).name}"
        self.last_stdout = ""

    def run(self, xs):
        if not xs:
            return []
        d = self.workdir
        out_dir = d / "outputs"
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        lines = []
        for i, x in enumerate(xs):
            f = d / f"input_{i}_0.raw"
            np.ascontiguousarray(x, dtype=np.float32).tofile(f)
            lines.append(str(f))  # models with several inputs list them on one line, space-separated
        (d / "input_list.txt").write_text("\n".join(lines) + "\n")
        cmd = [self.binary, "--model_path", self.pte, "--input_list_path", str(d / "input_list.txt"),
               "--output_folder_path", str(out_dir), *self.extra_args]
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
        self.last_stdout = r.stdout + r.stderr
        if r.returncode != 0:
            raise RuntimeError(f"runner failed (exit {r.returncode}): {' '.join(cmd)}\n{self.last_stdout[-2000:]}")
        outs = []
        for i in range(len(xs)):
            f = out_dir / f"output_{i}_0.raw"
            if not f.exists():
                raise RuntimeError(f"{f} not found — the runner may have used its default input (check the input_list path)\n"
                                   f"{self.last_stdout[-2000:]}")
            outs.append(np.fromfile(f, dtype=self.out_dtype).reshape(self.out_shape))
        return outs

    def close(self):
        if not self.keep:
            shutil.rmtree(self.workdir, ignore_errors=True)


def make_runner(kind, pte, binary=None, out_shape=None, **kw):
    if kind == "py":
        return PyRunner(pte)
    if kind == "resident":
        from services.vision.resident import ResidentRunner

        if not binary or not out_shape:
            raise ValueError("Resident Vision requires VISION_WORKER_BIN and output shape")
        return ResidentRunner(binary, pte, out_shape, **kw)
    if kind == "cli":
        if not binary or not out_shape:
            raise SystemExit("--runner cli requires the runner binary path and the output shape")
        return CliRunner(binary, pte, out_shape, **kw)
    raise SystemExit(f"unknown runner {kind}")


def timed(runner, xs):
    t = time.perf_counter()
    ys = runner.run(xs)
    return ys, (time.perf_counter() - t) * 1000
