#!/usr/bin/env bash
# Board LLM switcher — runs the organizer's Gemma bundles (QCS8275 .pte) with qnn_llama_runner (NPU).
# Bundles: ~/model_output/gemma3_1b, ~/model_output/gemma4_e2b (organizer Drive "ExecuTorch/Ventuno Q",
# docs/BOARD_RUNBOOK.md)
#
#   llm.sh status                     selected model, available memory, memory needed per model
#   llm.sh use gemma3|gemma4|auto     pin the model (auto = pick by available memory on every run)
#   llm.sh ask [-m model] [-s system] [-n seq_len] [--raw] "prompt"
#                                     one generation with the selected model. Answer only on stdout, speed/memory on stderr
#
# auto rule: gemma4 if MemAvailable ≥ gemma4 peak memory + margin (AUTO_MARGIN_MB), otherwise gemma3.
# Required memory (peak_mb) is the peak RSS measured on the board with /usr/bin/time -v (hybrid mode).
set -euo pipefail

ET="${EXECUTORCH_ROOT:-$HOME/git/executorch}"
RUNNER="${QNN_LLAMA_RUNNER:-$ET/build-x86/examples/qualcomm/oss_scripts/llama/qnn_llama_runner}"
export LD_LIBRARY_PATH="$ET/build-x86/backends/qualcomm:/usr/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export ADSP_LIBRARY_PATH="${ADSP_LIBRARY_PATH:-/usr/lib}"
STATE="${LLM_STATE_FILE:-$HOME/model_output/llm_selected}"
AUTO_MARGIN_MB="${AUTO_MARGIN_MB:-1500}"

# name | folder | .pte | runner decoder_model_version | context | peak RSS (MB, measured in hybrid mode)
MODELS="gemma3|$HOME/model_output/gemma3_1b|gemma3-1b_qcs8275_ctxt-5000.pte|gemma3|5000|1400
gemma4|$HOME/model_output/gemma4_e2b|gemma4_e2b_QCS8275_ctxt_2000.pte|gemma4|2000|2200"

field() { echo "$MODELS" | awk -F'|' -v n="$1" -v i="$2" '$1==n {print $i}'; }
avail_mb() { awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo; }
selected() { [ -f "$STATE" ] && cat "$STATE" || echo gemma4; }

resolve() {  # auto → concrete model name
  local sel="$1"
  if [ "$sel" != auto ]; then echo "$sel"; return; fi
  local need4; need4=$(( $(field gemma4 6) + AUTO_MARGIN_MB ))
  if [ "$(avail_mb)" -ge "$need4" ] && [ -f "$(field gemma4 2)/$(field gemma4 3)" ]; then echo gemma4; else echo gemma3; fi
}

cmd_status() {
  echo "selected : $(selected)  → would run: $(resolve "$(selected)")"
  echo "available: $(avail_mb) MB (auto picks gemma4 at ≥ $(( $(field gemma4 6) + AUTO_MARGIN_MB )) MB)"
  echo "$MODELS" | while IFS='|' read -r n d p v c peak; do
    if [ -f "$d/$p" ]; then st="ok ($(du -h "$d/$p" | cut -f1))"; else st="MISSING"; fi
    printf '  %-7s ctx %-5s peak ~%s MB  %s\n' "$n" "$c" "$peak" "$st"
  done
}

cmd_use() {
  case "${1:-}" in gemma3|gemma4|auto) ;; *) echo "usage: llm.sh use gemma3|gemma4|auto" >&2; exit 2;; esac
  mkdir -p "$(dirname "$STATE")"; echo "$1" > "$STATE"; echo "selected: $1"
}

# JSON configuration for the persistent API. No inference or allocation.
cmd_config() {
  local sel name dir worker
  sel="${LLM_SELECTION:-$(selected)}"
  name="${1:-$(resolve "$sel")}"
  dir=$(field "$name" 2)
  [ -n "$dir" ] || { echo "Unknown board LLM: $name" >&2; exit 2; }
  worker="${QNN_LLM_WORKER:-$ET/examples/qualcomm/oss_scripts/llama/qnn_llm_runner_host}"
  python3 - "$sel" "$name" "$dir/$(field "$name" 3)" "$dir/tokenizer.json" "$worker" "$LD_LIBRARY_PATH" "$ADSP_LIBRARY_PATH" <<'PY'
import json, sys
print(json.dumps(dict(zip(('selection', 'name', 'model_path', 'tokenizer_path', 'worker', 'ld_library_path', 'adsp_library_path'), sys.argv[1:]))))
PY
}

cmd_ask() {
  local model="" system="" seq="" raw=0
  while [ $# -gt 0 ]; do
    case "$1" in
      -m) model="$2"; shift 2;; -s) system="$2"; shift 2;; -n) seq="$2"; shift 2;;
      --raw) raw=1; shift;; --) shift; break;; -*) echo "unknown option $1" >&2; exit 2;; *) break;;
    esac
  done
  local prompt="${*:-}"; [ -n "$prompt" ] || { echo "usage: llm.sh ask [-m model] [-s system] [-n seq_len] \"prompt\"" >&2; exit 2; }
  local name; name=$(resolve "${model:-$(selected)}")
  local dir pte ver ctx peak; dir=$(field "$name" 2); pte=$(field "$name" 3); ver=$(field "$name" 4); ctx=$(field "$name" 5); peak=$(field "$name" 6)
  [ -n "$dir" ] || { echo "unknown model: $name" >&2; exit 2; }
  [ -f "$dir/$pte" ] || { echo "$name: $dir/$pte not found" >&2; exit 3; }
  local avail; avail=$(avail_mb)
  if [ "$avail" -lt $(( peak + 300 )) ]; then echo "$name: not enough memory (available ${avail}MB < need ~$(( peak + 300 ))MB)" >&2; exit 4; fi
  seq="${seq:-$ctx}"
  local args=(--decoder_model_version "$ver" --model_path "$dir/$pte" --tokenizer_path "$dir/tokenizer.json"
              --eval_mode 1 --seq_len "$seq" --temperature 0)
  if [ -n "$system" ]; then
    # gemma3: the runner puts system after the model turn → prepend it to the first user message,
    # as the Gemma3 format expects
    if [ "$ver" = gemma3 ]; then prompt="$system"$'\n\n'"$prompt"; else args+=(--system_prompt "$system"); fi
  fi
  local tmp attempt; tmp=$(mktemp -d)
  for attempt in 1 2 3; do
    ( cd "$tmp" && "$RUNNER" "${args[@]}" --prompt "$prompt" --output_path "$tmp/out.txt" > "$tmp/log" 2>&1 ) && break
    # Right after a previous LLM run, NPU (HTP) memory is released late and context creation fails
    # → wait briefly and retry
    if [ "$attempt" -lt 3 ] && grep -qE "Failed to find available PD|Can't create context from binary" "$tmp/log"; then
      echo "[$name] NPU memory not released yet — attempt ${attempt} failed, retrying in 5s" >&2; sleep 5; continue
    fi
    echo "$name: runner failed" >&2; grep -E "ERROR|Error|error" "$tmp/log" | tail -8 >&2; rm -rf "$tmp"; exit 5
  done
  if [ "$raw" = 1 ]; then cat "$tmp/out.txt"; else
    # Keep the text after the last model turn and strip end-of-turn tokens
    python3 - "$tmp/out.txt" <<'PY'
import re, sys
t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for marker in ("<|turn>model\n", "<start_of_turn>model\n"):
    if marker in t:
        t = t.rsplit(marker, 1)[1]
        break
print(re.split(r"<end_of_turn>|<turn\|>|<eos>", t)[0].strip())
PY
  fi
  local stats; stats=$(grep -o 'PyTorchObserver {.*}' "$tmp/log" | sed 's/PyTorchObserver //' || true)
  [ -n "$stats" ] && echo "[$name] $(echo "$stats" | python3 -c 'import json,sys; s=json.load(sys.stdin); print(f"load {(s["model_load_end_ms"]-s["model_load_start_ms"])/1000:.1f}s | prompt {s["prompt_tokens"]} tok @ {s["prefill_token_per_sec"]:.0f} tok/s | gen {s["generated_tokens"]} tok @ {s["decode_token_per_sec"]:.1f} tok/s | ttft {(s["first_token_ms"]-s["inference_start_ms"])/1000:.2f}s")')" >&2
  rm -rf "$tmp"
}

case "${1:-status}" in
  status) cmd_status;; use) shift; cmd_use "$@";; config) shift; cmd_config "$@";; ask) shift; cmd_ask "$@";;
  *) sed -n '2,12p' "$0"; exit 2;;
esac
