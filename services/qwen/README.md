# Qwen generation server / board Gemma

`server.py:create_app`, default 127.0.0.1:8000. POST `/v1/chat/completions`, GET
`/v1/models`, `/health`, `/ready`. Validates model/messages/generation options, provides a queue with 4 admitted / 1
concurrent, a 20-second queue+execution timeout, and request IDs/logs. The product prompt and `intent/item`
validation are owned by `app/language.py` and the Controller. `portion` is not used, and requests that are not
understood are returned as `not_understood`. There is no automatic fixture fallback.

## Board: resident Gemma4

`QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4` connect to the same `BoardLLMBackend` as the
existing board config. A separate `board` backend setting is not used.
The organizers' bundle has no Qwen3 `.pte`, so the actual board model is Gemma; the service name, port and
`QWEN_*` are names for the API boundary with the Controller. For installation records see
[BOARD_RUNBOOK](../../docs/BOARD_RUNBOOK.md), and for earlier resident measurements see
[RESIDENT_LLM](../../docs/RESIDENT_LLM.md).

- At server start, the Gemma4 worker is launched and the server waits for the model-loaded signal. No generation
  request is sent. Requests for the same model reuse the same PID and loaded QNN context.
- If a file is missing, the worker errors, or the 120-second startup timeout hits, server startup fails and the child is cleaned up.
  `/ready` is ready=true only while an actually loaded worker is alive.
- On cancellation, timeout or execution error, the worker process group is reaped. `/ready` is then false, and the model
  is reloaded on the next generation request. KV is reset between requests.
- The Gemma3 model, upload and explicit run code is kept, but the default selection and evaluation use Gemma4.
  `scripts/board_llm.sh use gemma4` pins the selection, and API startup always loads Gemma4.
- API `model=gemma3|gemma4` supports explicit switching. The response `runner` contains the actual model, PID,
  cold_start, load_seconds and prefill/decode stats.
- `QWEN_MODEL` is the API identifier. To change processes and settings that used the old Qwen ID, restart the
  Controller and the Qwen service together. The native worker and compatible bundle are installed separately.

For start commands with the selected env made explicit, follow the [board runbook](../../docs/BOARD_RUNBOOK.md).

## Dev HTTP / fixture

`QWEN_MODEL_BACKEND=mlx` calls the Mac HTTP at `QWEN_UPSTREAM_URL`.
`fixture` is deterministic and for development. The Controller's `QWEN_BACKEND=fixture|http` is separate from the
server's internal settings. direct calls the Mac directly; proxy/integration go through our server.
[Contracts](../../docs/CONTRACTS.md), [Model files guide](../../models/README.md).

## Optional Qwen CLI adapter

Only `QWEN_MODEL_BACKEND=qwen_cli` uses `common.backends.ExecuTorchBackend`.
Do not switch the existing `executorch` board config to this CLI. If you have separately obtained a compatible Qwen3 `.pte`, tokenizer
and runner, set `QNN_LLAMA_RUNNER`, `QWEN_MODEL_PATH`,
`QWEN_TOKENIZER_PATH` and `QWEN_SEQ_LEN`. This is not the path for the current board Gemma.

The Qwen CLI launches a process for every request. It passes ChatML and a non-thinking prefix, the qwen3 decoder,
temperature, total seq_len and output_path, then reads the output file. seq_len is the total
input+output limit, and max_completion_tokens is not enforced. On timeout/cancellation the
child is terminated and reaped. The real Qwen board model, template and NPU behavior are not verified; the contract is checked with a process
double. [QC guide](../../qc-executorch-guide/IoT/README.md#part-4-run-qwen-06b).
