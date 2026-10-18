"""Compare per-invoke CLI loading with resident DINO/YOLO on the same image.

Direct pipeline wall time includes preprocessing, tensor file IPC, native work and
head postprocessing; it excludes HTTP/network/camera. Run in /tmp on the board.
No service is stopped, no bundle/config is modified, and output files must be new.
"""

import argparse
import hashlib
import json
import math
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.vision.pipeline import VisionPipeline  # noqa: E402


def equal_objects(a, b):
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.keys() != y.keys():
            return False
        for key in x:
            if isinstance(x[key], float):
                if not math.isclose(x[key], y[key], rel_tol=1e-4, abs_tol=1e-4):
                    return False
            elif x[key] != y[key]:
                return False
    return True


def summary(rows):
    return {key: {"median_ms": statistics.median([r[key] for r in rows]),
                  "mean_ms": statistics.mean([r[key] for r in rows]),
                  "p95_ms": float(np.percentile([r[key] for r in rows], 95))}
            for key in ("invoke_ms", "boxes_ms", "dino_ms")}


def run(args):
    image_path, bundle = Path(args.image).resolve(), Path(args.bundle).resolve()
    out = Path(args.output).resolve()
    if out.exists() or out.with_suffix(".md").exists():
        raise FileExistsError("Use new output paths to preserve previous measurements")
    cfg = json.loads((bundle / "bundle.json").read_text())
    if cfg["dino"]["runner"] != "cli" or (
        cfg["boxes"]["mode"] == "yolo" and cfg["boxes"].get("runner", "py") != "cli"
    ):
        raise ValueError("Benchmark requires the unchanged CLI bundle as the baseline")
    with Image.open(image_path) as opened:
        opened.load()
        image = opened.convert("RGB")
    report = {"created_at": datetime.now(timezone.utc).isoformat(),
              "platform": platform.platform(), "bundle": str(bundle),
              "image": str(image_path), "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
              "bundle_sha256": hashlib.sha256((bundle / "bundle.json").read_bytes()).hexdigest(),
              "cli": str(Path(args.cli).resolve()), "worker": str(Path(args.worker).resolve()),
              "scope": "Direct pipeline wall time; excludes HTTP/camera/network. Ordered CLI then resident; OS caches may be warm.",
              "warmups": args.warmups, "repetitions": args.repetitions, "modes": {}}
    reference = None
    out.parent.mkdir(parents=True, exist_ok=True)
    # Do not keep the new resident contexts loaded during the old baseline.
    for mode in ("cli", "resident"):
        started = time.perf_counter()
        pipeline = VisionPipeline(bundle, runner_bin=str(Path(args.cli).resolve()),
                                  resident=mode == "resident", worker_bin=str(Path(args.worker).resolve()))
        result = {"startup_ms": (time.perf_counter() - started) * 1000,
                  "startup_runners": pipeline.status, "rows": []}
        report["modes"][mode] = result
        try:
            for i in range(args.warmups + args.repetitions):
                started = time.perf_counter()
                objects = pipeline.analyze(image)
                elapsed = (time.perf_counter() - started) * 1000
                if reference is None:
                    reference = objects
                row = {"index": i, "warmup": i < args.warmups, "invoke_ms": elapsed,
                       **pipeline.timing, "objects": objects,
                       "matches_baseline": equal_objects(reference, objects)}
                result["rows"].append(row)
                print(f"{mode} {i}: {elapsed:.3f} ms; matching={row['matches_baseline']}", flush=True)
            result["first_invoke_ms"] = result["rows"][0]["invoke_ms"]
            result["summary"] = summary([r for r in result["rows"] if not r["warmup"]])
            result["final_runners"] = pipeline.status
        finally:
            pipeline.close()
            # Partial results survive if the other mode fails to start.
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    valid = all(r["matches_baseline"] for m in report["modes"].values() for r in m["rows"])
    report["all_outputs_match"] = valid
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Vision invoke latency: CLI vs resident", "", f"UTC: {report['created_at']}", "",
             report["scope"], "", f"Output parity: {valid}", "",
             f"Repetitions: {args.repetitions} per mode, excluding {args.warmups} recorded warmups.", "",
             "| Mode | Pipeline startup | First invoke | Invoke median | Invoke p95 | Boxes median | DINO median |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for mode, result in report["modes"].items():
        s = result["summary"]
        lines.append(f"| {mode} | {result['startup_ms']:.3f} ms | {result['first_invoke_ms']:.3f} ms | "
                     f"{s['invoke_ms']['median_ms']:.3f} ms | {s['invoke_ms']['p95_ms']:.3f} ms | "
                     f"{s['boxes_ms']['median_ms']:.3f} ms | {s['dino_ms']['median_ms']:.3f} ms |")
    lines += ["", "Resident startup includes model loading; CLI startup only constructs Python wrappers.",
              "CLI pays process/model loading inside every invoke. OS cold-cache behavior is not measured.",
              "Use the JSON companion for every sample, input/bundle hashes and native worker PIDs.", ""]
    out.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    if not valid:
        raise RuntimeError("Outputs differ: do not interpret latency as equivalent-task performance")
    print(out.with_suffix(".md"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repetitions", type=int, default=20)
    arguments = parser.parse_args()
    if arguments.warmups < 0 or arguments.repetitions < 2:
        parser.error("warmups must be nonnegative and repetitions must be at least 2")
    run(arguments)
