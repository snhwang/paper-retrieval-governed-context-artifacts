#!/usr/bin/env bash
# Table 7 (tab:e2e) executor reruns on the BEAR 0.4.2 top-5 lists.
# Prepared 2026-10-30. Do not start without the coordinator's go: the executor
# runs on the shared GPU.
#
# Usage, in WSL, from an artifacts clone that holds the lists:
#   WP0_WIN_GPU_MAX_MIB=<limit agreed with model-server> \
#       bash evals/wp0_v040/run_e2e_rerun.sh [EXECUTOR ...]      (default: mistral-nemo)
#
# Executors run one at a time, in the order given. Only one exists, because
# only Table 7 has BM25 rows, and Table 7 has a single executor:
#   mistral-nemo  Mistral-Nemo-Instruct-2407 12B, Q4_0, Ollama on this PC
#                 (port 11434, the server the published run used), single-turn
#                 constrained selection. Rows, 1,100 calls each:
#                   BEAR+BM25 (gov), BM25 (no gov)            the rerun
#                   BEAR+BGE (gov), BGE (no gov)              control: same lists
#                   as published, so any change is executor drift
#                 Set WP0_E2E_ROWS to run fewer rows (names as in ROWS of
#                 e2e_rerun.py, separated by ";").
# Tables 8 and 9 (ReAct, Gemma 4 12B and 31B, thinking or not) use BGE only,
# whose lists did not change, so they need no rerun.
#
# Card limits agreed with model-server (2026-10-30), Windows nvidia-smi MiB,
# both required, both "at most":
#   WP0_WIN_GPU_MAX_MIB=67000      before loading, with nothing of ours resident
#   WP0_WIN_GPU_ROW_MAX_MIB=81000  after loading and before each row, with our
#                                  model resident
# Guards, in order. A failed guard exits 75:
#   1. The Qwen3-4B GPU lane (wp0-gpuq4b042) must not be running. The two GPU
#      jobs never overlap.
#   2. ~/tist-gpu.lock is taken with flock (waiting WP0_LOCK_WAIT seconds,
#      default 0), so a job holding it blocks this one.
#   3. The card is at most WP0_WIN_GPU_MAX_MIB, and no Ollama model is loaded
#      (ours included).
#   4. The tag digest and the GGUF layer must be the expected ones.
#   5. After loading, Ollama must report the 32,768 window, and the card must
#      be at most WP0_WIN_GPU_ROW_MAX_MIB, checked again before every row.
# Whatever happens after the load, the script unloads the model it loaded
# (keep_alive 0), and only that model, then confirms with /api/ps and writes
# <out>/UNLOADED. WP7 stage 2 starts after that. Each call also records
# Ollama's prompt_tokens, and a prompt at the window stops the run (Ollama
# truncates silently).
#
# Model choice. The published run asked for "mistral-nemo" (tag digest
# e7e06d107c6c). The server now defaults to a 262,144-token window, which
# would hold about 40 GiB of KV cache for this model. "mistral-nemo-32k" (tag
# d79a1e80980f, created 2026-07-09 from the same GGUF layer b559938ab7a0, the
# same template and stop words, plus num_ctx 32768) bounds it to about 5 GiB.
# The retrieval prompts need under 1,000 tokens. Agreed with model-server:
# use this tag, not an Ollama restart.
set -u
: "${WP0_WIN_GPU_MAX_MIB:?set WP0_WIN_GPU_MAX_MIB (agreed: 67000), the limit before loading}"
: "${WP0_WIN_GPU_ROW_MAX_MIB:?set WP0_WIN_GPU_ROW_MAX_MIB (agreed: 81000), the limit with the model resident}"
if systemctl --user is-active -q wp0-gpuq4b042 2>/dev/null; then
  echo "the Qwen3-4B GPU lane (wp0-gpuq4b042) is running; not started"; exit 75
fi
ROOT=${WP0_ROOT:-$HOME/tist-evals/wp0-v042}
ART=${WP0_ART:-$ROOT/artifacts}
PY=${WP0_PY:-$HOME/.venvs/tist-evals/bin/python}
OUT=${WP0_E2E_OUT:-$ART/results/v042/e2e_rerun}
LOGS=$ROOT/logs
LISTS=("$ROOT/artifacts/results/wp0/lists_v042/e2e" "$ROOT/artifacts-dense/results/wp0/lists_v042/e2e")
BASE_URL=${WP0_OLLAMA_URL:-http://192.168.1.175:11434/v1}
BEAR_SHA=$(cat "$HOME/tist-evals/bear-9d085b4/BEAR_GIT_SHA" 2>/dev/null || echo unknown)
mkdir -p "$OUT" "$LOGS"
cd "$ART" || exit 1

run_executor() {
  local ex=$1 model digest ctx rows
  case $ex in
    mistral-nemo)
      model=${WP0_E2E_MODEL:-mistral-nemo-32k}
      digest=${WP0_E2E_DIGEST:-d79a1e80980f}
      ctx=32768
      rows=${WP0_E2E_ROWS:-"BEAR+BM25 (gov);BM25 (no gov);BEAR+BGE (gov);BGE (no gov)"} ;;
    *) echo "unknown executor $ex"; return 2 ;;
  esac
  local IFS=';'; local -a R=($rows); unset IFS
  local log=$LOGS/e2e_rerun_$ex.log
  {
    echo "### ================ attempt $(date -Is) ================"
    echo "### executor: $ex, model $model (digest $digest), ctx $ctx, url $BASE_URL"
    echo "### rows:     ${R[*]}"
    echo "### card:     at most ${WP0_WIN_GPU_MAX_MIB} MiB before loading, ${WP0_WIN_GPU_ROW_MAX_MIB} MiB with the model resident"
    echo "### bear:     0.4.2 ($BEAR_SHA), lists ${LISTS[*]}"
  } >> "$log"
  # The client loads no model and uses no GPU itself. The card work happens in
  # Ollama on Windows, so the lock is held for the whole executor.
  flock -E 75 -w "${WP0_LOCK_WAIT:-0}" "$HOME/tist-gpu.lock" \
    "$HOME/bin/tist-capped" --mem 4G -- env \
      CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 WP0_NO_LOCAL_MODELS=1 \
      PYTHONUNBUFFERED=1 PYTHONPATH=evals/wp0_v040/site BEAR_SOURCE_SHA="$BEAR_SHA" \
      "$PY" evals/wp0_v040/e2e_rerun.py --rows "${R[@]}" --lists "${LISTS[@]}" \
        --model "$model" --expect-digest "$digest" --expect-ctx "$ctx" --base-url "$BASE_URL" \
        --win-gpu-max-mib "$WP0_WIN_GPU_MAX_MIB" --win-gpu-row-max-mib "$WP0_WIN_GPU_ROW_MAX_MIB" \
        --verify-live --out "$OUT/$ex" >> "$log" 2>&1
  local rc=$?
  case $rc in
    0)  echo "[$(date '+%F %T')] $ex done" | tee -a "$log" ;;
    1)  echo "[$(date '+%F %T')] $ex failed (rc 1), see $log" | tee -a "$log" ;;
    75) echo "[$(date '+%F %T')] $ex not started: lock held, or a card or server check failed, see $log" | tee -a "$log" ;;
    137) echo "[$(date '+%F %T')] $ex killed by the 4G memory cap (rc 137)" | tee -a "$log" ;;
    *)  echo "[$(date '+%F %T')] $ex failed (rc $rc), see $log" | tee -a "$log" ;;
  esac
  return $rc
}

for ex in "${@:-mistral-nemo}"; do
  run_executor "$ex" || exit $?
done
