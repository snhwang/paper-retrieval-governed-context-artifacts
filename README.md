# Retrieval-Governed Context — Paper Artifacts

**Provisional Patent Pending (filed April 15, 2026)** | Copyright (c) 2024-2026 The Pennsylvania State University. All rights reserved.
Inventor: Scott N. Hwang

Licensed under the [Open Core Ventures Source Available License (OCVSAL) v1.0](LICENSE). Production use requires a commercial agreement. For commercial licensing, contact the Penn State Office of Technology Transfer at ottinfo@psu.edu.

Evaluation scripts, frozen corpus, and result files for:

> "Retrieval-Governed Context: Scope-Gated Selection of Instructions and Tools for LLMs and Intelligent Agents"
> Submitted to ACM Transactions on Intelligent Systems and Technology (TIST).

Uses the BEAR library at [snhwang/bear](https://github.com/snhwang/bear),
pinned to `v0.1.0`.

## Layout

```
evals/                    # evaluation scripts
  eval_retrieval.py         # Pet Sim: F1 / alpha ablation (Table 6)
  eval_retrieval_backends.py# Pet Sim: backend comparison (Table 12)
  eval_governance_ablation.py# Pet Sim: governance ablation panels (Table 12)
  eval_ablation.py          # Pet Sim: alpha weight ablation
  eval_baseline_comparison.py# Pet Sim: CPA semantic recall + token efficiency (Tables 10, 11)
  eval_scalability.py       # Procedural: token efficiency (Table 9)
  eval_tool_scaling.py      # Procedural: tool scaling + leakage (Tables 7, 8)
  eval_tool_composition.py  # Composer validation
  eval_toolbench.py         # ToolBench retrieval + MetaTool variants (Tables 2, 3, 4)
  eval_toolbench_e2e.py     # End-to-end ToolBench: retrieval -> LLM (Table 5)
  toolbench_setup.py        # Download ToolBench and MetaTool data
  stat_utils.py             # Bootstrap CI / statistical helpers

pet_sim/instructions/     # frozen Pet Simulation corpus (8 YAML files)
                          # DO NOT MODIFY — these are exactly what the paper
                          # measured against
results/                  # pre-computed result files referenced in the paper
run_evals.sh              # runner reproducing all paper tables
serve_mistral_nemo.sh     # vLLM server matching paper Table 5 deployment
requirements.txt          # all dependencies including datasets for ToolBench
```

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download external benchmark data (ToolBench + MetaTool)
python evals/toolbench_setup.py

# Reproduce all deterministic paper tables (Tables 2, 3, 4, 6-12)
./run_evals.sh

# Add Table 5 (end-to-end ToolBench with LLM).
# Paper-exact reproduction: Mistral-Nemo-Instruct-2407 (12B) via vLLM.
# In one shell, start the server (requires CUDA GPU with ~24GB VRAM):
./serve_mistral_nemo.sh
# In another shell, run the eval against it:
./run_evals.sh --all --base-url http://127.0.0.1:8000/v1
```

Any OpenAI-compatible endpoint works (vLLM, LM Studio, Ollama). If you don't
need paper-exact reproduction, point `--base-url` at whatever you have running.
LM Studio's default endpoint (`http://127.0.0.1:1234/v1`) works without
overriding `--base-url`.

## Evaluation Coverage

### Pet Simulation corpus (frozen, author-constructed)

These evals use `pet_sim/instructions/` and require no LLM or external data.

| Script | Paper table | What it measures |
|--------|-------------|-----------------|
| `eval_retrieval.py` | Table 6 | F1 across query types, alpha ablation |
| `eval_retrieval_backends.py` | Table 12 | Governance ablation across 7 backends |
| `eval_governance_ablation.py` | Table 12 | Full / mandatory-only / no governance |
| `eval_baseline_comparison.py` | Tables 10, 11 | CPA vs BEAR semantic recall + Pet Sim token efficiency |
| `eval_scalability.py` | Table 9 | Token efficiency as agent count scales |
| `eval_tool_scaling.py` | Tables 7, 8 | Tool retrieval scaling + token savings |

### External benchmarks

| Script | Paper table | Benchmark |
|--------|-------------|-----------|
| `eval_toolbench.py` | Tables 2, 3, 4 | ToolBench retrieval + MetaTool + MetaTool-with-tags |
| `eval_toolbench_e2e.py` | Table 5 | End-to-end ToolBench: retrieval → LLM tool selection (LLM required) |

Run `toolbench_setup.py` first to download data from HuggingFace.

`eval_toolbench_e2e.py` requires an OpenAI-compatible LLM endpoint. The paper
used `mistralai/Mistral-Nemo-Instruct-2407` (12B) served via vLLM. Any
compatible endpoint works (LM Studio, vLLM, Ollama). Pass `--model` and
`--base-url` to override the defaults.

## Running individual evals

`./run_evals.sh` invokes every script with the flags used to produce the
paper's result files. To reproduce a single table or experiment, run that
script directly:

```bash
# Pet Simulation (deterministic, no LLM)
python evals/eval_retrieval.py                   # Table 6 (lexical)
python evals/eval_retrieval.py --semantic        # Table 6 (semantic)
python evals/eval_retrieval_backends.py --all    # Table 12 (backend comparison)
python evals/eval_governance_ablation.py         # Table 12 (governance ablation)
python evals/eval_baseline_comparison.py         # Tables 10, 11
python evals/eval_scalability.py                 # Table 9
python evals/eval_tool_scaling.py                # Tables 7, 8
python evals/eval_tool_composition.py            # Composer validation
python evals/eval_ablation.py                    # Parameter sensitivity (lexical)
python evals/eval_ablation.py --semantic         # Parameter sensitivity (semantic)

# External benchmarks (requires toolbench_setup.py first)
python evals/eval_toolbench.py --latex           # Tables 2, 3, 4
python evals/eval_toolbench_e2e.py \              # Table 5 (LLM required)
    --model mistralai/Mistral-Nemo-Instruct-2407
```

## Embedding Models

The following models download automatically on first use via HuggingFace:

- `BAAI/bge-base-en-v1.5` (768-dim, primary)
- `BAAI/bge-m3` (1024-dim)
- `Qwen/Qwen3-Embedding-0.6B` (1024-dim)
- `Qwen/Qwen3-Embedding-4B` (2560-dim)

## Corpus Integrity

The `pet_sim/instructions/` directory is a frozen snapshot of the corpus
used to generate all Pet Simulation results in the paper. Do not modify
these files — doing so will produce different numerical results. The
bear-dev repo may contain a more recent version of the instructions for
the live simulation; the two are intentionally kept separate.

## BEAR Version

Pinned to bear `v0.1.0`. Bumping the version will likely change numerical
results. Update the pin in `requirements.txt` and re-run the full suite
before comparing to published numbers.
