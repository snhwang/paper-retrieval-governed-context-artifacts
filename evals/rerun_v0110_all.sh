#!/usr/bin/env bash
# Unattended re-run of every BEAR-0.1.10-affected eval EXCEPT the expensive
# vLLM ReAct job, which is gated behind a cheap embedding-only retrieval diff.
#
# Each step tees to results/logs/ and continues on failure, so you come back to
# as much progress as possible. New/authoritative outputs are written; the old
# (pre-fix) JSONs remain in git history for diffing.
#
# Requires: bear 0.1.10 active in this env (editable-installed bear-dev).
# Run from the repo root:
#     bash evals/rerun_v0110_all.sh
set -u
cd "$(dirname "$0")/.."
mkdir -p results/logs

echo "### bear version:"
python -c "import bear; print(bear.__version__)" || { echo "bear import failed"; exit 1; }

echo
echo "### [1/5] MetaTool+QueryTags-top5 (affected: gated + inferred tags)"
python evals/eval_toolbench.py --top-k 5 --metatool-query-tags-only \
    --metatool-query-tags-file evals/data/external_benchmarks/metatool/query_tags_top5.json \
    --output results/toolbench_eval_qtags_top5_v0110.json \
    2>&1 | tee results/logs/qtags_top5_v0110.log || echo "FAILED: qtags_top5"

echo
echo "### [2/5] ToolBench inferred-categories (LLM labels cached -> retrieval only)"
echo "    (uses results/toolbench_inferred_categories.json cache; no new API calls)"
python evals/eval_toolbench_inferred_categories.py \
    2>&1 | tee results/logs/inferred_v0110.log || echo "FAILED: inferred"

echo
echo "### [3/5] Pet-Sim governance decomposed ablation (all backends)"
python evals/eval_governance_decomposed.py \
    2>&1 | tee results/logs/decomposed_v0110.log || echo "FAILED: decomposed"

echo
echo "### [4/5] Pet-Sim alpha sweep (all backends)"
python evals/eval_alpha_sweep.py \
    2>&1 | tee results/logs/alpha_v0110.log || echo "FAILED: alpha"

echo
echo "### [5/5] ReAct retrieval diff (embedding only; decides if the vLLM job needs re-running)"
python evals/diag_react_retrieval_diff.py --top-k 5 \
    2>&1 | tee results/logs/react_diff_v0110.log || echo "FAILED: react_diff"

echo
echo "### DONE. Review results/logs/*.log; new JSONs are under results/."
echo "### Then: git add -A results/ && git commit -m 'v0.1.10 affected-eval re-runs' && git push"
