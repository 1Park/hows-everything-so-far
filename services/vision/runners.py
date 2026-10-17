""".pte 실행기 — Python 바인딩 / CLI runner 를 같은 인터페이스로 갈아끼운다.

  runner.run([x1, x2, ...]) -> [y1, y2, ...]
    각 x 는 입력 1개짜리 샘플 (예: (1,3,224,224) float32), y 는 첫 번째 출력 (np.ndarray).
    .pte 는 batch 1 고정 export 이므로 잔 N개 = 샘플 N개.

PyRunner : executorch.runtime 으로 모델을 한 번 로드해 두고 반복 호출 (가장 빠름).
CliRunner: qnn_executor_runner 같은 CLI 를 호출. input_list.txt 한 줄 = 추론 1회라서
           잔 N개를 runner 1번 실행으로 묶는다 (모델 로딩 비용 1회). 출력은 outputs/output_{i}_0.raw.
"""

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np


class PyRunner:
    def __init__(self, pte_path):
        import torch  # executorch.runtime 입출력이 torch.Tensor
        from executorch.runtime import Runtime

        self.torch = torch
        self.method = Runtime.get().load_program(Path(pte_path)).load_method("forward")
        self.name = f"py:{Path(pte_path).name}"

    def run(self, xs):
        return [self.method.execute([self.torch.from_numpy(np.ascontiguousarray(x))])[0].numpy() for x in xs]


class CliRunner:
    """qnn_executor_runner 호환 CLI.

    out_shape: 출력 텐서 shape (raw 파일엔 shape 정보가 없음). 예: (1,384), (1,1000), (1,84,8400)
    out_dtype: 출력 dtype. 양자화 .pte 라도 보통 입출력은 float32 (QDQ가 그래프 안쪽).
    extra_args: 예) ["--warm_up", "0"]. 보드 runner 의 --help 로 플래그를 먼저 확인할 것.
    """

    def __init__(self, binary, pte_path, out_shape, out_dtype="float32", workdir=None, extra_args=(), keep=False):
        # runner는 workdir에서 실행되므로 상대 경로 바이너리는 절대 경로로 (PATH의 이름이면 그대로)
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
            lines.append(str(f))  # 입력이 여러 개인 모델이면 한 줄에 공백으로 이어 붙인다
        (d / "input_list.txt").write_text("\n".join(lines) + "\n")
        cmd = [self.binary, "--model_path", self.pte, "--input_list_path", str(d / "input_list.txt"),
               "--output_folder_path", str(out_dir), *self.extra_args]
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True)
        self.last_stdout = r.stdout + r.stderr
        if r.returncode != 0:
            raise RuntimeError(f"runner 실패 (exit {r.returncode}): {' '.join(cmd)}\n{self.last_stdout[-2000:]}")
        outs = []
        for i in range(len(xs)):
            f = out_dir / f"output_{i}_0.raw"
            if not f.exists():
                raise RuntimeError(f"{f} 없음 — runner가 기본 입력으로 돌았을 수 있음 (input_list 경로 확인)\n"
                                   f"{self.last_stdout[-2000:]}")
            outs.append(np.fromfile(f, dtype=self.out_dtype).reshape(self.out_shape))
        return outs

    def close(self):
        if not self.keep:
            shutil.rmtree(self.workdir, ignore_errors=True)


def make_runner(kind, pte, binary=None, out_shape=None, **kw):
    if kind == "py":
        return PyRunner(pte)
    if kind == "cli":
        if not binary or not out_shape:
            raise SystemExit("--runner cli 는 runner 바이너리 경로와 출력 shape 가 필요")
        return CliRunner(binary, pte, out_shape, **kw)
    raise SystemExit(f"unknown runner {kind}")


def timed(runner, xs):
    t = time.perf_counter()
    ys = runner.run(xs)
    return ys, (time.perf_counter() - t) * 1000
