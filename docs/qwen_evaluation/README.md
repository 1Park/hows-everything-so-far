# Qwen evaluation records

This folder preserves prompts, raw responses, timings and analyses from past runs. They include the old food menu and the portion/clarify schema, so do not use them as the reference for the current product contract or accuracy. The current prompt is [`app/language.py`](../../app/language.py), and reruns use [`scripts/evaluate_qwen.py`](../../scripts/evaluate_qwen.py).

## Drink evaluation (2026-10-17, old schema)

- [17/20 result](drinks-20261017T061614204547Z.json): our proxy → Mac MLX, HTTP median 0.679 s.
- [First evaluation, 15/20](drinks-20261017T060722867674Z.json), [early transport contract failure](drinks-20261017T060535441028Z.json).
- [Board-resident worker raw](resident-worker-20261017.json), [interpretation and conditions](../RESIDENT_LLM.md).

This data was used to refine the development prompt and is not a held-out generalization result. Mac HTTP timings are kept separate from board NPU latency.

## Earlier food and STT-like distortion experiments

- [English evaluation](QWEN_ENGLISH_EVALUATION.md), [synthetic STT substitution evaluation](QWEN_STT_EVALUATION.md), [Korean/mixed evaluation](QWEN_EVALUATION.md).
- [English prompt and cases](english_cases.py.md), [evaluation request code](refill_qwen_eval.py.md), [STT case generation](stt_cases.py.md).
- [English raw](qwen_english_results.json.md), [analysis](qwen_english_analysis.json.md), [STT manifest](stt_manifest.json.md), [STT raw](qwen_stt_results.json.md), [pairwise analysis](qwen_stt_analysis.json.md).
- [Full archive list and pre-move hashes](MIGRATION.md).

`.py.md`/`.json.md` files are archives that keep the original text in a single 4-backtick block; they are not executable files. If needed, restore the block body to a separate experiment path. The recorded hashes are of the bytes before the move and may differ from hashes taken after Markdown line-ending normalization. Original results are not overwritten; new evaluations are saved as timestamped files.
