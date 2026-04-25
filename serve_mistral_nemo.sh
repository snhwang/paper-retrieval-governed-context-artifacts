#!/usr/bin/env bash
# =============================================================================
# serve_mistral_nemo.sh — vLLM server for paper Table 5
#
# Serves mistralai/Mistral-Nemo-Instruct-2407 (12B) on an OpenAI-compatible
# chat-completions endpoint. This matches the deployment used for the paper's
# end-to-end ToolBench experiment (Table 5).
#
# Prerequisites:
#   - CUDA GPU with ~24GB VRAM at fp16 (less with quantization; see vLLM docs)
#   - pip install vllm  (Linux/CUDA only; see https://docs.vllm.ai)
#   - First run downloads ~24GB from Hugging Face
#
# Usage:
#   ./serve_mistral_nemo.sh                    # defaults: port 8000
#   PORT=8001 ./serve_mistral_nemo.sh          # custom port
#   MAX_MODEL_LEN=4096 ./serve_mistral_nemo.sh # smaller context window
#
# Once the server is ready, in another shell:
#   ./run_evals.sh --all --base-url http://127.0.0.1:8000/v1
#
# To stop: Ctrl+C
# =============================================================================

set -e

MODEL="${MODEL:-mistralai/Mistral-Nemo-Instruct-2407}"
PORT="${PORT:-8000}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.85}"

if ! python -c "import vllm" 2>/dev/null; then
    echo "ERROR: vLLM is not installed."
    echo ""
    echo "  pip install vllm"
    echo ""
    echo "vLLM requires Linux/CUDA. Installation guide:"
    echo "  https://docs.vllm.ai/en/latest/getting_started/installation.html"
    exit 1
fi

echo "========================================"
echo "  vLLM: serving paper Table 5 model"
echo "========================================"
echo "  Model:    $MODEL"
echo "  Port:     $PORT"
echo "  Endpoint: http://127.0.0.1:$PORT/v1"
echo "  Context:  $MAX_MODEL_LEN tokens"
echo "  GPU mem:  $GPU_MEM_UTIL"
echo ""
echo "Once the server prints 'Application startup complete', run in another shell:"
echo "  ./run_evals.sh --all --base-url http://127.0.0.1:$PORT/v1"
echo ""
echo "Stop with Ctrl+C."
echo "========================================"
echo ""

exec vllm serve "$MODEL" \
    --port "$PORT" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEM_UTIL"
