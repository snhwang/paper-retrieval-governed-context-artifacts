#!/usr/bin/env bash
# =============================================================================
# run_evals.sh — Retrieval-Governed Prompting (BEAR paper)
#
# Reproduces the evaluations reported in the retrieval-governed-context paper.
# Evaluates retrieval quality, tool scaling, CPA comparison, token efficiency,
# behavioral divergence, and backend/governance ablation on the pet_sim corpus.
#
# LLM REQUIREMENTS:
#   - Most evals are deterministic (no LLM needed)
#   - eval_behavioral_divergence.py requires:
#       LM Studio running with: mistral-nemo-instruct-2407 (Mistral Nemo 12B)
#       OR set OPENAI_API_KEY and pass --base-url https://api.openai.com/v1 --model gpt-5.4-2026-03-05
#   - eval_tool_scaling.py end-to-end dispatch (optional) tries:
#       LM Studio with mistral-nemo-instruct-2407 at http://127.0.0.1:1234/v1
#       (skips gracefully if unavailable)
#
# EMBEDDING MODELS (downloaded automatically on first use):
#   - BAAI/bge-base-en-v1.5 (768-dim) — primary
#   - Qwen/Qwen3-Embedding-0.6B, Qwen/Qwen3-Embedding-4B — backend comparison
#   - mlx-community variants if on Apple Silicon
#
# Note: the paper reports an 8-condition divergence matrix (2 LLMs × 2 retrieval
# modes × 2 temperatures). With --all, this runner generates the full matrix
# automatically — one .json + .txt per condition in results/, skipping any LLM
# whose API key is not set.
#
# Usage:
#   ./run_evals.sh                              # deterministic only
#   ./run_evals.sh --all                        # include LLM-dependent evals (full matrix)
#   ./run_evals.sh --all --model MODEL_ID       # model override (role_divergence only)
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
while [[ $# -gt 0 ]]; do
    case "$1" in
        --all) ALL=true; shift ;;
        --model) MODEL="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

MODEL_ARGS=""
if [[ -n "$MODEL" ]]; then
    MODEL_ARGS="--model $MODEL"
fi

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

# ----- §4.5 Behavioral Divergence (retrieval-level, no LLM) -----
echo "--- §4.5 Behavioral Divergence (retrieval-level) ---"
python3 "$EVAL_DIR/eval_divergence.py" | tee "$RESULTS_DIR/eval_divergence_output.txt"
echo ""

echo "--- §4.5 Behavioral Divergence (semantic) ---"
python3 "$EVAL_DIR/eval_divergence.py" --semantic | tee "$RESULTS_DIR/eval_divergence_semantic_output.txt"
echo ""

# ----- §4.5 Refined Query -----
echo "--- Refined Query ---"
python3 "$EVAL_DIR/eval_refined_query.py" | tee "$RESULTS_DIR/eval_refined_output.txt"
echo ""

# ----- §4.6 Backend Comparison & Governance Ablation -----
# These require downloading embedding models (BGE-M3, Qwen3) on first run
echo "--- §4.6 Retrieval Backend Comparison ---"
python3 "$EVAL_DIR/eval_retrieval_backends.py" --all | tee "$RESULTS_DIR/eval_retrieval_backends_output.txt"
echo ""

echo "--- §4.6 Governance Ablation ---"
python3 "$EVAL_DIR/eval_governance_ablation.py" | tee "$RESULTS_DIR/eval_governance_ablation_output.txt"
echo ""

# ----- §4.5 Output Divergence (REQUIRES LLM) -----
# Requires: LM Studio with mistral-nemo-instruct-2407 at http://127.0.0.1:1234/v1
#       OR: ANTHROPIC_API_KEY set for Claude Haiku
if [[ "$ALL" == true ]]; then
    echo "--- §4.5 Output Divergence (LLM required) ---"
    echo "  Matrix: 2 LLMs x 2 retrieval modes x 2 temperatures = 8 runs"

    # LLM configs: "label|extra-cli-args"
    LLM_CONFIGS=(
        "gpt54|--backend local --base-url https://api.openai.com/v1 --model gpt-5.4-2026-03-05"
        "haiku45|--backend anthropic --model claude-haiku-4-5-20251001"
    )

    for LLM_CONFIG in "${LLM_CONFIGS[@]}"; do
        LLM_LABEL="${LLM_CONFIG%%|*}"
        LLM_ARGS="${LLM_CONFIG#*|}"

        # Skip LLMs whose keys aren't set
        case "$LLM_LABEL" in
            gpt54)   [[ -z "$OPENAI_API_KEY" ]]    && { echo "  [skip $LLM_LABEL: OPENAI_API_KEY not set]"; continue; } ;;
            haiku45) [[ -z "$ANTHROPIC_API_KEY" ]] && { echo "  [skip $LLM_LABEL: ANTHROPIC_API_KEY not set]"; continue; } ;;
        esac

        for RETR in hash semantic; do
            RETR_ARG=""
            [[ "$RETR" == semantic ]] && RETR_ARG="--semantic"

            for TEMP in 0.0 0.7; do
                TAG="${LLM_LABEL}_${RETR}_t${TEMP/./}"
                echo "  [llm=$LLM_LABEL retrieval=$RETR temp=$TEMP]"
                python3 "$EVAL_DIR/eval_behavioral_divergence.py" $LLM_ARGS $RETR_ARG \
                    --temperature "$TEMP" \
                    --output "$RESULTS_DIR/eval_output_divergence_${TAG}.json" \
                    | tee "$RESULTS_DIR/eval_output_divergence_${TAG}.txt"
                echo ""
            done
        done
    done

    echo "--- Role Divergence (LLM required) ---"
    echo "  Expects: LM Studio with mistral-nemo-instruct-2407 at localhost:1234"
    python3 "$EVAL_DIR/eval_behavioral_divergence.py" $MODEL_ARGS | tee "$RESULTS_DIR/eval_role_divergence_output.txt"
    echo ""
else
    echo "--- Skipping LLM-dependent evals (use --all to include) ---"
    echo "  eval_behavioral_divergence.py  (needs LM Studio: mistral-nemo-instruct-2407 OR OPENAI_API_KEY)"
    echo "  eval_behavioral_divergence.py    (needs LM Studio: mistral-nemo-instruct-2407)"
    echo ""
fi

echo "========================================"
echo "  Evals complete"
echo "  Results in: $RESULTS_DIR/"
echo "========================================"
