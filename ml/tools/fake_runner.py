"""Fake qnn_executor_runner for Mac testing — mimics the same CLI flags/file conventions with executorch.runtime.

Lets us verify CliRunner's file I/O path without the board. The board uses the real runner.
  ml/tools/fake_runner.sh --model_path x.pte --input_list_path input_list.txt --output_folder_path outputs
Input raw files are assumed to be float32 (1,3,S,S) (S is inferred from the file size).
"""

import argparse
import math
from pathlib import Path

import numpy as np
import torch
from executorch.runtime import Runtime


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_path", required=True)
    ap.add_argument("--input_list_path", default="input_list.txt")
    ap.add_argument("--output_folder_path", default="outputs")
    ap.add_argument("--warm_up", type=int, default=0)
    ap.add_argument("--iteration", type=int, default=1)
    args, _ = ap.parse_known_args()

    method = Runtime.get().load_program(Path(args.model_path)).load_method("forward")
    out = Path(args.output_folder_path)
    out.mkdir(parents=True, exist_ok=True)
    lines = [ln.strip() for ln in Path(args.input_list_path).read_text().splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        x = np.fromfile(line.split(" ")[0], dtype=np.float32)
        s = int(math.isqrt(x.size // 3))
        y = method.execute([torch.from_numpy(x.reshape(1, 3, s, s))])
        for k, t in enumerate(y):
            t.numpy().tofile(out / f"output_{i}_{k}.raw")
    print(f"I fake_runner: {len(lines)} inference done")


if __name__ == "__main__":
    main()
