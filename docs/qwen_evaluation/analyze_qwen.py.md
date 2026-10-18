# analyze_qwen.py

Original path: `evaluation/analyze_qwen.py` · Original SHA-256: `a3d75e6e7e1cbf522df3bec027a1ea1d7302efee72edb0323227e4fd1a350024`

The original content is preserved in the code block below. See the [evaluation index](README.md) for how to restore it as an executable file. Line endings may have been normalized when it was stored as Markdown.

````python
import collections
import argparse
import json
import pathlib
import re

from refill_qwen_eval import validate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", default=["qwen_refill_results.json", "qwen_refill_v2_results.json"])
    parser.add_argument("--output", default="qwen_analysis.json")
    args = parser.parse_args()
    summaries = []
    for filename in args.inputs:
        path = pathlib.Path(__file__).parent / filename
        data = json.loads(path.read_text(encoding="utf-8"))
        for temperature in sorted({row["temperature"] for row in data["rows"]}):
            rows = [row for row in data["rows"] if row["temperature"] == temperature]
            groups = collections.defaultdict(lambda: {"correct": 0, "total": 0})
            failures = []
            normalized_valid = 0
            false_refill = 0
            for row in rows:
                raw = row.get("raw", "").strip()
                fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
                candidate = fence.group(1) if fence else raw
                try:
                    parsed = json.loads(candidate)
                except ValueError:
                    parsed = None
                valid = validate(parsed)
                correct = valid and parsed == row["expected"]
                normalized_valid += valid
                false_refill += valid and parsed["intent"] == "refill" and row["expected"]["intent"] != "refill"
                groups[row["group"]]["correct"] += correct
                groups[row["group"]]["total"] += 1
                if not correct:
                    failures.append({"case_id": row["case_id"], "utterance": row["utterance"], "expected": row["expected"], "actual": parsed})
            summary = {"file": filename, "temperature": temperature, "total": len(rows), "strict_exact": sum(row["exact_match"] for row in rows), "normalized_exact": sum(group["correct"] for group in groups.values()), "normalized_schema_valid": normalized_valid, "false_refill_after_normalization": false_refill, "groups": dict(groups), "failures": failures}
            summaries.append(summary)
    destination = pathlib.Path(__file__).parent / args.output
    destination.write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summaries, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
````
