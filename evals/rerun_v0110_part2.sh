#!/usr/bin/env bash
# Part 2 of the BEAR 0.1.10 re-runs: the offline pieces the first orchestrator
# missed, plus reproducibility-capture of the audit/diagnostic scripts. All
# offline, no LLM, no key. The one remaining GPU/vLLM job (eval_toolbench_react
# -> tab:e2e / tab:e2e-react) is NOT here; run that separately with the model
# server up.
#
# Each step tees to results/logs/ and continues on failure. Requires bear 0.1.10.
# Run from the repo root:
#     bash evals/rerun_v0110_part2.sh
set -u
cd "$(dirname "$0")/.."
mkdir -p results/logs

echo "### bear version:"
python -c "import bear; print(bear.__version__)" || { echo "bear import failed"; exit 1; }

echo
echo "### [1/8] Table 4: LLM-inferred multi-category (cache complete -> no API calls)"
python evals/eval_toolbench_multitag_categories.py \
    2>&1 | tee results/logs/multitag_v0110.log || echo "FAILED: multitag"

echo
echo "### [2/8] Table 4: LLM-inferred top-5 categories (cache complete -> no API calls)"
python evals/eval_toolbench_top5_categories.py \
    2>&1 | tee results/logs/top5cats_v0110.log || echo "FAILED: top5cats"

echo
echo "### [3/8] tab:retrieval (Pet-Sim) -- hash embeddings"
python evals/eval_retrieval.py \
    2>&1 | tee results/logs/retrieval_hash_v0110.log || echo "FAILED: retrieval_hash"

echo
echo "### [4/8] tab:retrieval (Pet-Sim) -- semantic (BGE) embeddings"
python evals/eval_retrieval.py --semantic \
    2>&1 | tee results/logs/retrieval_semantic_v0110.log || echo "FAILED: retrieval_semantic"

echo
echo "### [5/8] backend-comparison table (Pet-Sim, all semantic backends + bm25)"
python evals/eval_retrieval_backends.py \
    --models bge bge-m3 qwen3 qwen3-4b bm25 \
    --output results/backend_comparison.json \
    2>&1 | tee results/logs/backends_v0110.log || echo "FAILED: backends"

echo
echo "### [6/8] composite-scale audit (repro-capture -> composite_scale_audit.json)"
python evals/eval_composite_scale_audit.py --backends bge bge-m3 qwen3 qwen3-4b bm25 \
    2>&1 | tee results/logs/composite_audit_v0110.log || echo "FAILED: composite_audit"

echo
echo "### [7/8] Pet-Sim fix diagnosis (repro-capture -> petsim_fix_diagnosis.json)"
python evals/eval_petsim_fix_diagnosis.py --backends bge bge-m3 qwen3 qwen3-4b bm25 \
    2>&1 | tee results/logs/petsim_diag_v0110.log || echo "FAILED: petsim_diag"

echo
echo "### [8/8] ToolBench-IR transfer (repro-capture -> backend_transfer_*.json)"
python evals/eval_backend_transfer.py --corpus metatool \
    2>&1 | tee results/logs/transfer_metatool_v0110.log || echo "FAILED: transfer_metatool"
python evals/eval_backend_transfer.py --corpus toolbench \
    2>&1 | tee results/logs/transfer_toolbench_v0110.log || echo "FAILED: transfer_toolbench"

echo
echo "### DONE. Review results/logs/*.log; new JSON + printed tables under results/."
echo "### Still to run separately (GPU/vLLM): eval_toolbench_react.py -> tab:e2e / tab:e2e-react."
echo "### Then: git add -A results/ && git commit -m 'v0.1.10 part-2 re-runs' && git push"
