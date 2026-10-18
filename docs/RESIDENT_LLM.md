# Resident board LLM

Current behavior and settings follow the [LLM service](../services/qwen/README.md); operation follows the [board runbook](BOARD_RUNBOOK.md). Gemma4 is preloaded at server start without a generation call. `runner.resident/llm/pid` in `/ready` is the actual load state.

## Past verification (2026-10-17)

The following is a QA record for the previous schema (portion/clarify) and is not a current product accuracy result.

- Gemma4 first call 4.505 s (load 2.895 s), next two calls 1.569 s/1.569 s, same worker PID.
- Explicit model ID switch check: Gemma4 first call 5.606 s, reuse 1.863/1.881 s, switch to Gemma3 4.418 s, back to Gemma4 5.272 s.
- [Raw responses and stats](qwen_evaluation/resident-worker-20261017.json). These are a few smoke requests and do not guarantee full-scenario accuracy or current invoke latency.

Reusing the resident worker is not the same as reusing conversation history. KV is reset for every request. `board_llm.sh ask` is a one-shot CLI diagnostic and is separate from resident HTTP performance.
