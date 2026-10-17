# English STT-noise robustness — temperature 0

## Method

24 clean/noisy pairs (48 sequential API requests) were evaluated against the existing `mlx-community/Qwen3-0.6B-4bit` endpoint. All prompts and utterances were English, temperature was fixed to 0, thinking was requested off, and the completion limit remained 192. The English system prompt was unchanged: no spelling-correction instructions or special aliases were added. Its hash was checked against the dataset manifest.

This is **synthetic text corruption**, not recorded speech or measured outputs of an STT model. Each noisy utterance contains one or two hand-selected phonetic substitutions or segmentation changes. Accent, room noise, real error frequencies, and audio recognition performance were not evaluated. `rice → rye` creates another legitimate food word and is intentionally ambiguous: clarification would be safer than assuming the original word.

Expected intent/item/portion remain those of the original speaker utterance. Thus the score measures recovery of original intent, not merely whether a corrupted text has a plausible interpretation. An abstention can fail exact recovery without being unsafe.

The 24 pairs use **18 distinct source scenarios**, with some repeated originals to compare different substitutions. Clean accuracy here is weighted by pairs, so it must not be compared directly with the previous full 48-scenario accuracy. Clean requests were rerun in this experiment rather than copied from historical results. One run per pair is not a repeatability estimate.

## Results

Scores remove only a surrounding Markdown code fence; no values are repaired. All 48 outputs had fences, so strict raw JSON exact match was 0/48.

| Metric | Result |
|---|---:|
| Original intent exact match, clean | 18/24 (75.0%) |
| Original intent exact match, noisy | 11/24 (45.8%) |
| Valid equal output between clean/noisy | 14/24 (58.3%) |
| Correct noisy output among clean-correct pairs | 11/18 (61.1%) |
| Clean-correct → noisy-incorrect | 7 pairs |
| Clean-incorrect → noisy-correct | 0 pairs |
| Schema-valid clean / noisy | 22/24 / 18/24 |
| False refill on expected non-refill, clean / noisy | 2/6 / 2/6 |
| Median HTTP latency, clean / noisy | 0.647 / 0.644 seconds |
| p95 HTTP latency, clean / noisy | 1.088 / 0.942 seconds |
| Request errors | 0/48 |

The 14 identical valid outputs include **3 pairs that are wrong on both sides**. Agreement alone is not correctness. Two other pairs have identical invalid objects; they are not counted as valid agreement. The unchanged false-refill count hides changed failure cases: S14 becomes invalid rather than a valid order, while S22 changes from cancellation to a valid order.

## Pair-by-pair results

`Y` means intent, item, and portion all match the original target after fence removal. `N` includes invalid schema and wrong meaning. Full sentences, context, expected objects, and outputs are available in the linked manifest and analysis.

| ID | Substitution | Clean correct | Noisy correct | Valid output unchanged | Noisy result / note |
|---|---|---|---|---|---|
| S01 | kimchi → kim chee | Y | Y | Y | kimchi, normal |
| S02 | kimchi → kin chi | Y | Y | Y | kimchi, normal |
| S03 | bean → been | Y | Y | Y | bean_sprouts, small |
| S04 | sprouts → spouts | Y | Y | Y | bean_sprouts, small |
| S05 | rice → rise, short request | Y | Y | Y | rice, normal |
| S06 | rice → rye | Y | N | N | item=rye, outside menu |
| S07 | kimchi → kim chee, small portion | Y | Y | Y | kimchi, small |
| S08 | bean sprouts → been spouts | Y | Y | Y | bean_sprouts, small |
| S09 | rice → rise, small refill sentence | Y | N | N | item=rise, outside menu |
| S10 | kimchi → kim chee; bean → been | Y | Y | Y | bean_sprouts, small |
| S11 | bean → been; rice → rise, two clauses | Y | N | N | bean_sprouts instead of rice |
| S12 | Not → Knot | Y | N | N | kimchi instead of bean_sprouts |
| S13 | No → Know, refusal | N | N | N | clarify with non-null item/portion: invalid |
| S14 | kimchi → kim chee, refusal | N | N | N | clarify with non-null item/portion: invalid |
| S15 | cancel → council, full sentence | Y | N | N | clarify with non-null item/portion: invalid |
| S16 | No → Know, portion correction | Y | N | N | normal instead of small |
| S17 | bean → been, item correction | N | N | Y | original wrong kimchi/normal retained |
| S18 | rice → rise, item correction | N | N | Y | original wrong kimchi/normal retained |
| S19 | portion → potion | Y | Y | Y | kimchi, normal |
| S20 | kimchi → kim chee; bean → been, two items | N | N | Y | selects kimchi rather than clarify |
| S21 | kimchi → kim chee, double portion | N | N | N | portion=double: invalid on both sides |
| S22 | Cancel → Council, short sentence | Y | N | N | cancellation becomes kimchi refill |
| S23 | refill → re fill | Y | Y | Y | kimchi, normal |
| S24 | please → pleas | Y | Y | Y | rice, normal |

## Concrete examples

- `Please refill the kim chee.` → correctly recovers kimchi.
- `Just a little been spouts, please.` → correctly recovers bean sprouts, small.
- `More rise, please.` → rice, but `A small refill of rise, please.` → unsupported item `rise`. Recovery is context-sensitive, not a reliable alias rule.
- `Knot kimchi. Bean sprouts please.` → kimchi; the intended negation is lost.
- `Council my refill, please.` with current kimchi/normal → refill kimchi/normal, although the original `Cancel my refill, please.` correctly canceled.

## Implications

Simple menu-name distortions can be recovered in this small set, but distorted negation/cancellation and context edits are not robust. Do not fuzzy-correct all words indiscriminately: `rye` can be a real request, and repairing a guessed negation can change consent. This experiment did not test an alias normalizer, STT vocabulary biasing, grammar-constrained decoding, or a revised prompt; none is claimed to solve these failures.

Keep menu/portion validation, show the interpreted request explicitly, and require confirmation independently of language-model output. Use physical cancel as an unambiguous path. Next evaluation should feed actual outputs of the chosen English STT engine through the same frozen prompt and retain both audio ground truth and transcription.

Latency is client HTTP wall time, not TTFT or model-only execution time. Results are from the supplied MLX endpoint, not VENTUNO Q/ExecuTorch. Server internal option handling and exact weight provenance were not independently inspected.

## Reproduce / artifacts

```powershell
python evaluation/refill_qwen_eval.py --prompt en --temperatures 0 --stt --output evaluation/qwen_stt_results.json
python evaluation/analyze_stt.py
```

The evaluator enforces English prompt and temperature 0 for `--stt`. The first command generates the manifest and sends 48 new requests; it overwrites the named outputs. The analyzer only reads saved responses and checks completion, counts, temperature, and prompt hash.

- [Dataset builder and phonetic substitutions](stt_cases.py.md)
- [Separate clean/noisy dataset manifest](stt_manifest.json.md)
- [Raw responses](qwen_stt_results.json.md)
- [Pair-level scoring](qwen_stt_analysis.json.md)
- [Analyzer](analyze_stt.py.md)
