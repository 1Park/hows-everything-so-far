# English-only refill evaluation

## Scope

The product/demo language is English, as requested for the US hackathon. Previous Korean results are not the primary product-language acceptance result.

All system instructions, six few-shot examples, customer utterances, menu names, context, and output fields sent in this run are English/ASCII. The 48 scenarios preserve the previous expected intents, items, portions, and injected request context. This is a translation of the previous scenario set, not a newly independent holdout. No prompt tuning was performed after observing this run.

- Endpoint: `http://won-macmini:8000/v1/chat/completions`.
- Model ID: `mlx-community/Qwen3-0.6B-4bit`.
- 48 scenarios at temperature 0 and 0.6: **96 requests**.
- `enable_thinking=false`, `max_completion_tokens=192`, `stream=false`.
- Parameters were requested; their internal server handling was not inspected.
- Expected policy: one allowed item, normal/small portions, unsupported or ambiguous requests require clarification; refusal/postponement cancels. These are application-specific labels, not universal linguistic ground truth.
- Models, server settings, and hardware were not modified. No actuators were invoked.

## Results

| Configuration | Exact match after fence removal | Valid schema after fence removal | False refill among 27 expected non-refill cases | Median / p95 HTTP latency |
|---|---:|---:|---:|---|
| English, temperature 0 | 21/48 (43.8%) | 39/48 | 10/27 | 0.644 / 1.027 s |
| English, temperature 0.6 | 22/48 (45.8%) | 37/48 | 8/27 | 0.652 / 0.739 s |
| Previous Korean v2, temperature 0 | 14/48 (29.2%) | 38/48 | 5/27 | 0.728 / 0.937 s |

All 96 English responses used Markdown fences, so strict raw JSON parsing and strict exact match were 0/96. The scores above remove only one surrounding code fence; they do not repair field values. There were zero request errors. A schema-valid incorrect order is more consequential than a response rejected by validation. Improved total exact match did not improve the false-refill metric.

At temperature 0, the original 32-case subset scored 14/32 and the translated 16-case extension scored 7/16. The four simple orders scored 4/4 and the four negation-with-alternative cases scored 3/4. Cancellation scored 1/5, context edits 2/5, and ambiguous/unsupported requests 0/7. Category sizes are too small to establish real deployment accuracy.

This is one run per temperature, not a repeatability study. The 1-case difference does not establish temperature 0.6 as superior. Changing both instruction and utterance language is an end-to-end language-configuration comparison, not an isolated test of model language capability.

## Representative failures at temperature 0

| Input/context | Expected | Actual after fence removal |
|---|---|---|
| Don't bring me kimchi. / current kimchi normal | cancel / null / null | refill / kimchi / normal |
| Bring it later, please. / current kimchi normal | cancel / null / null | refill / kimchi / normal |
| I'll change it to bean sprouts. / current kimchi small | refill / bean_sprouts / small | refill / kimchi / normal |
| Some of that, please. / no current request | clarify / null / null | refill / rice / small |

Some cancellation failures merely return noop/clarify rather than cancel; not every exact-match failure is an unauthorized order. False-refill counts specifically require a schema-valid refill when the expected intent is not refill. Wrong-item errors on legitimate orders are additional failures.

## Decision

English improves straightforward ordering in this test, but the current deployment still does not reliably support unrestricted corrections, refusals, or ambiguous references. Use the English results, not Korean results, as the product baseline. Keep a displayed request card and explicit physical confirmation. Reject invalid schema/menu/portion values rather than silently substituting defaults.

Before concluding that a larger model or multiple calls are necessary, inspect the deployed chat template/tokenizer and compare one controlled alternative, such as thinking enabled, on this same English suite. This run does not prove LangChain or multiple LLM calls would help.

Latency includes client/network/prefill/generation and may benefit from prefix caching. No TTFT, token throughput, memory, cold model loading, or ExecuTorch/QNN board performance was measured. Server internals and exact weight provenance remain unverified beyond the reported model ID.

## Reproduce and evidence

```powershell
python evaluation/refill_qwen_eval.py --prompt en --temperatures 0 0.6 --holdout --output evaluation/qwen_english_results.json
python evaluation/analyze_qwen.py --inputs qwen_english_results.json --output qwen_english_analysis.json
```

The first command issues 96 new requests and overwrites the named result file. The second only reads saved results. Preserve current evidence under a different name before rerunning if needed.

- [English prompt and translated utterances](english_cases.py.md)
- [Raw responses, expected outputs, timing, prompt hash](qwen_english_results.json.md)
- [Normalized scoring and complete failures](qwen_english_analysis.json.md)
- [Previous evaluation](QWEN_EVALUATION.md)
