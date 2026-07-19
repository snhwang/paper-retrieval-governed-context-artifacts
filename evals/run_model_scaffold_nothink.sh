#!/usr/bin/env bash
# Run one thinking model under the CONSTRAINED {thought, action} ReAct scaffold
# with native thinking OFF, on the full 1,100-query ToolBench test set. This is
# the exact instrument Mistral's Table 8 "ReAct" used (no --reasoning-mode), so
# it answers: does our constrained scaffold help or hurt the model, independent
# of native reasoning?
#
# One invocation produces all three constrained conditions (native off):
#   mono_react   = monolithic (3,225 tools) under the scaffold
#   bear_react   = BEAR top-5 under the scaffold
#   bear_single  = BEAR top-5 single-turn (the matched baseline)
# so scaffold-vs-single is self-contained (compare bear_react vs bear_single).
#
# Usage (from repo root):
#     MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_scaffold_nothink.sh
#     MODEL=gemma4:12b LABEL=g4-12b bash evals/run_model_scaffold_nothink.sh
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:?set MODEL, e.g. MODEL=gemma4:31b}"
LABEL="${LABEL:?set LABEL, e.g. LABEL=g4-31b}"
BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"

echo "[$(date)] scaffold (native-off) full-1100 for $MODEL (label $LABEL)"
# No --reasoning-mode => constrained {thought,action}; --reasoning-effort none
# => native thinking disabled (so the 768-token constrained budget is not starved).
python evals/eval_toolbench_react.py --reasoning-effort none \
    --temperature 1.0 --llm-top-p 0.95 --llm-top-k 64 \
    --base-url "$BASE_URL" --model "$MODEL" \
    --run-label ${LABEL}-scaffold-nothink-full 2>&1 | tee results/${LABEL}_scaffold_nothink_full.log

echo "[$(date)] DONE. Next: python evals/scaffold_vs_single.py ${LABEL}"
