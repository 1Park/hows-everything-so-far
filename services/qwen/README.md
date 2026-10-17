# Qwen generation service

## Resident board Gemma4

`QWEN_MODEL_BACKEND=board`, `QWEN_MODEL=gemma4` uses `BoardLLMBackend` and
`scripts/board_llm.sh`. FastAPI startup loads Gemma4 and waits for the native
worker's ready event before accepting requests. No generation request is sent.
Missing assets, worker failure, or a 120-second startup timeout fail server startup
and reap the child process. `/ready` requires a live loaded worker. Normal requests
reuse the same model process; shutdown closes it. After a runtime failure, readiness
is false until a subsequent request reloads the worker. Gemma3 support remains for
explicit use, but startup always selects Gemma4. The native worker and compatible
Gemma4 bundle must already be installed on the board; this code does not upload models.

`server.py:create_app`, default 127.0.0.1:8000. POST /v1/chat/completions,
GET /v1/models, /health, /ready. Validated messages/options, queue4/concurrency1,
request IDs and timeout. Product prompts/JSON validation remain in app/language.py.
Backends: mlx calls Mac HTTP; fixture is explicit; executorch calls the track native
qnn_llama_runner. No automatic fallback.

## Board ExecuTorch

Obtain the compatible QCS8275 runner, Qwen3-0.6B .pte, matching tokenizer.bin
and QNN/HTP libraries from the track team. See the
[QC guide](../../qc-executorch-guide/IoT/README.md#part-4-run-qwen-06b).
Set actual paths as process environment variables or in a personal env file:

```bash
export QNN_LLAMA_RUNNER=/actual/bundle/qnn_llama_runner
export QWEN_MODEL_PATH=/actual/bundle/qwen_0p6B_monza.pte
export QWEN_TOKENIZER_PATH=/actual/bundle/tokenizer.bin
export QWEN_SEQ_LEN=512  # example ONLY: use the bundle-supported total token budget
python scripts/dev.py --mode board --env-file .env.board
```

Configure ADSP_LIBRARY_PATH/LD_LIBRARY_PATH according to the supplied image only.
Relative asset paths resolve against the repository; QWEN_MODEL is the API ID.
Missing assets/sequence limit -> readiness503. Readiness checks files/config,
**not successful runtime loading**. Run real generations before claiming readiness.

The adapter passes preformatted Qwen ChatML with all messages and a non-thinking
assistant prefix via --prompt, plus --decoder_model_version qwen3, --temperature,
--seq_len and --output_path. Check supplied runner --help/source for flag and
raw-prompt compatibility: the QC guide board build supports qwen3; stock upstream
versions may differ. Do not substitute a decoder or double-wrap the template.
Output comes from the output file, never scraped logs. Exact prompt echo is removed.
Empty/failed output returns an error; app JSON validation remains strict.

Limits: one native process per request, not persistent model loading. Native seq_len
bounds TOTAL prompt+output tokens. It does not enforce max_completion_tokens;
responses explicitly report runner_limits.completion_token_limit_enforced=false.
Exact completion budgets need a matching native tokenizer/runner extension.
Timeout/cancellation kills and reaps the child. stdout/stderr are discarded to
avoid exposing customer prompts; use scripts/runner_smoke.py for standalone diagnostics.

Tests use a real child-process double. Actual .pte inference, tokenizer/template
correctness, board latency/memory and NPU delegation remain **unverified**.
