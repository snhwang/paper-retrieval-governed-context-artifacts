#!/usr/bin/env bash
# Run one natively-thinking model on the FULL 1,100-query ToolBench test set for
# the scale experiment (Table 9): 4 conditions, cheap -> expensive. No sampling,
# no seeds -- the full standard test set is the population.
#
# Usage (from the repo root):
#     MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_full1100.sh
#     STAGES="3 4" MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_full1100.sh
# BASE_URL defaults to the paper's Ollama server; override if needed.
#
# STAGES picks the runs by number ("1 2 3 4" when unset). Each run is one pass over
# the 1,100 queries and writes its own files, so the runs can be made one at a time.
# A model whose four runs do not fit in one booked night needs that
# (reproduce/56_e2e_long_context.sh, parts g12-native and g31-native).
#
# Assumes a Gemma-family thinking model (recommended sampling temp 1.0 / top_p
# 0.95 / top_k 64, reasoning toggled via --reasoning-effort). After it finishes,
# compute the grid with:  python evals/grid_from_full1100.py $LABEL
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

MODEL="${MODEL:?set MODEL, e.g. MODEL=gemma4:12b}"
LABEL="${LABEL:?set LABEL, e.g. LABEL=g4-12b}"
BASE_URL="${BASE_URL:-http://127.0.0.1:11434/v1}"  # the Windows Ollama, reached from WSL (mirrored networking)
STAGES="${STAGES:-1 2 3 4}"
for s in $STAGES; do case $s in 1|2|3|4) ;; *) echo "STAGES takes the numbers 1 to 4, not '$s'" >&2; exit 2 ;; esac; done
want() { [[ " $STAGES " == *" $1 "* ]]; }

# LLM_SEED, when set, goes with every request (evals/e2e_rerun/PLAN.md). Unset, no seed is sent, as in July.
COMMON="--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64 --base-url $BASE_URL --model $MODEL${LLM_SEED:+ --seed $LLM_SEED}"
PY="python evals/eval_toolbench_react.py"

echo "[$(date)] FULL-1100 runs for $MODEL (label $LABEL) @ $BASE_URL, runs: $STAGES"

if want 1; then
  echo "[$(date)] (1/4) BEAR single-turn (nothink)"
  $PY --skip mono-react bear-react --reasoning-effort none $COMMON \
      --run-label ${LABEL}-bearsingle-nothink-full 2>&1 | tee results/${LABEL}_bearsingle_full.log
fi

if want 2; then
  echo "[$(date)] (2/4) BEAR + reasoning"
  $PY --skip mono-react --reasoning-mode $COMMON \
      --run-label ${LABEL}-bear-full 2>&1 | tee results/${LABEL}_bear_full.log
fi

if want 3; then
  # Free-form prompt with the reasoning channel off. A thinking model often answers nothing here.
  # In July 2026 this run scored 0.145 on Gemma 4 12B, before the script counted empty answers.
  # On 21 Nov 2026 the check for empty answers stopped it (15 of the first 25 were empty). That
  # check is lifted for this run only, so that the run completes and its count of empty answers
  # is on record (PLAN.md, version 4). The value is not in the paper.
  echo "[$(date)] (3/4) Monolithic, reasoning OFF"
  $PY --skip bear-react bear-single --reasoning-mode --reasoning-effort none --max-empty-rate 1.0 $COMMON \
      --run-label ${LABEL}-mono-nothink-full 2>&1 | tee results/${LABEL}_mono_nothink_full.log
fi

if want 4; then
  echo "[$(date)] (4/4) Monolithic, reasoning ON (slowest)"
  $PY --skip bear-react bear-single --reasoning-mode $COMMON \
      --run-label ${LABEL}-mono-think-full 2>&1 | tee results/${LABEL}_mono_think_full.log
fi

echo "[$(date)] DONE (runs: $STAGES). When all four are in: python evals/grid_from_full1100.py ${LABEL}"
