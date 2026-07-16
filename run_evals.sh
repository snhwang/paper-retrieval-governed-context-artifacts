#!/usr/bin/env bash
# =============================================================================
# run_evals.sh — Retrieval-Governed Context (BEAR paper)
#
# Reproduces every numeric table in the paper. The default run is fully
# deterministic and requires no LLM. Passing --all also runs the end-to-end
# tool-selection experiments (Tables 7 and 8), which require an
# OpenAI-compatible LLM endpoint.
#
# TABLE COVERAGE (see README.md for the full paper-to-script mapping):
#
#   Deterministic (default run):
#     Table 3     ToolBench retrieval                    eval_toolbench.py
#     Table 4     LLM-inferred categories (3 variants)   eval_toolbench_inferred_categories.py
#                                                        eval_toolbench_multitag_categories.py
#                                                        eval_toolbench_top5_categories.py
#     Table 5     MetaTool retrieval                     eval_toolbench.py (MetaTool mode)
#     Table 6     MetaTool + LLM-generated tags          eval_toolbench.py (with pre-generated tags)
#     Table 9     Pet Sim retrieval                      eval_retrieval.py
#     Tables 10,11 Tool scaling + token savings          eval_tool_scaling.py
#     Table 12    Token efficiency (10-500 agents)       eval_scalability.py
#     Tables 13,14 CPA vs BEAR                            eval_baseline_comparison.py
#     Table 15    Governance ablation                    eval_governance_ablation.py
#     Table 16    Decomposed governance ablation         eval_governance_decomposed.py
#     Table 17    Alpha weight sweep                     eval_alpha_sweep.py
#
#   LLM-required (add --all):
#     Table 7     End-to-end ToolBench                   eval_toolbench_e2e.py
#     Table 8     End-to-end ToolBench (ReAct)           eval_toolbench_react.py
#
# LLM ENDPOINT:
#   The paper used Mistral-Nemo-Instruct-2407 (12B) at Q4_0 quantization,
#   served by Ollama with OLLAMA_CONTEXT_LENGTH=131072 (the monolithic baseline
#   injects all 3,225 schemas, ~82k tokens):
#       ollama pull mistral-nemo
#       OLLAMA_CONTEXT_LENGTH=131072 OLLAMA_MAX_LOADED_MODELS=1 ollama serve
#       ./run_evals.sh --all --base-url http://127.0.0.1:11434/v1 \
#           --model mistral-nemo
#   Any OpenAI-compatible endpoint with structured-output (response_format
#   json_schema) support works. Override with --model and --base-url.
#   serve_mistral_nemo.sh serves the bf16 checkpoint via vLLM instead; it is
#   NOT the deployment behind the published numbers.
#
# EMBEDDING MODELS (downloaded automatically on first use):
#   BAAI/bge-base-en-v1.5 (primary), BAAI/bge-m3, Qwen/Qwen3-Embedding-0.6B,
#   Qwen/Qwen3-Embedding-4B
#
# USAGE:
#   ./run_evals.sh                                    # deterministic tables only
#   ./run_evals.sh --all                              # + LLM tables (7, 8)
#   ./run_evals.sh --all --model my-model
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
echo "  Retrieval-Governed Context (paper)"
echo "========================================"
echo ""

# =========================
# Pet Simulation corpus
# =========================

echo "--- Table 9: Pet Sim retrieval (lexical) ---"
python3 "$EVAL_DIR/eval_retrieval.py" | tee "$RESULTS_DIR/eval_retrieval_output.txt"
echo ""

echo "--- Table 9: Pet Sim retrieval (semantic) ---"
python3 "$EVAL_DIR/eval_retrieval.py" --semantic | tee "$RESULTS_DIR/eval_retrieval_semantic_output.txt"
echo ""

echo "--- Retrieval backend comparison (BGE-M3, Qwen3) ---"
python3 "$EVAL_DIR/eval_retrieval_backends.py" --all | tee "$RESULTS_DIR/eval_retrieval_backends_output.txt"
echo ""

echo "--- Table 15: Governance ablation ---"
python3 "$EVAL_DIR/eval_governance_ablation.py" | tee "$RESULTS_DIR/eval_governance_ablation_output.txt"
echo ""

echo "--- Table 16: Decomposed governance ablation (5 backends + ITR) ---"
python3 "$EVAL_DIR/eval_governance_decomposed.py" | tee "$RESULTS_DIR/eval_governance_decomposed_output.txt"
echo ""

echo "--- Table 17: Alpha weight sweep ---"
python3 "$EVAL_DIR/eval_alpha_sweep.py" | tee "$RESULTS_DIR/eval_alpha_sweep_output.txt"
echo ""

echo "--- Tables 13, 14: BEAR vs CPA baseline ---"
python3 "$EVAL_DIR/eval_baseline_comparison.py" | tee "$RESULTS_DIR/eval_baseline_output.txt"
echo ""

echo "--- Table 12: Scalability (10-500 agents) ---"
python3 "$EVAL_DIR/eval_scalability.py" | tee "$RESULTS_DIR/eval_scalability_output.txt"
echo ""

echo "--- Tables 10, 11: Tool scaling + token savings ---"
python3 "$EVAL_DIR/eval_tool_scaling.py" | tee "$RESULTS_DIR/eval_tool_scaling_output.txt"
echo ""

echo "--- Tool composition (Composer validation) ---"
python3 "$EVAL_DIR/eval_tool_composition.py" | tee "$RESULTS_DIR/eval_tool_composition_output.txt"
echo ""

echo "--- Parameter sensitivity (alpha, theta, K; lexical) ---"
python3 "$EVAL_DIR/eval_ablation.py" | tee "$RESULTS_DIR/eval_ablation_output.txt"
echo ""

echo "--- Parameter sensitivity (semantic) ---"
python3 "$EVAL_DIR/eval_ablation.py" --semantic | tee "$RESULTS_DIR/eval_ablation_semantic_output.txt"
echo ""

# =========================
# ToolBench + MetaTool retrieval (deterministic; needs toolbench_setup.py first)
# =========================

echo "--- Tables 3, 5, 6: ToolBench + MetaTool retrieval ---"
python3 "$EVAL_DIR/eval_toolbench.py" --latex | tee "$RESULTS_DIR/eval_toolbench_output.txt"
echo ""

echo "--- Table 4: ToolBench with LLM-inferred categories (top-1) ---"
python3 "$EVAL_DIR/eval_toolbench_inferred_categories.py" | tee "$RESULTS_DIR/eval_toolbench_inferred_categories_output.txt"
echo ""

echo "--- Table 4: ToolBench with LLM-inferred categories (multi-tag) ---"
python3 "$EVAL_DIR/eval_toolbench_multitag_categories.py" | tee "$RESULTS_DIR/eval_toolbench_multitag_categories_output.txt"
echo ""

echo "--- Table 4: ToolBench with LLM-inferred categories (top-5) ---"
python3 "$EVAL_DIR/eval_toolbench_top5_categories.py" | tee "$RESULTS_DIR/eval_toolbench_top5_categories_output.txt"
echo ""


# =========================
# End-to-end tool selection (REQUIRES LLM)
# =========================

if [[ "$ALL" == true ]]; then
    echo "--- Table 7: End-to-end ToolBench (single-turn, LLM required) ---"
    python3 "$EVAL_DIR/eval_toolbench_e2e.py" $E2E_ARGS \
        | tee "$RESULTS_DIR/eval_toolbench_e2e_output.txt" \
        || echo "  [e2e ToolBench failed: see error above; continuing]"
    echo ""

    echo "--- Table 8: End-to-end ToolBench (ReAct, LLM required) ---"
    python3 "$EVAL_DIR/eval_toolbench_react.py" $E2E_ARGS \
        | tee "$RESULTS_DIR/eval_toolbench_react_output.txt" \
        || echo "  [e2e ReAct ToolBench failed: see error above; continuing]"
    echo ""
else
    echo "--- Skipping end-to-end LLM experiments (use --all to include) ---"
    echo "  Table 7: eval_toolbench_e2e.py     (needs OpenAI-compatible endpoint)"
    echo "  Table 8: eval_toolbench_react.py   (needs OpenAI-compatible endpoint)"
    echo ""
fi

echo "========================================"
echo "  Evals complete"
echo "  Results in: $RESULTS_DIR/"
echo "========================================"
