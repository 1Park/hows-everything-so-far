"""Evaluate board Gemma with production prompts: 20 clean + 20 synthetic STT variants."""

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.language import generation, parse_interpretation  # noqa: E402
from common.api import ApiError  # noqa: E402
from common.config import ROOT  # noqa: E402
from common.contracts import CurrentRequest  # noqa: E402


def cases():
    clean = json.loads((ROOT / "fixtures/drink_cases.json").read_text(encoding="utf-8"))
    noise = json.loads((ROOT / "fixtures/drink_cases_distorted.json").read_text(encoding="utf-8"))
    assert len(clean) == len(noise) == 20
    assert len({r["id"] for r in noise}) == 20
    by_id = {r["id"]: r for r in clean}
    assert set(by_id) == {r["id"] for r in noise}
    return [dict(r, suite="clean") for r in clean] + [
        dict(by_id[r["id"]], suite="distorted", original=by_id[r["id"]]["utterance"],
             utterance=r["utterance"], distortion=r["distortion"])
        for r in noise
    ]


def write_report(report, stem):
    pending_json = stem.with_suffix(".json.tmp")
    pending_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    pending_json.replace(stem.with_suffix(".json"))
    lines = ["# Board Gemma drink interpretation evaluation", "",
             f"- Created (UTC): {report['created_at']}",
             f"- Endpoint: `{report['endpoint']}`",
             "- Scope: production text interpretation only; no image/STT execution.",
             "- Clean cases: development set used during prompt refinement, not held-out.",
             "- Distorted cases: 20 manually authored, paired synthetic STT-like variants; "
             "expected intent/item inherited from the clean source.",
             "- Timing: PC HTTP wall time over SSH tunnel, including server queue and inference; "
             "not isolated board compute, TTFT, or token throughput.",
             "- Each call is independent; no conversation history or automatic retries.",
             "- Raw HTTP bodies and full request payloads are preserved in the JSON companion.", ""]
    for model in report["models"]:
        lines += [f"## {model['model']}", ""]
        for suite in ("clean", "distorted"):
            rows = [r for r in model["rows"] if r["suite"] == suite]
            if rows:
                times = [r["seconds"] for r in rows]
                lines += [f"- {suite}: {sum(r['correct'] for r in rows)}/{len(rows)}; "
                          f"median {statistics.median(times):.3f}s; "
                          f"range {min(times):.3f}–{max(times):.3f}s"]
        if model["rows"]:
            payload = model["rows"][0]["request"]
            lines += ["", "### Shared system prompt", "", "```text",
                      payload["messages"][0]["content"], "```", "",
                      "### Requested generation options", "", "```json",
                      json.dumps({k: v for k, v in payload.items() if k != "messages"},
                                 ensure_ascii=False, indent=2), "```", ""]
        for row in model["rows"]:
            lines += [f"### {row['suite']} / {row['id']}", "",
                      f"- Result: {'PASS' if row['correct'] else 'FAIL'}",
                      f"- HTTP status: {row.get('http_status', 'no response')}",
                      f"- HTTP wall time: {row['seconds']:.4f}s"]
            if "original" in row:
                lines += [f"- Original: {row['original']}",
                          f"- Distortion: {row['distortion']}"]
            lines += ["", "User prompt input:", "", "```json",
                      row["request"]["messages"][1]["content"], "```", "",
                      "Expected:", "", "```json",
                      json.dumps(row["expected"], ensure_ascii=False), "```", "",
                      "Model output (message content, unmodified):", "", "```text",
                      row.get("content", "[No assistant content extracted]"), "```", ""]
            if "error" in row:
                lines += ["Error:", "", "```text", str(row["error"]), "```", ""]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")


async def run(args):
    dataset = cases()
    async with httpx.AsyncClient(timeout=args.timeout, trust_env=False) as client:
        ready = await client.get(args.url.rstrip("/") + "/ready")
        ready.raise_for_status()
        listing = await client.get(args.url.rstrip("/") + "/v1/models")
        listing.raise_for_status()
        available = [r["id"] for r in listing.json()["data"]]
        models = args.models or ["gemma4"]
        if not models or any(m not in available for m in models):
            raise ValueError(f"Requested Gemma models unavailable. Listed: {available}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder = ROOT / "docs/gemma_evaluation"
        folder.mkdir(exist_ok=True)
        stem = folder / f"drinks-{stamp}"
        report = {
            "created_at": datetime.now(timezone.utc).isoformat(), "endpoint": args.url,
            "ready": ready.json(), "model_listing": listing.json(),
            "scope": "Text only; synthetic STT-like noise, not real STT or vision accuracy.",
            "dataset_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                               for p in ("fixtures/drink_cases.json",
                                         "fixtures/drink_cases_distorted.json")},
            "models": [],
        }
        for model in models:
            result = {"model": model, "rows": []}
            report["models"].append(result)
            for case in dataset:
                payload = generation(model, CurrentRequest(**case["current_request"]),
                                     case["utterance"]).model_dump()
                row = dict(case, request=payload, correct=False)
                started = time.perf_counter()
                try:
                    response = await client.post(args.url.rstrip("/") + "/v1/chat/completions",
                                                 json=payload)
                    row["seconds"] = round(time.perf_counter() - started, 4)
                    row["http_status"] = response.status_code
                    row["raw_body"] = response.text
                    response.raise_for_status()
                    raw = response.json()
                    row["raw"] = raw
                    row["content"] = raw["choices"][0]["message"]["content"]
                    row["actual"] = parse_interpretation(row["content"]).model_dump()
                    row["correct"] = row["actual"] == row["expected"]
                except ApiError as error:
                    row["error"] = {"code": error.code, "message": error.message}
                except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
                    row["error"] = f"{type(error).__name__}: {error}"
                row.setdefault("seconds", round(time.perf_counter() - started, 4))
                result["rows"].append(row)
                write_report(report, stem)
                print(f"{model} {case['suite']}/{case['id']}: "
                      f"{'PASS' if row['correct'] else 'FAIL'} {row['seconds']}s", flush=True)
        print(stem.with_suffix(".md"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18000")
    parser.add_argument("--models", nargs="+", help="Explicit models to evaluate; default: gemma4 only")
    parser.add_argument("--timeout", type=float, default=180)
    arguments = parser.parse_args()
    asyncio.run(run(arguments))
