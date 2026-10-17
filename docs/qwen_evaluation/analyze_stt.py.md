# analyze_stt.py

원본 경로: `evaluation/analyze_stt.py` · 원본 SHA-256: `93e10272af8a5242af69a66a4e3d94a53abe45a9cdc9cd436ecb9510ac8cd0f0`

원본 내용을 아래 코드 블록에 보존했다. 실행 가능한 파일로 복원하는 방법은 [평가 인덱스](README.md)를 참조한다. 줄바꿈은 Markdown 저장 과정에서 정규화될 수 있다.

````python
import json
import pathlib
import re
import statistics

from refill_qwen_eval import validate, percentile


def parse(row):
    text = row.get("raw", "").strip()
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    try:
        return json.loads(fence.group(1) if fence else text)
    except ValueError:
        return None


def main():
    directory = pathlib.Path(__file__).parent
    manifest = json.loads((directory / "stt_manifest.json").read_text(encoding="utf-8"))
    results = json.loads((directory / "qwen_stt_results.json").read_text(encoding="utf-8"))
    assert results.get("finished_at")
    assert manifest["prompt_sha256"] == results["prompt_sha256"]
    assert len(results["rows"]) == 2 * len(manifest["pairs"])
    assert all(row["temperature"] == 0 for row in results["rows"])
    indexed = {row["case_id"]: row for row in results["rows"]}
    pairs = []
    for pair in manifest["pairs"]:
        record = dict(pair)
        for variant in ["clean", "noisy"]:
            row = indexed[pair["pair_id"] + "_" + variant]
            parsed = parse(row)
            valid = validate(parsed)
            record[variant + "_output"] = parsed
            record[variant + "_valid"] = valid
            record[variant + "_correct"] = valid and parsed == pair["expected"]
            record[variant + "_false_refill"] = valid and parsed["intent"] == "refill" and pair["expected"]["intent"] != "refill"
            record[variant + "_latency_s"] = row["elapsed_s"]
        record["same_valid_output"] = record["clean_valid"] and record["noisy_valid"] and record["clean_output"] == record["noisy_output"]
        pairs.append(record)
    totals = {field: sum(pair[field] for pair in pairs) for field in ["clean_correct", "noisy_correct", "clean_valid", "noisy_valid", "clean_false_refill", "noisy_false_refill", "same_valid_output"]}
    totals.update(pairs=len(pairs), unique_source_cases=len({pair["source_id"] for pair in pairs}), both_correct=sum(pair["clean_correct"] and pair["noisy_correct"] for pair in pairs), degraded=sum(pair["clean_correct"] and not pair["noisy_correct"] for pair in pairs), improved=sum(not pair["clean_correct"] and pair["noisy_correct"] for pair in pairs), non_refill_pairs=sum(pair["expected"]["intent"] != "refill" for pair in pairs), request_errors=sum("error" in row for row in results["rows"]), strict_exact=sum(row["exact_match"] for row in results["rows"]))
    for variant in ["clean", "noisy"]:
        times = [pair[variant + "_latency_s"] for pair in pairs]
        totals[variant + "_median_s"] = statistics.median(times)
        totals[variant + "_p95_s"] = percentile(times, 0.95)
    (directory / "qwen_stt_analysis.json").write_text(json.dumps({"totals": totals, "pairs": pairs}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(totals, indent=2))
    for pair in pairs:
        print(json.dumps({key: pair[key] for key in ["pair_id", "clean", "noisy", "expected", "clean_output", "noisy_output", "clean_correct", "noisy_correct", "same_valid_output"]}))


if __name__ == "__main__":
    main()
````
