#!/usr/bin/env bash
# Extend Gemma4:31b to the full 1,100-query ToolBench test set for Table 9 by
# running ONLY the 734-query complement of the stratified pilot (seed42 u seed43
# = 366 already done). Then run evals/merge_gemma_full1100.py to stitch them into
# the full standard test set -- no query is evaluated twice.
#
# Usage (from the repo root):
#     bash evals/run_gemma_complement.sh
# Override the server/model if needed:
#     BASE_URL=http://localhost:11434/v1 MODEL=gemma4:31b bash evals/run_gemma_complement.sh
#
# Conditions run cheap -> expensive so a flag error surfaces on the ~40min BEAR
# run rather than after hours of monolithic. Gemma sampling is its recommended
# temperature 1.0 / top_p 0.95 / top_k 64. Each condition replicates its
# stratified-run flags exactly, only swapping --sample-queries for the explicit
# complement index list.
set -euo pipefail
cd "$(dirname "$0")/.."   # repo root

BASE_URL="${BASE_URL:-http://192.168.1.175:11434/v1}"
MODEL="${MODEL:-gemma4:31b}"
IDX="results/g4_complement_indices.json"

echo "[$(date)] regenerating the complement index split"
python evals/make_complement_indices.py

COMMON="--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64 --base-url $BASE_URL --model $MODEL --query-indices-file $IDX"
PY="python evals/eval_toolbench_react.py"

echo "[$(date)] START complement runs (734 queries) on $MODEL @ $BASE_URL"

echo "[$(date)] (1/4) BEAR single-turn (nothink)"
$PY --skip mono-react bear-react --reasoning-effort none $COMMON \
    --run-label g4-bearsingle-nothink-compl 2>&1 | tee results/g4_bearsingle_compl.log

echo "[$(date)] (2/4) BEAR + reasoning (bear-react)"
$PY --skip mono-react --reasoning-mode $COMMON \
    --run-label g4-bear-compl 2>&1 | tee results/g4_bear_compl.log

echo "[$(date)] (3/4) Monolithic, reasoning OFF"
$PY --skip bear-react bear-single --reasoning-mode --reasoning-effort none $COMMON \
    --run-label g4-mono-nothink-compl 2>&1 | tee results/g4_mono_nothink_compl.log

echo "[$(date)] (4/4) Monolithic, reasoning ON (slowest)"
$PY --skip bear-react bear-single --reasoning-mode $COMMON \
    --run-label g4-mono-think-compl 2>&1 | tee results/g4_mono_think_compl.log

echo "[$(date)] ALL COMPLEMENT RUNS COMPLETE"
echo "Next: python evals/merge_gemma_full1100.py   # stitches pilot + complement -> full 1,100"
