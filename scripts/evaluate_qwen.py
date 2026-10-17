"""Real HTTP evaluation. Creates a new result file exclusively; never uses a fixture fallback."""

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.language import SYSTEM_PROMPT, generation, parse_interpretation  # noqa: E402
from common.api import ApiError  # noqa: E402
from common.backends import MLXBackend  # noqa: E402
from common.config import ROOT, load_settings  # noqa: E402
from common.contracts import CurrentRequest  # noqa: E402


async def run(args):
    settings = load_settings()
    backend = MLXBackend(args.url, settings.qwen_model, settings.inference_timeout)
    cases_path = ROOT / "fixtures/drink_cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    rows = []
    ready = await backend.ready()
    print(f"Model listed by API: {ready}", flush=True)
    for case in cases:
        started = time.monotonic()
        row = {
            "id": case["id"],
            "current_request": case["current_request"],
            "utterance": case["utterance"],
            "expected": case["expected"],
        }
        try:
            result = await backend.generate(
                generation(
                    settings.qwen_model,
                    CurrentRequest(**case["current_request"]),
                    case["utterance"],
                )
            )
            row["raw"] = result
            row["actual"] = parse_interpretation(
                result["choices"][0]["message"]["content"]
            ).model_dump()
            row["correct"] = row["actual"] == case["expected"]
        except ApiError as error:
            row.update(error={"code": error.code, "message": error.message}, correct=False)
        row["seconds"] = round(time.monotonic() - started, 4)
        rows.append(row)
        print(f"{case['id']}: {'PASS' if row['correct'] else 'FAIL'} {row['seconds']}s", flush=True)
    await backend.close()
    source_values = {r.get("raw", {}).get("source", "mlx") for r in rows if "raw" in r}
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.url,
        "model": settings.qwen_model,
        "model_list_verified": ready,
        "temperature": 0,
        "requested_options": {
            "stream": False,
            "max_completion_tokens": 192,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        "system_prompt": SYSTEM_PROMPT,
        "dataset_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        "runtime": "Windows client -> our proxy -> Mac MLX"
        if args.proxy
        else "Windows client -> Mac MLX",
        "sources": sorted(source_values),
        "total": len(rows),
        "correct": sum(r["correct"] for r in rows),
        "median_seconds": statistics.median(r["seconds"] for r in rows),
        "note": "Text interpretation evaluation only. Not Vision/STT/board accuracy or board inference performance.",
        "rows": rows,
    }
    path = (
        ROOT
        / "docs/qwen_evaluation"
        / ("drinks-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    )
    with path.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"{report['correct']}/{len(rows)} · {path}", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--proxy", action="store_true")
    asyncio.run(run(parser.parse_args()))
