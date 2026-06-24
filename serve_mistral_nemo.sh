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
#   ./serve_mistral_nemo.sh                    # defaults; auto-detects WSL
#   PORT=8001 ./serve_mistral_nemo.sh          # custom port
#   MAX_MODEL_LEN=4096 ./serve_mistral_nemo.sh # smaller context window
#   EAGER=0 ./serve_mistral_nemo.sh            # force CUDA graphs even on WSL
#   EAGER=1 ./serve_mistral_nemo.sh            # force eager even on bare Linux
#
# The script auto-handles known issues:
#   - WSL detection -> --enforce-eager (avoids CUDA graph capture segfault)
#   - HF cache permission check -> auto-fix via chown if writable, else instruct
#   - HF_TOKEN check -> warn if missing (non-fatal but slower downloads)
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

# --- Auto-detect WSL and default to eager mode ----------------------------
# vLLM's CUDA graph capture (Profiling CUDA graph memory step) segfaults on
# many WSL configurations during reshape_and_cache_flash. --enforce-eager
# disables graph capture; runtime is ~10-30% slower but stable.
if [[ -z "${EAGER:-}" ]]; then
    if grep -qi microsoft /proc/version 2>/dev/null; then
        EAGER=1
    else
        EAGER=0
    fi
fi

EXTRA_ARGS=()
[[ "$EAGER" == "1" ]] && EXTRA_ARGS+=(--enforce-eager)

# --- WSL: disable ALL custom CUDA kernels ---------------------------------
# vLLM 0.20 ships custom CUDA kernels for rms_norm, rotary_embedding,
# silu_and_mul, fused_add_rms_norm, etc. On several WSL2 + CUDA driver
# combinations these kernels segfault inside the bound C++ function
# immediately after the model finishes loading, even with --enforce-eager.
# Peeling them off one at a time becomes a whack-a-mole: fixing rms_norm
# just moves the crash to rotary_embedding, etc.
#
# The robust fix is to disable the entire custom-op registry and fall back
# to the native PyTorch implementation of every CustomOp. Each affected op
# has a tested native fallback. Runtime cost is typically 10-30%.
#
# Override with NATIVE_OPS=0 if a future driver/vLLM release fixes the
# underlying kernel issue.
if [[ -z "${NATIVE_OPS:-}" ]]; then
    if grep -qi microsoft /proc/version 2>/dev/null; then
        NATIVE_OPS=1
    else
        NATIVE_OPS=0
    fi
fi
if [[ "$NATIVE_OPS" == "1" ]]; then
    EXTRA_ARGS+=(--compilation-config '{"custom_ops": ["none"]}')
fi

# --- Pre-flight: vLLM installed -------------------------------------------
if ! python -c "import vllm" 2>/dev/null; then
    echo "ERROR: vLLM is not installed."
    echo ""
    echo "  pip install vllm"
    echo ""
    echo "vLLM requires Linux/CUDA. Installation guide:"
    echo "  https://docs.vllm.ai/en/latest/getting_started/installation.html"
    exit 1
fi

# --- Pre-flight: HF cache writable ----------------------------------------
# Permission errors here mean the cache was created by a different user
# (typically a previous sudo invocation). Fix or instruct.
HF_CACHE="${HF_HOME:-$HOME/.cache/huggingface}"
if [[ -d "$HF_CACHE" ]] && [[ ! -w "$HF_CACHE" || $(find "$HF_CACHE" -not -writable -print -quit 2>/dev/null) ]]; then
    if [[ "$EUID" -eq 0 ]]; then
        echo "Fixing $HF_CACHE ownership..."
        chown -R "$(logname 2>/dev/null || echo "$SUDO_USER")" "$HF_CACHE"
    elif sudo -n true 2>/dev/null; then
        echo "Fixing $HF_CACHE ownership (passwordless sudo available)..."
        sudo chown -R "$(whoami)" "$HF_CACHE"
    else
        echo "WARNING: $HF_CACHE has files not writable by $(whoami)."
        echo "         vLLM will continue but with cache write failures."
        echo "         Fix with:  sudo chown -R \"\$(whoami)\" \"$HF_CACHE\""
        echo ""
    fi
fi

# --- Pre-flight: HF_TOKEN -------------------------------------------------
# Anonymous downloads from HF Hub are rate-limited. For first-run download
# of a 24GB model, this matters.
if [[ -z "${HF_TOKEN:-}" ]] && [[ ! -d "$HF_CACHE/hub/models--mistralai--Mistral-Nemo-Instruct-2407" ]]; then
    echo "NOTE: HF_TOKEN not set and Mistral-Nemo not in cache."
    echo "      First-run download (~24GB) will be rate-limited."
    echo "      To skip the rate limit: export HF_TOKEN=hf_xxxxxxx"
    echo "      Get a token: https://huggingface.co/settings/tokens"
    echo ""
fi

echo "========================================"
echo "  vLLM: serving paper Table 5 model"
echo "========================================"
echo "  Model:    $MODEL"
echo "  Port:     $PORT"
echo "  Endpoint: http://127.0.0.1:$PORT/v1"
echo "  Context:  $MAX_MODEL_LEN tokens"
echo "  GPU mem:  $GPU_MEM_UTIL"
if [[ "$EAGER" == "1" ]]; then
    if grep -qi microsoft /proc/version 2>/dev/null; then
        echo "  Mode:     eager (CUDA graphs disabled, WSL detected)"
    else
        echo "  Mode:     eager (CUDA graphs disabled)"
    fi
fi
if [[ "$NATIVE_OPS" == "1" ]]; then
    echo "  CustomOp: all native (vLLM custom CUDA kernels disabled for WSL)"
fi
echo ""
echo "vLLM will load the model (multi-minute first time, faster subsequently)."
echo "This script will print a READY banner when /v1/models responds."
echo "Stop with Ctrl+C."
echo "========================================"
echo ""

# Background readiness poller. Prints a banner once /v1/models responds, so
# you don't have to scrape vLLM's own log for "Application startup complete".
# Self-terminates after 30 min if the model never loads.
(
    sleep 10
    for _ in $(seq 1 360); do  # 360 * 5s = 30 min cap
        if curl -sf -m 2 "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
            echo ""
            echo "========================================"
            echo "  vLLM READY at http://127.0.0.1:$PORT/v1"
            echo "  Run in another shell:"
            echo "    ./run_evals.sh --all --base-url http://127.0.0.1:$PORT/v1"
            echo "========================================"
            echo ""
            exit 0
        fi
        sleep 5
    done
) &
POLLER_PID=$!
trap "kill $POLLER_PID 2>/dev/null" EXIT

# Tool-calling support is REQUIRED by the ReAct end-to-end ToolBench eval
# (eval_toolbench_react.py), which sends OpenAI-compatible tools= and
# tool_choice=auto. Without these flags, vLLM silently drops the tool block
# and the eval scores 0 across the board.
vllm serve "$MODEL" \
    --port "$PORT" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEM_UTIL" \
    --enable-auto-tool-choice \
    --tool-call-parser mistral \
    "${EXTRA_ARGS[@]}"
