#!/usr/bin/env bash
# =============================================================================
# run_evals.sh — Retrieval-Governed Prompting (BEAR paper)
#
# Reproduces the evaluations reported in the retrieval-governed-context paper.
# Evaluates retrieval quality, tool scaling, CPA comparison, token efficiency,
# and backend/governance ablation on the pet_sim corpus, plus end-to-end
# ToolBench tool selection (with --all).
#
# LLM REQUIREMENTS:
#   - Default run is deterministic (no LLM needed)
#   - With --all: eval_toolbench_e2e.py runs end-to-end ToolBench tool
#     selection (paper Table 5). Requires an OpenAI-compatible endpoint;
#     paper used mistralai/Mistral-Nemo-Instruct-2407 12B via vLLM.
#     Override defaults with --model and --base-url.
#   - eval_tool_scaling.py end-to-end dispatch (optional) tries:
#       LM Studio with mistral-nemo-instruct-2407 at http://127.0.0.1:1234/v1
#       (skips gracefully if unavailable)
#
# EMBEDDING MODELS (downloaded automatically on first use):
#   - BAAI/bge-base-en-v1.5 (768-dim) — primary
#   - Qwen/Qwen3-Embedding-0.6B, Qwen/Qwen3-Embedding-4B — backend comparison
#   - mlx-community variants if on Apple Silicon
#
# Usage:
#   ./run_evals.sh                                       # deterministic only
#   ./run_evals.sh --all                                 # + end-to-end ToolBench (LLM)
#   ./run_evals.sh --all --model mistral-nemo-instruct-2407
#   ./run_evals.sh --all --base-url http://127.0.0.1:8000/v1
# =============================================================================

set -e
cd "$(dirname "$0")"

# Detect WSL and resolve Windows host IP for LM Studio
if grep -qi microsoft /proc/version 2>/dev/null; then
    WSL_HOST=$(ip route show default 2>/dev/null | awk '/default/{print $3}')
    if [[ -n "$WSL_HOST" ]]; then
        export LM_STUDIO_URL="http://${WSL_HOST}:1234/v1"
    fi
fi

ALL=false
MODEL=""
BASE_URL=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --all) ALL=true; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        --base-url) BASE_URL="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

E2E_ARGS=""
[[ -n "$MODEL" ]]    && E2E_ARGS="$E2E_ARGS --model $MODEL"
[[ -n "$BASE_URL" ]] && E2E_ARGS="$E2E_ARGS --base-url $BASE_URL"

EVAL_DIR="evals"
RESULTS_DIR="results"
mkdir -p "$RESULTS_DIR"

echo "========================================"
echo "  Retrieval-Governed Prompting (paper)"
echo "========================================"
echo ""

# ----- §4.1 Retrieval Quality -----
echo "--- §4.1 Retrieval Quality ---"
python3 "$EVAL_DIR/eval_retrieval.py" | tee "$RESULTS_DIR/eval_retrieval_output.txt"
echo ""

# ----- §4.1 Retrieval Quality (semantic embeddings) -----
echo "--- §4.1 Retrieval Quality (semantic) ---"
python3 "$EVAL_DIR/eval_retrieval.py" --semantic | tee "$RESULTS_DIR/eval_retrieval_semantic_output.txt"
echo ""

# ----- §4.2 Tool Scaling -----
# Note: end-to-end dispatch step tries LM Studio (nemotron-3-super); skips if unavailable
echo "--- §4.2 Tool Scaling ---"
python3 "$EVAL_DIR/eval_tool_scaling.py" | tee "$RESULTS_DIR/eval_tool_scaling_output.txt"
echo ""

# ----- §4.2 Tool Composition -----
echo "--- §4.2 Tool Composition ---"
python3 "$EVAL_DIR/eval_tool_composition.py" | tee "$RESULTS_DIR/eval_tool_composition_output.txt"
echo ""

# ----- §4.3 CPA Comparison -----
echo "--- §4.3 BEAR vs CPA Baseline ---"
python3 "$EVAL_DIR/eval_baseline_comparison.py" | tee "$RESULTS_DIR/eval_baseline_output.txt"
echo ""

# ----- §4.4 Token Efficiency & Scaling -----
echo "--- §4.4 Scalability (10-500 agents) ---"
python3 "$EVAL_DIR/eval_scalability.py" | tee "$RESULTS_DIR/eval_scalability_output.txt"
echo ""

# ----- Parameter sensitivity (supports §4.1, §4.4) -----
echo "--- Parameter Sensitivity (alpha, theta, K) ---"
python3 "$EVAL_DIR/eval_ablation.py" | tee "$RESULTS_DIR/eval_ablation_output.txt"
echo ""

echo "--- Parameter Sensitivity (semantic) ---"
python3 "$EVAL_DIR/eval_ablation.py" --semantic | tee "$RESULTS_DIR/eval_ablation_semantic_output.txt"
echo ""

# ----- §4.6 Backend Comparison & Governance Ablation -----
# These require downloading embedding models (BGE-M3, Qwen3) on first run
echo "--- §4.6 Retrieval Backend Comparison ---"
python3 "$EVAL_DIR/eval_retrieval_backends.py" --all | tee "$RESULTS_DIR/eval_retrieval_backends_output.txt"
echo ""

echo "--- §4.6 Governance Ablation ---"
python3 "$EVAL_DIR/eval_governance_ablation.py" | tee "$RESULTS_DIR/eval_governance_ablation_output.txt"
echo ""

# ----- End-to-end ToolBench (REQUIRES LLM) -----
# Paper Table 5 used mistralai/Mistral-Nemo-Instruct-2407 12B via vLLM.
# Override via --model and --base-url (any OpenAI-compatible endpoint).
if [[ "$ALL" == true ]]; then
    echo "--- End-to-end ToolBench (LLM required) ---"
    python3 "$EVAL_DIR/eval_toolbench_e2e.py" $E2E_ARGS \
        | tee "$RESULTS_DIR/eval_toolbench_e2e_output.txt" \
        || echo "  [e2e ToolBench failed: see error above; continuing]"
    echo ""
else
    echo "--- Skipping end-to-end ToolBench (use --all to include) ---"
    echo "  eval_toolbench_e2e.py  (paper Table 5; needs OpenAI-compatible LLM endpoint)"
    echo ""
fi

echo "========================================"
echo "  Evals complete"
echo "  Results in: $RESULTS_DIR/"
echo "========================================"
