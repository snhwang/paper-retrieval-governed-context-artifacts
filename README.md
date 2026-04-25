# Retrieval-Governed Context — Paper Artifacts

Evaluation scripts, frozen corpus, and result files for:

> "Retrieval-Governed Context: Scope-Gated Selection of Instructions and Tools for LLMs and Intelligent Agents"
> Submitted to ACM Transactions on Intelligent Systems and Technology (TIST).
> Preprint link TBD (arXiv once posted).

Uses the BEAR library at [snhwang/bear](https://github.com/snhwang/bear),
pinned to `v0.1.0`.

## Layout

```
evals/                    # evaluation scripts
  eval_retrieval.py         # Pet Sim: F1 / alpha ablation (Table 5)
  eval_retrieval_backends.py# Pet Sim: backend comparison (Table 12)
  eval_governance_ablation.py# Pet Sim: governance ablation panels (Table 12)
  eval_ablation.py          # Pet Sim: alpha weight ablation
  eval_baseline_comparison.py# Pet Sim: CPA comparison, novel+semantic (Tables 7,8)
  eval_scalability.py       # Procedural: token efficiency (Table 9)
  eval_tool_scaling.py      # Procedural: tool scaling + leakage (Table 10)
  eval_tool_composition.py  # Composer validation
  eval_toolbench.py         # ToolBench + MetaTool: retrieval + ablation (Tables 2,3)
  toolbench_setup.py        # Download ToolBench and MetaTool data
  eval_behavioral_divergence.py  # LLM behavioral divergence (demo only)
  stat_utils.py             # Bootstrap CI / statistical helpers

pet_sim/instructions/     # frozen Pet Simulation corpus (8 YAML files)
                          # DO NOT MODIFY — these are exactly what the paper
                          # measured against
results/                  # pre-computed result files referenced in the paper
run_evals.sh              # runner reproducing all deterministic evals
requirements.txt          # all dependencies including datasets for ToolBench
```

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Download external benchmark data (ToolBench + MetaTool)
python evals/toolbench_setup.py

# Run all deterministic evals (no LLM required)
./run_evals.sh

# Run ToolBench + MetaTool evals
python evals/eval_toolbench.py --latex
```

## Evaluation Coverage

### Pet Simulation corpus (frozen, author-constructed)

These evals use `pet_sim/instructions/` and require no LLM or external data.

| Script | Paper table | What it measures |
|--------|-------------|-----------------|
| `eval_retrieval.py` | Table 5 | F1 across query types, alpha ablation |
| `eval_retrieval_backends.py` | Table 12 | Governance ablation across 7 backends |
| `eval_governance_ablation.py` | Table 12 | Full / mandatory-only / no governance |
| `eval_baseline_comparison.py` | Tables 7, 8 | CPA vs BEAR, novel and semantic contexts |
| `eval_scalability.py` | Table 9 | Token efficiency as agent count scales |
| `eval_tool_scaling.py` | Table 10 | Tool precision and cross-domain leakage |

### External benchmarks

| Script | Paper table | Benchmark |
|--------|-------------|-----------|
| `eval_toolbench.py` | Tables 2, 3 | ToolBench (3,225 APIs) + MetaTool (199 tools) |

Run `toolbench_setup.py` first to download data from HuggingFace.

### LLM-dependent (optional)

`eval_behavioral_divergence.py` runs BEAR vs Role vs Static output divergence
across models and temperatures. Requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
in a `.env` file at the repo root. Results are not reported in the paper but
are included for completeness.

```bash
# GPT-5.4 Mini
python evals/eval_behavioral_divergence.py \
  --base-url https://api.openai.com/v1 \
  --model gpt-5.4-mini-2026-03-17 --temperature 0.0

# Claude Haiku
python evals/eval_behavioral_divergence.py \
  --model claude-haiku-4-5-20251001 --temperature 0.0
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
