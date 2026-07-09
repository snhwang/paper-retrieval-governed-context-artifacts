# Retrieval-Governed Context — Paper Artifacts

**Provisional Patent Pending (filed April 15, 2026)** | Copyright (c) 2024-2026 The Pennsylvania State University. All rights reserved.
Inventor: Scott N. Hwang

Licensed under the [Open Core Ventures Source Available License (OCVSAL) v1.0](LICENSE). Production use requires a commercial agreement. For commercial licensing, contact the Penn State Office of Technology Transfer at ottinfo@psu.edu.

Evaluation scripts, frozen corpus, and result files for:

> "Retrieval-Governed Context: Scope-Gated Selection of Instructions and Tools for LLMs and Intelligent Agents"

Uses the BEAR library at [snhwang/bear](https://github.com/snhwang/bear), pinned to `v0.1.10`.

## Quick Start

Requires [uv](https://docs.astral.sh/uv/).

### First-time setup (run once)

Creates the environment, installs the pinned dependencies, and downloads the
external benchmark data. Note that `uv venv` does not install `pip` into the
environment, so use `uv pip` for installs (plain `pip` would resolve to a system
interpreter and install outside the venv).

```bash
uv venv                                 # create .venv
source .venv/bin/activate
uv pip install -r requirements.txt      # pinned dependency set
python evals/toolbench_setup.py         # download ToolBench + MetaTool data
```

#### Script permissions

The shell scripts (`run_evals.sh`, `serve_mistral_nemo.sh`, `evals/*.sh`) need
the executable bit to be invoked as `./run_evals.sh`. It is often lost on a fresh
clone, on a Windows checkout, or under WSL when the repository lives on a Windows
drive (`/mnt/c/...`). If you see `Permission denied`, either set it once:

```bash
chmod +x run_evals.sh serve_mistral_nemo.sh evals/*.sh
```

or invoke the scripts through the interpreter, which needs no permission change:

```bash
bash run_evals.sh
bash serve_mistral_nemo.sh
```

### Every session after that

The setup steps above do not need to be repeated. Just activate the environment
and run:

```bash
source .venv/bin/activate

# Reproduce all deterministic paper tables
./run_evals.sh

# Add end-to-end LLM experiments (Tables 7, 8).
# Paper-exact reproduction: mistralai/Mistral-Nemo-Instruct-2407 (12B) via vLLM.
# In one shell, start the server (requires CUDA GPU with ~24GB VRAM):
./serve_mistral_nemo.sh
# In another shell, run the full suite against it:
./run_evals.sh --all --base-url http://127.0.0.1:8000/v1
```

Any OpenAI-compatible endpoint works (vLLM, LM Studio, Ollama). If you do not need paper-exact reproduction, point `--base-url` at whatever endpoint you have running. LM Studio's default endpoint (`http://127.0.0.1:1234/v1`) works without overriding `--base-url`.

## Environment Setup

Most paper tables are deterministic and require **no API keys**. Keys are only
needed to (a) regenerate the LLM-inferred metadata (the ToolBench
inferred-category and MetaTool generated-tag conditions), or (b) download the
model weights for the end-to-end experiments.

Copy the template and fill in only the values you need:

```bash
cp .env.example .env
```

Both the Python evals (via `python-dotenv`) and `serve_mistral_nemo.sh` auto-load
a `.env` from the repo root, so exporting variables in your shell is optional.
Variables already present in the environment take precedence over the file, so a
one-off `HF_TOKEN=... bash serve_mistral_nemo.sh` still overrides it. The `.env`
file is git-ignored — never commit real keys.

### Credentials

| Variable | Needed for | Notes |
|:--|:--|:--|
| `ANTHROPIC_API_KEY` | Regenerating the LLM-inferred metadata | Default provider for `metatool_generate_*.py` and the `*_categories.py` evals. |
| `OPENAI_API_KEY` | Same scripts with an OpenAI `--model` | Also used as a fallback by the `metatool_generate_*` scripts. |
| `OLLAMA_API_KEY` | Metadata generation against a non-OpenAI, OpenAI-compatible host | Only for the `metatool_generate_*` scripts. |
| `HF_TOKEN` | Downloading the Mistral-Nemo weights | Optional, but anonymous downloads of the ~24GB checkpoint are heavily rate-limited. |

The end-to-end evals (`eval_toolbench_e2e.py`, `eval_toolbench_react.py`) do not
read a key from the environment; they talk to an OpenAI-compatible endpoint
selected with `--base-url` / `--model`.

### LLM server settings

`serve_mistral_nemo.sh` reads these from `.env` (or the environment):

| Variable | Default | Notes |
|:--|:--|:--|
| `MODEL` | `mistralai/Mistral-Nemo-Instruct-2407` | The served model. Note the eval's `--model` must match this **exactly**, including case. |
| `HOST` | `0.0.0.0` | Binds all interfaces so a remote eval can reach the server. Set `127.0.0.1` to restrict to localhost. |
| `PORT` | `8355` | |
| `MAX_MODEL_LEN` | `32768` | The monolithic baseline packs ~200 tool schemas into a single prompt. Do not lower below ~28k or that condition breaks. |
| `GPU_MEM_UTIL` | `0.4` | Fraction of total VRAM vLLM reserves **up front**, independent of model size. |

### Recommended: run the LLM server on a separate machine

The evals load embedding models onto the GPU for retrieval, while vLLM holds its
weights plus a pre-allocated KV cache on the same card. On a single GPU these
compete, and the largest embedder (Qwen3-4B, ~8GB) can exhaust VRAM. Under WSL
that does **not** raise an error — the driver silently spills to host memory over
PCIe and throughput collapses to a few tokens per second.

Serving the LLM from a second machine removes the contention entirely:

```bash
# On the GPU box serving the LLM
#   .env:  HF_TOKEN=hf_...   HOST=0.0.0.0   GPU_MEM_UTIL=0.85
bash serve_mistral_nemo.sh

# On the machine running the evals — its GPU is now free for the embedders
python evals/eval_toolbench_e2e.py --all \
    --base-url http://<server-ip>:8355/v1 \
    --model mistralai/Mistral-Nemo-Instruct-2407
```

Network latency (~1–5 ms) is negligible next to LLM inference (100–500 ms per
call). If you must share one GPU, lower `GPU_MEM_UTIL` until the embedders fit;
a 12B model at a 32k context needs roughly `0.4` on a 96GB card. Verify the
server is reachable and get the exact model id with:

```bash
curl -s http://<server-ip>:8355/v1/models | python -m json.tool
```

## Table-to-Script Mapping

Every numeric table in the paper is produced by a Python script in `evals/`. Static tables (schema cheatsheet, provenance rubric, summary comparison) and figures (pipeline diagram, YAML example) have no backing script.

| Paper | Label | Backing script(s) | LLM required |
|:--|:--|:--|:--:|
| Figure 1 | `fig:instructions` | *(diagram)* | — |
| Table 1 | `tab:schema-cheatsheet` | *(static)* | — |
| Figure 2 | `fig:pipeline` | *(diagram)* | — |
| Table 2 | `tab:provenance` | *(static)* | — |
| Table 3 | `tab:toolbench-results` | `eval_toolbench.py` | no |
| Table 4 | `tab:toolbench-inferred` | `eval_toolbench_inferred_categories.py`, `eval_toolbench_multitag_categories.py`, `eval_toolbench_top5_categories.py` (data pre-generated via Anthropic API) | no (post-generation) |
| Table 5 | `tab:metatool-results` | `eval_toolbench.py --metatool` | no |
| Table 6 | `tab:metatool-tags-results` | `eval_toolbench.py` with tag JSON generated by `metatool_generate_tags.py`, `metatool_generate_query_tags.py`, `metatool_generate_query_tags_top5.py` (Anthropic API for generation, retrieval eval is deterministic) | no (post-generation) |
| Table 7 | `tab:e2e` | `eval_toolbench_e2e.py` | yes |
| Table 8 | `tab:e2e-react` | `eval_toolbench_react.py` | yes |
| Table 9 | `tab:retrieval` | `eval_retrieval.py` | no |
| Table 10 | `tab:tool-scaling` | `eval_tool_scaling.py` | no |
| Table 11 | `tab:token-savings` | `eval_tool_scaling.py` (same run) | no |
| Table 12 | `tab:token-efficiency` | `eval_scalability.py` | no |
| Table 13 | `tab:semantic-advantage` | `eval_baseline_comparison.py --semantic` | no |
| Table 14 | `tab:token-compare` | `eval_baseline_comparison.py` | no |
| Table 15 | `tab:governance-ablation` | `eval_governance_ablation.py` | no |
| Table 16 | `tab:decomposed-ablation` | `eval_governance_decomposed.py` | no |
| Table 17 | `tab:alpha-sweep` | `eval_alpha_sweep.py` | no |
| Table 18 | `tab:summary` | *(narrative summary)* | — |
| Table 19 | `tab:metatool-subset` | `eval_metatool_subset_analysis.py` (Appendix B) | no |

For each script, a fresh run writes a structured JSON result file to `results/` plus a reproducibility footer that captures Python, numpy, scipy, and bear versions along with the git commit hash. Pre-computed result files corresponding to the paper's numbers are already committed to `results/` for direct comparison.

## Layout

```
evals/                                # evaluation scripts
  # Pet Simulation (deterministic, no LLM)
  eval_retrieval.py                   # Table 9: F1 by query type, alpha ablation
  eval_retrieval_backends.py          # Backend comparison across embeddings
  eval_governance_ablation.py         # Table 15: F1@10 governance ablation
  eval_governance_decomposed.py       # Table 16: decomposed governance × 5 backends + ITR row
  eval_baseline_comparison.py         # Tables 13, 14: CPA vs BEAR (semantic recall + tokens)
  eval_scalability.py                 # Table 12: token efficiency at 10-500 agents
  eval_tool_scaling.py                # Tables 10, 11: tool scaling + token savings
  eval_tool_composition.py            # Composer output validation
  eval_ablation.py                    # Parameter sensitivity (alpha, theta, K)
  eval_alpha_sweep.py                 # Table 17: alpha weight sweep
  compute_petsim_stats.py             # Pet Sim corpus descriptive statistics

  # ToolBench + MetaTool retrieval (deterministic, no LLM)
  eval_toolbench.py                   # Tables 3, 5, 6: ToolBench + MetaTool retrieval
  eval_toolbench_inferred_categories.py  # Table 4: LLM-inferred categories (top-1)
  eval_toolbench_multitag_categories.py  # Table 4: LLM-inferred categories (multi-tag)
  eval_toolbench_top5_categories.py      # Table 4: LLM-inferred categories (top-5)
  eval_metatool_subset_analysis.py    # Table 19 (Appendix B): retained vs excluded subsets

  # Anthropic-API metadata generation (produces JSON consumed by the retrieval evals)
  metatool_generate_tags.py           # MetaTool tool-tag generation
  metatool_generate_query_tags.py     # MetaTool per-query top-1 tag generation
  metatool_generate_query_tags_top5.py# MetaTool per-query top-5 tag generation

  # End-to-end tool selection (requires OpenAI-compatible LLM endpoint)
  eval_toolbench_e2e.py               # Table 7: single-turn end-to-end
  eval_toolbench_react.py             # Table 8: ReAct end-to-end

  # Shared utilities
  toolbench_setup.py                  # Download ToolBench and MetaTool data
  stat_utils.py                       # Bootstrap CI / paired-sample tests
  repro_footer.py                     # Reproducibility metadata capture

pet_sim/instructions/                 # frozen Pet Simulation corpus (8 YAML files)
                                      # DO NOT MODIFY — these are exactly what the
                                      # paper measured against
results/                              # pre-computed result files referenced in the paper
run_evals.sh                          # runner reproducing all paper tables
serve_mistral_nemo.sh                 # vLLM server matching paper Tables 7, 8 deployment
requirements.txt                      # pinned dependency set
```

## Running Individual Evals

`./run_evals.sh` invokes every deterministic script; passing `--all` adds the LLM-required experiments. To reproduce a single table, run its script directly:

```bash
# Pet Simulation (deterministic, no LLM)
python evals/eval_retrieval.py                   # Table 9 (lexical)
python evals/eval_retrieval.py --semantic        # Table 9 (semantic)
python evals/eval_retrieval_backends.py --all    # Backend comparison
python evals/eval_governance_ablation.py         # Table 15
python evals/eval_governance_decomposed.py       # Table 16
python evals/eval_baseline_comparison.py         # Tables 13, 14
python evals/eval_baseline_comparison.py --semantic  # Table 13 semantic
python evals/eval_scalability.py                 # Table 12
python evals/eval_tool_scaling.py                # Tables 10, 11
python evals/eval_tool_composition.py            # Composer validation
python evals/eval_ablation.py                    # Parameter sensitivity (lexical)
python evals/eval_ablation.py --semantic         # Parameter sensitivity (semantic)
python evals/eval_alpha_sweep.py                 # Table 17

# ToolBench + MetaTool retrieval (deterministic; requires toolbench_setup.py first)
python evals/eval_toolbench.py --latex           # Tables 3, 5, 6
python evals/eval_toolbench_inferred_categories.py   # Table 4 (top-1)
python evals/eval_toolbench_multitag_categories.py   # Table 4 (multi-tag)
python evals/eval_toolbench_top5_categories.py       # Table 4 (top-5)
python evals/eval_metatool_subset_analysis.py    # Table 19 (Appendix B)

# End-to-end LLM experiments (requires OpenAI-compatible endpoint)
python evals/eval_toolbench_e2e.py \             # Table 7
    --model mistralai/Mistral-Nemo-Instruct-2407 \
    --base-url http://127.0.0.1:8000/v1
python evals/eval_toolbench_react.py \           # Table 8
    --model mistralai/Mistral-Nemo-Instruct-2407 \
    --base-url http://127.0.0.1:8000/v1
```

## Regenerating LLM-Generated Metadata

Table 4 (LLM-inferred ToolBench categories) and Table 6 (MetaTool tag variants) use tag JSON that was generated once via the Anthropic Messages API and then committed. The retrieval evals that consume this JSON are deterministic; only the generation step needs an API key.

To regenerate:

```bash
# ANTHROPIC_API_KEY may live in .env instead of being exported
python evals/metatool_generate_tags.py            # tool-level tags for Table 6
python evals/metatool_generate_query_tags_top5.py # per-query tags (up to 5) for Table 6
# ToolBench inferred-category variants are generated inline by their eval scripts.
```

`evals/metatool_generate_query_tags.py` (a single top-1 tag per query) is kept for
reference but is **not used by any reported table**. The manuscript reports only
the up-to-five-tag MetaTool+QueryTags condition.

Generated tag files are written to `evals/` (`metatool_tags.json`, `metatool_query_tags.json`, `metatool_query_tags_top5.json`).

## Embedding Models

The following models download automatically on first use via HuggingFace:

- `BAAI/bge-base-en-v1.5` (768-dim, primary)
- `BAAI/bge-m3` (1024-dim)
- `Qwen/Qwen3-Embedding-0.6B` (1024-dim)
- `Qwen/Qwen3-Embedding-4B` (2560-dim)

## Corpus Integrity

The `pet_sim/instructions/` directory is a frozen snapshot of the corpus used to generate all Pet Simulation results in the paper. Do not modify these files. Doing so will produce different numerical results.

## BEAR Version

Pinned to bear `v0.1.10` (see `requirements.txt`). Bumping the version will likely change numerical results. Update the pin and re-run the full suite before comparing to published numbers.
