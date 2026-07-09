#!/usr/bin/env python3
"""
Serve the LLM for the Evolutionary Ecosystem simulation using vLLM.

Uses google/gemma-4-12B-it, -E4B, or 31B via Docker.
Exposes an OpenAI-compatible endpoint on the configured port.

NOTE: The 12b and e2b models have been tested (both serve and handle tool
calls). The other MODELS entries (e4b, 31b) are provided for convenience but
are unverified.

Prerequisites (to run on another machine):
  - Docker WITH NVIDIA GPU support (the command uses --gpus all). Plain Docker
    is not enough; install the NVIDIA Container Toolkit and confirm `nvidia-smi`
    works. https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/
  - An NVIDIA GPU + recent driver. The default image targets CUDA 13; for an
    older driver use the CUDA 12.9 image (see the override below). Needs enough
    VRAM to fit the 12B at the chosen --gpu-memory-utilization.
  - A Hugging Face token WITH Gemma access accepted. gemma-4-* models are gated:
    put HF_TOKEN in a .env next to this script AND accept the license on the
    model's HF page with that account, or the download 403s.
  - Python 3 to run this launcher (stdlib only, no pip deps).
  - First run pulls a multi-GB image and downloads ~24GB of weights into
    ~/.cache/huggingface; the configured port (default 8355) must be free.

Usage:
    python serve_llm.py                    # default port 8355
    python serve_llm.py --port 8356        # custom port
    python serve_llm.py --model 12b        # use 12B model

Override the vLLM image (e.g. for a CUDA 12.9 host):
    VLLM_SPARK_IMAGE=vllm/vllm-openai:gemma4-unified-cu129 python serve_llm.py

Then start the sim pointing at this server:
    python -m examples.evolutionary_ecosystem.server.app \\
        --base-url http://localhost:8355/v1 \\
        --model gemma-4-12b
"""

import argparse
import os
import subprocess
from pathlib import Path

# Model options: (hf_id, served_name)
MODELS = {
    "e2b":  ("google/gemma-4-E2B-it",  "gemma-4-e2b"),
    "e4b":  ("google/gemma-4-E4B-it",  "gemma-4-e4b"),
    "12b":  ("google/gemma-4-12B-it",  "gemma-4-12b"),
    "31b":  ("google/gemma-4-31B-it",  "gemma-4-31b"),
}

DEFAULT_PORT       = 8355
DEFAULT_MODEL      = "12b"
CONTAINER_PORT     = 8000
CONTAINER_NAME     = "vllm_bear_llm"
# Pinned vLLM image with Gemma 4 support. The gemma4_unified (encoder-free)
# architecture used by gemma-4-12B-it has NOT shipped in a stable vLLM release
# yet (see vllm-project/vllm#44429), so a stable vX.Y.Z tag will fail with
# "Transformers does not recognize this architecture". This nightly-based tag
# is the one vLLM publishes for it. Default targets CUDA 13; for a CUDA 12.9
# host use vllm/vllm-openai:gemma4-unified-cu129 via VLLM_SPARK_IMAGE.
# Ref: https://recipes.vllm.ai/Google/gemma-4-12B-it
DEFAULT_VLLM_IMAGE = "vllm/vllm-openai:gemma4-unified"


def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


def main():
    parser = argparse.ArgumentParser(description="Serve LLM for BEAR evolutionary ecosystem")
    parser.add_argument("--port",  type=int, default=DEFAULT_PORT)
    parser.add_argument("--model", choices=list(MODELS), default=DEFAULT_MODEL,
                        help="Model size: 12b, 27b, or 31b (default: 12b)")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.5,
                        help="Fraction of GPU memory vLLM will reserve (default: 0.5)")
    parser.add_argument("--max-model-len", type=int, default=32768,
                        help="Max context length in tokens (default: 32768)")
    args = parser.parse_args()

    load_env()

    image     = os.environ.get("VLLM_SPARK_IMAGE", DEFAULT_VLLM_IMAGE)
    hf_token  = os.environ.get("HF_TOKEN", "")
    if not hf_token or hf_token == "your_token_here":
        print("Error: Set HF_TOKEN in .env file or environment")
        return 1

    hf_cache  = os.path.expanduser("~/.cache/huggingface")
    model_hf, model_name = MODELS[args.model]
    gpu_util = str(args.gpu_memory_utilization)
    max_len = str(args.max_model_len)

    cmd = [
        "docker", "run",
        "--name", CONTAINER_NAME,
        "--rm", "-it",
        "--gpus", "all",
        "--ipc", "host",
        "-p", f"{args.port}:{CONTAINER_PORT}",
        "-e", f"HF_TOKEN={hf_token}",
        "-v", f"{hf_cache}:/root/.cache/huggingface/",
        image,
        model_hf,
        "--served-model-name", model_name,
        "--host", "0.0.0.0",
        "--port", str(CONTAINER_PORT),
        "--dtype", "auto",
        "--trust-remote-code",
        "--gpu-memory-utilization", gpu_util,
        "--max-model-len", max_len,
        "--enable-chunked-prefill",
        # Tool/function calling. Without these, any request with
        # tool_choice="auto" is rejected with HTTP 400
        # ("auto" tool choice requires --enable-auto-tool-choice ...).
        # gemma4 uses a custom (non-JSON) tool-call protocol, so it needs its
        # dedicated parser and chat template (bundled in the image at
        # /vllm-workspace/examples/). See recipes.vllm.ai/Google/gemma-4-12B-it
        "--enable-auto-tool-choice",
        "--tool-call-parser", "gemma4",
        "--chat-template", "/vllm-workspace/examples/tool_chat_template_gemma4.jinja",
    ]

    print(f"Starting {model_hf}")
    print(f"Server: http://localhost:{args.port}/v1")
    print(f"Model name for API calls: {model_name}")
    print(f"Context: {int(max_len)//1024}k tokens")
    print("-" * 60)
    print(f"Then run the sim with:")
    print(f"  python -m examples.evolutionary_ecosystem.server.app \\")
    print(f"      --base-url http://localhost:{args.port}/v1 \\")
    print(f"      --model {model_name}")
    print("-" * 60)

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nShutting down...")
    except subprocess.CalledProcessError as e:
        # str(e) includes the full command list (with -e HF_TOKEN=...); redact
        # the token so a failed run never prints it to the terminal or logs.
        msg = str(e).replace(hf_token, "***") if hf_token else str(e)
        print(f"Error: {msg}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
