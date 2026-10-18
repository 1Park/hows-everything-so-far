# Qwen3-0.6B-4bit refill request interpretation evaluation

Run: 2026-10-15 PDT / 2026-10-16 UTC. Requests were sent directly to the user-specified `http://won-macmini:8000`. Nothing was run on the board and no robot actions were performed.

## Conclusion

**The current server, prompt and non-thinking settings are fast, but they did not show enough accuracy to auto-confirm Korean refill requests.** The earlier proposal of "one Qwen call handles corrections, negation and context" was not demonstrated on this model deployment. Use the output only as a draft for confirmation, and keep button selection / final confirmation.

This is not a conclusion about the performance of all Qwen models. The server template, actual weights, quantization and serving settings were not inspected independently; only the deployment's identity was checked, via `/v1/models` and the model name in responses. These are observations of the current deployment.

## Method

- Model ID: `mlx-community/Qwen3-0.6B-4bit`.
- 112 structured requests: v1 32 sentences × temperature 0/0.6, v2 48 sentences × temperature 0.
- 6 additional diagnostics: UTF-8 vs. Unicode-escape transport, and Korean vs. English single-task comparisons. 1 separate connection check.
- All structured calls used `stream=false`, `max_completion_tokens=192`, `chat_template_kwargs.enable_thinking=false`. Whether the server actually applied these options internally was not verified separately.
- v1: English rule prompt. The model sometimes copied verbatim the schema example that listed the enum candidates separated by pipes. The result therefore also reflects weaknesses in the prompt design.
- v2: revised to Korean rules with 6 concrete JSON examples. Because it was revised after seeing the v1 failures, the original 32 sentences are a development set. 16 new sentences were added as a separate holdout, and the prompt was not retuned after seeing those responses. All are small, human-written synthetic tests, not an independent field evaluation.
- Each request was a separate conversation, with `current_request` injected explicitly. This is not a real multi-turn app integration test.
- Scoring is an exact match on intent/item/portion. For cancel, clarify and noop, item/portion must be null. Expected answers follow the single-item, normal/small policy.
- The strict score (parser applied to the raw text as-is) is reported separately from the normalized score, which only removes a single Markdown code fence wrapping the entire response. Wrong field values, the string "null", menu items and intents were not corrected.

## Results

| Prompt / temperature | Count | Strict exact match | Exact match after fence removal | Schema-valid after fence removal | Response time median / p95 |
|---|---:|---:|---:|---:|---|
| v1 / 0 | 32 | 0/32 | 2/32 (6.3%) | 5/32 | 0.626 / 1.072 s |
| v1 / 0.6 | 32 | 0/32 | 3/32 (9.4%) | 6/32 | 0.602 / 0.850 s |
| v2 / 0 | 48 | 0/48 | 14/48 (29.2%) | 38/48 | 0.728 / 0.937 s |

v2 scored 8/32 (25.0%) on the development set and 6/16 (37.5%) on the new holdout. The overall v2 score in the table must not be presented as an independent holdout score. With small samples and one run per setting, no ranking between temperatures or claim about repeat stability is established.

The strict score of 0 is because every structured response was wrapped in a code block, so direct JSON parsing failed. **It does not mean the model understood nothing.** However, removing the fence alone did not make performance sufficient.

Normalized exact match by category for the original 32 v2 sentences:

| Category | Correct |
|---|---:|
| Simple order | 2/4 |
| Negation then alternative | 0/4 |
| Cancel / refusal | 0/5 |
| Context of existing request / correction | 0/5 |
| Ambiguous / unsupported request | 3/7 |
| Greeting / information question | 2/3 |
| English order | 1/2 |
| Instruction-override attack | 0/2 |

The 0/5 for cancel includes cases where the model held back with clarify/noop instead of cancel. It does not mean all of them were executed as orders. On the other hand, even after fence removal and schema validation, **5 of the 27 cases that must not produce an order came out as valid refills**. These include a menu information question, unsupported multiple/bulk requests, and instruction-override attacks. Errors where the correct answer was refill but a different food was chosen are separate from these 5.

`false_refill=0` in the original results is because every response failed the strict parser. If fences are stripped in production, read `false_refill_after_normalization` in `qwen_analysis.json`. Do not confuse parse rejection with semantic safety.

## Representative failures — v2 actual responses with only the fence removed

| Input / context | Expected | Actual |
|---|---|---|
| 콩나물은 됐어요. 밥 조금 주세요 ("No more bean sprouts. A little rice, please") | refill / rice / small | refill / bean_sprouts / normal |
| Current: kimchi, small → 콩나물로 바꿀게요 ("I'll switch to bean sprouts") | refill / bean_sprouts / small | refill / kimchi / small |
| Current: kimchi, normal → 아니, 조금만 ("No, just a little") | refill / kimchi / small | clarify / null / null |
| 리필 가능한 반찬이 뭔가요? ("Which side dishes can be refilled?") | noop / null / null | refill / kimchi / normal |
| 김치랑 콩나물 둘 다 주세요 ("Both kimchi and bean sprouts, please") | clarify / null / null | refill / kimchi / normal |

## Encoding and simple-task diagnostics

- When the same Korean sentence was sent once as direct UTF-8 and once as JSON Unicode escapes, both responses preserved the original Korean sentence (with a period added). There is no evidence that corruption of Korean text in this Python path was the main cause of the low scores.
- Even with a very short food-selection prompt, the model output **김치** (kimchi) for ‘김치 말고 콩나물 주세요’ ("bean sprouts, not kimchi, please"). For the equivalent English request it output `bean_sprouts`.
- In the Korean Yes/No classification diagnostic, the model repeated the customer sentence instead of the specified label. In the English diagnostic it output `NO.`. With one case each, this is not statistical evidence of an overall performance gap between the languages.
- The user's `Hello! ð` matches what a UTF-8 emoji looks like when decoded incorrectly, but this was not confirmed because the raw bytes and response headers the user received were not checked. The evaluation client sent requests as UTF-8 bytes and explicitly decoded responses as UTF-8.
- The first connection check used a PowerShell→Python stdin path, so it was excluded from the Korean accuracy evaluation. The formal evaluation and diagnostics were run from UTF-8 source files.

## Interpreting latency, and what was not measured

Times are HTTP request → full response received wall time, measured on the Windows client. They include network, tokenization, prompt processing and generation, and are not model-only latency. Because requests were sequential with a repeated prompt, the server's prefix cache may have had an effect. Server hardware/cache settings and concurrent load were not checked.

- Across the 112 structured requests: 0 HTTP errors, and finish_reason was always stop.
- TTFT, streaming tokens/s, actual peak RAM, cold load, long-running operation, thinking=true and constrained JSON decoding were not measured.
- Do not carry the Mac MLX 4-bit results over as performance of the VENTUNO Q ExecuTorch/QNN bundle. Quantization, tokenizer, template and backend may differ.

## Project decisions

1. With the current settings, do not connect free-form Korean speech directly to execution authority.
2. Removing the JSON fence only fixes the format problem. It does not fix context or negation errors.
3. It is worth first checking the server's chat template, tokenizer, actual model and whether options are applied. The server settings were not changed in this evaluation.
4. Run the next comparison on the same tests, changing one thing at a time: thinking on/off, or a different model size. Installing additional models or changing the server was not part of this work.
5. There is no evidence that multiple Qwen calls or adding LangChain would fix these errors. Keep simple input, explicit request cards and physical confirmation.

## Reproduction

Reading the saved results first does not send any server requests. The first two commands below make 112 new inference requests in total.

```powershell
python evaluation/refill_qwen_eval.py --output evaluation/qwen_refill_results.json
python evaluation/refill_qwen_eval.py --prompt v2 --temperatures 0 --holdout --output evaluation/qwen_refill_v2_results.json
python evaluation/analyze_qwen.py
python evaluation/qwen_diagnostics.py
```

Rerunning overwrites the same files. To keep existing results, pass a new filename to the evaluator's `--output` and update the analysis input to match. The original JSON preserves the request sentences, expected values, raw responses, timings, usage, and the prompt with its hash. No real customer data was used.

Files:
- [Evaluation client, cases and prompts](refill_qwen_eval.py.md)
- [v1 raw responses](qwen_refill_results.json.md)
- [v2 raw responses](qwen_refill_v2_results.json.md)
- [Analysis after format normalization](qwen_analysis.json.md)
- [Encoding and simple-task diagnostics](qwen_diagnostics.json.md)
