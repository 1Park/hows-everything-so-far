"""Mac 테스트용 가짜 qnn_executor_runner — 같은 CLI 플래그/파일 규칙을 executorch.runtime 으로 흉내낸다.

CliRunner 의 파일 입출력 경로를 보드 없이 검증하기 위한 것. 보드에서는 진짜 runner 를 쓴다.
  ml/tools/fake_runner.sh --model_path x.pte --input_list_path input_list.txt --output_folder_path outputs
입력 raw 는 float32 (1,3,S,S) 로 가정 (S 는 파일 크기로 추정).
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
