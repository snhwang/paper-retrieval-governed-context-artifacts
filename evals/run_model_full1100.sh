#!/usr/bin/env bash
# Run one natively-thinking model on the FULL 1,100-query ToolBench test set for
# the scale experiment (Table 9): 4 conditions, cheap -> expensive. No sampling,
# no seeds -- the full standard test set is the population.
#
# Usage (from the repo root):
#     MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_full1100.sh
# BASE_URL defaults to the paper's Ollama server; override if needed.
#
# Assumes a Gemma-family thinking model (recommended sampling temp 1.0 / top_p
# 0.95 / top_k 64, reasoning toggled via --reasoning-effort). After it finishes,
# compute the grid with:  python evals/grid_from_full1100.py $LABEL
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

MODEL="${MODEL:?set MODEL, e.g. MODEL=gemma4:12b}"
LABEL="${LABEL:?set LABEL, e.g. LABEL=g4-12b}"
BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"

COMMON="--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64 --base-url $BASE_URL --model $MODEL"
PY="python evals/eval_toolbench_react.py"

echo "[$(date)] FULL-1100 runs for $MODEL (label $LABEL) @ $BASE_URL"

echo "[$(date)] (1/4) BEAR single-turn (nothink)"
$PY --skip mono-react bear-react --reasoning-effort none $COMMON \
    --run-label ${LABEL}-bearsingle-nothink-full 2>&1 | tee results/${LABEL}_bearsingle_full.log

echo "[$(date)] (2/4) BEAR + reasoning"
$PY --skip mono-react --reasoning-mode $COMMON \
    --run-label ${LABEL}-bear-full 2>&1 | tee results/${LABEL}_bear_full.log

echo "[$(date)] (3/4) Monolithic, reasoning OFF"
$PY --skip bear-react bear-single --reasoning-mode --reasoning-effort none $COMMON \
    --run-label ${LABEL}-mono-nothink-full 2>&1 | tee results/${LABEL}_mono_nothink_full.log

echo "[$(date)] (4/4) Monolithic, reasoning ON (slowest)"
$PY --skip bear-react bear-single --reasoning-mode $COMMON \
    --run-label ${LABEL}-mono-think-full 2>&1 | tee results/${LABEL}_mono_think_full.log

echo "[$(date)] DONE. Next: python evals/grid_from_full1100.py ${LABEL}"
