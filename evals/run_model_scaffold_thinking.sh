#!/usr/bin/env bash
# Constrained {thought, action} scaffold with native reasoning ON.
#
# This is the missing cell for a SAME-FORMAT reasoning ablation. We already have
# the scaffold with native reasoning OFF (run_model_scaffold_nothink.sh); pairing
# the two isolates native reasoning with the output format held constant, which
# the cross-format comparison (scaffold-off 0.660 vs reasoning-mode-on 0.620)
# cannot do.
#
# Requires the token-budget fix (commit 8b262bc): the constrained path now floors
# at 8192 tokens when reasoning is enabled, so thinking cannot starve the JSON.
#
# Usage (from repo root):
#     MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_scaffold_thinking.sh
# Optional stratified subsample instead of the full 1,100 (much faster):
#     SAMPLE=200 SEED=42 MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_scaffold_thinking.sh
#
# Cost note: monolithic + native thinking is the slowest configuration we run
# (~0.5 min/query on 31b), so the full 1,100 is ~8-9 h per model. SAMPLE=200 is
# ~1.5 h and still powers a within-model paired test.
#
# Compare against the native-off run with:
#     python evals/scaffold_thinking_ablation.py <LABEL>
set -euo pipefail
cd "$(dirname "$0")/.."

MODEL="${MODEL:?set MODEL, e.g. MODEL=gemma4:31b}"
LABEL="${LABEL:?set LABEL, e.g. LABEL=g4-31b}"
BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"
SAMPLE="${SAMPLE:-}"
SEED="${SEED:-42}"

SAMPLE_ARGS=""
SUFFIX="full"
if [ -n "$SAMPLE" ]; then
  SAMPLE_ARGS="--sample-queries $SAMPLE --sample-seed $SEED"
  SUFFIX="s${SEED}"
fi

echo "[$(date)] scaffold + native reasoning ON for $MODEL (label $LABEL, ${SAMPLE:-1100} queries)"
# No --reasoning-mode  => constrained {thought,action} scaffold
# No --reasoning-effort => native thinking left ON
python evals/eval_toolbench_react.py \
    --skip bear-single $SAMPLE_ARGS \
    --temperature 1.0 --llm-top-p 0.95 --llm-top-k 64 \
    --base-url "$BASE_URL" --model "$MODEL" \
    --run-label ${LABEL}-scaffold-thinking-${SUFFIX} 2>&1 \
  | tee results/${LABEL}_scaffold_thinking_${SUFFIX}.log

echo "[$(date)] DONE. Compare with the native-off run:"
echo "  python evals/scaffold_thinking_ablation.py ${LABEL}"
