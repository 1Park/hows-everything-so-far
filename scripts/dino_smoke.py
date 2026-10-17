"""Run one DINOv2 prepared-tensor sample, without image preprocessing."""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import load_settings
from common.executorch import DinoRunner


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env.board")
    parser.add_argument("--output", required=True)
    parser.add_argument("tensors", nargs="+", help="One sample's prepared tensor files")
    args = parser.parse_args()
    settings = load_settings(args.env_file)
    runner = DinoRunner(settings.qnn_runner, settings.vision_model_path, settings.inference_timeout)
    outputs = await runner.infer([Path(name).read_bytes() for name in args.tensors])
    folder = Path(args.output).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    for name, data in outputs.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    print(f"Native runner completed; raw outputs: {folder}")
    print("Not accuracy or NPU delegation verification. Compare bundle reference tensors.")


if __name__ == "__main__":
    asyncio.run(main())
