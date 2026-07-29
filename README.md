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

# Add end-to-end LLM experiments (Tables 7, 8, 9).
# Paper-exact reproduction: Mistral-Nemo-Instruct-2407 (12B, Q4_0) served by Ollama.
ollama pull mistral-nemo                            # ~7GB, one time
OLLAMA_CONTEXT_LENGTH=131072 ollama serve           # in one shell (fits the ~82k monolithic prompt)
./run_evals.sh --all \
    --base-url http://127.0.0.1:11434/v1 \
    --model mistral-nemo                            # in another
```

Any OpenAI-compatible endpoint works (Ollama, vLLM, LM Studio). See
[Serving the model](#serving-the-model) for the exact deployment behind Tables 7
and 8, and for alternatives.

## Environment Setup

Most paper tables are deterministic and require **no API keys**. Keys are only
needed to regenerate the LLM-inferred metadata (the ToolBench inferred-category
and MetaTool generated-tag conditions). The end-to-end experiments need no key:
`ollama pull mistral-nemo` is unauthenticated.

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
| `HF_TOKEN` | Downloading Mistral-Nemo weights for the **vLLM** path only | Not needed for Ollama. Anonymous downloads of the ~24GB `bf16` checkpoint are heavily rate-limited. |

The end-to-end evals (`eval_toolbench_e2e.py`, `eval_toolbench_react.py`) do not
read a key from the environment; they talk to an OpenAI-compatible endpoint
selected with `--base-url` / `--model`.

## Serving the model

Tables 7 and 8 were produced with **Mistral-Nemo-Instruct-2407 (12B) at `Q4_0`
quantization, served by [Ollama](https://ollama.com)**. This is the only
deployment the published numbers come from, and the only one needed to
reproduce them:

```bash
ollama pull mistral-nemo                                    # Q4_0 by default; ~7GB

# The monolithic baseline injects the whole 3,225-tool corpus (~82k tokens), so
# the context window must be 131072. Set the variable in the SAME shell that
# runs `ollama serve`; quit the Ollama tray app first, or it keeps serving the
# old window on port 11434 and ignores this.
OLLAMA_CONTEXT_LENGTH=131072 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_HOST=0.0.0.0 ollama serve
```

Verify the window took effect (Ollama only reports a model once it is loaded, so
warm it first):

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions -H 'Content-Type: application/json' \
    -d '{"model":"mistral-nemo","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' >/dev/null
curl -s http://127.0.0.1:11434/api/ps          # expect "context_length":131072
```

```bash
python evals/eval_toolbench_e2e.py --all \
    --base-url http://127.0.0.1:11434/v1 --model mistral-nemo
python evals/eval_toolbench_react.py \
    --base-url http://127.0.0.1:11434/v1 --model mistral-nemo
```

Both evals preflight the prompt against the server's context window and abort
with instructions if it is too small, so a wrong `OLLAMA_CONTEXT_LENGTH` fails
loudly rather than silently truncating the monolithic prompt.

Three things this depends on, all of which will silently change the numbers if
you get them wrong:

**Quantization.** `Q4_0`, which is what `ollama pull mistral-nemo` gives you by
default. Quantization is not output-preserving — serving the same model at
`bf16` produces different scores.

**Structured outputs.** Both evals constrain tool selection with a
`response_format` JSON schema whose enum lists the candidate tool names, so the
server must support OpenAI-style structured outputs. Neither eval sends
`tools=` / `tool_choice=`; free-form function calling is not used anywhere in
this repository, and models that emit malformed tool-call JSON under it were
the source of a large error rate before this was fixed.

**Context length.** `OLLAMA_CONTEXT_LENGTH=131072`. The monolithic baseline
injects all 3,225 tool schemas into one prompt (~82k tokens), so the window must
be at least ~98k; 131072 clears it with margin and stays within Mistral-Nemo's
128k native context. The retrieval conditions only need ~2k, so if you run
*only* those (`--skip-monolithic`, or `--monolithic-cap` at a small value) you
can drop to `32768` and save KV-cache VRAM — but the default paper runs include
the monolithic baseline, so use 131072.

Left unset entirely, Ollama sizes the KV cache from *free VRAM* at load time and
will reserve tens of gigabytes it never uses, starving the retrieval embedders
the eval loads onto the same card. Pinning the value bounds it: ~20GB at 131072,
~5GB at 32768. `OLLAMA_MAX_LOADED_MODELS=1` keeps previously used models from
lingering in VRAM.

| Variable | Value | Why |
|:--|:--|:--|
| `OLLAMA_CONTEXT_LENGTH` | `131072` | Fits the ~82k-token monolithic prompt; also bounds the KV cache. Drop to `32768` only if you skip the monolithic baseline. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | Stops idle models from holding VRAM. |
| `OLLAMA_HOST` | `0.0.0.0` | Only needed to reach the server from another machine (or from WSL — see below). |

Any other OpenAI-compatible endpoint with structured-output support (vLLM, LM
Studio) will run the evals, but will not reproduce the published numbers unless
it serves the same model at the same quantization.

### VRAM: keep the LLM off the embedders' card

The evals load embedding models onto the GPU for retrieval while the LLM server
holds weights plus a KV cache on the same card. `eval_toolbench_e2e.py --all`
is the worst case: it builds six retrievers, the largest (Qwen3-4B) about 8GB.
Under WSL, exhausting VRAM does **not** raise an error — the driver silently
spills to host memory over PCIe and throughput collapses to a few tokens per
second.

Two failure modes are worth naming, because neither announces itself:

- A server sized against free VRAM (Ollama's default, and llama.cpp's, which
  backs LM Studio) expands to fill an empty card. Quantization does not save
  you here: a 7GB model can still occupy 50GB. Bound the context explicitly.
- Idle models left resident. Check with `ollama ps`, and check for a stray
  `llama-server` or `vllm` with
  `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv`.

Serving the LLM from a second machine removes the contention entirely:

```bash
# On the GPU box serving the LLM
OLLAMA_HOST=0.0.0.0 OLLAMA_CONTEXT_LENGTH=131072 ollama serve

# On the machine running the evals — its GPU is now free for the embedders
python evals/eval_toolbench_e2e.py --all \
    --base-url http://<server-ip>:11434/v1 --model mistral-nemo
```

Network latency (~1–5 ms) is negligible next to LLM inference (100–500 ms per
call). Verify reachability and get the exact model id with:

```bash
curl -s http://<server-ip>:11434/v1/models | python -m json.tool
```

Note for **WSL**: WSL2 is NAT'd, so `localhost` inside WSL is not the Windows
loopback. If the eval runs in WSL and Ollama runs on Windows, set
`OLLAMA_HOST=0.0.0.0` and point `--base-url` at the host's LAN address, not
`127.0.0.1`.

### Extras (not used by the paper)

`serve_mistral_nemo.sh` starts a vLLM server for the unquantized `bf16`
checkpoint. **Nothing in the paper was produced with it.** It is kept because
vLLM is a better choice for throughput-bound work and for unquantized runs, and
it is here to play with, not to reproduce anything. It reads `MODEL`, `HOST`,
`PORT` (default `8355`), `MAX_MODEL_LEN`, and `GPU_MEM_UTIL` from `.env`; see
the script's header. Serving `bf16` needs ~24GB of weights against `Q4_0`'s
~7GB, and the eval's `--model` must then be the full Hugging Face id
(`mistralai/Mistral-Nemo-Instruct-2407`), not `mistral-nemo`.

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
| Table 9 | `tab:e2e-scale` | `eval_toolbench_react.py` driven by `run_model_full1100.sh` (native-reasoning conditions) and `run_model_scaffold_nothink.sh` (constrained scaffold); analyze with `grid_from_full1100.py` and `scaffold_vs_single.py`. Gemma-31B assembled from pilot + complement via `make_complement_indices.py`, `run_gemma_complement.sh`, `merge_gemma_full1100.py`. Mistral cells reuse the Table 7/8 runs. | yes |
| Table 10 | `tab:retrieval` | `eval_retrieval.py` | no |
| Table 11 | `tab:tool-scaling` | `eval_tool_scaling.py` | no |
| Table 12 | `tab:token-savings` | `eval_tool_scaling.py` (same run) | no |
| Table 13 | `tab:token-efficiency` | `eval_scalability.py` | no |
| Table 14 | `tab:semantic-advantage` | `eval_baseline_comparison.py --semantic` | no |
| Table 15 | `tab:token-compare` | `eval_baseline_comparison.py` | no |
| Table 16 | `tab:governance-ablation` | `eval_governance_ablation.py` | no |
| Table 17 | `tab:decomposed-ablation` | `eval_governance_decomposed.py`; safety panel at the bottom from `eval_scope_excluded_safety.py` | no |
| Table 18 | `tab:alpha-sweep` | `eval_alpha_sweep.py` | no |
| Table 19 | `tab:summary` | *(narrative summary)* | — |
| Table 20 | `tab:transfer` | `eval_backend_transfer.py` | no |
| Table 21 | `tab:reranker` | `eval_reranker_composition.py` (reranker arms, both corpora); `eval_framework_baseline.py` (LlamaIndex row) | no |

For each script, a fresh run writes a structured JSON result file to `results/` plus a reproducibility footer that captures Python, numpy, scipy, and bear versions along with the git commit hash. Pre-computed result files corresponding to the paper's numbers are already committed to `results/` for direct comparison.

## Layout

```
evals/                                # evaluation scripts
  # Pet Simulation (deterministic, no LLM)
  eval_retrieval.py                   # Table 10: F1 by query type, alpha ablation
  eval_retrieval_backends.py          # Backend comparison across embeddings
  eval_governance_ablation.py         # Table 16: F1@10 governance ablation
  eval_governance_decomposed.py       # Table 17: decomposed governance × 5 backends + ITR row
  eval_scope_excluded_safety.py       # Table 17 safety panel: mandatory ON/OFF on scope-excluded variant
  eval_baseline_comparison.py         # Tables 13, 14: CPA vs BEAR (semantic recall + tokens)
  eval_scalability.py                 # Table 13: token efficiency at 10-500 agents
  eval_tool_scaling.py                # Tables 10, 11: tool scaling + token savings
  eval_tool_composition.py            # Composer output validation
  eval_ablation.py                    # Parameter sensitivity (alpha, theta, K)
  eval_alpha_sweep.py                 # Table 18: alpha weight sweep
  compute_petsim_stats.py             # Pet Sim corpus descriptive statistics

  # ToolBench + MetaTool retrieval (deterministic, no LLM)
  eval_toolbench.py                   # Tables 3, 5, 6: ToolBench + MetaTool retrieval
  eval_toolbench_inferred_categories.py  # Table 4: LLM-inferred categories (top-1)
  eval_toolbench_multitag_categories.py  # Table 4: LLM-inferred categories (multi-tag)
  eval_toolbench_top5_categories.py      # Table 4: LLM-inferred categories (top-5)

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
serve_mistral_nemo.sh                 # optional vLLM server (bf16); Tables 7, 8 used Ollama
requirements.txt                      # pinned dependency set
```

## Composition Layer

`evals/composition.py` packages the paper's composition claim as reusable
code: BEAR governs candidate-set construction, and external systems attach as
post-stages over the governed candidate set, through BEAR's public API, with
no changes to BEAR core (pinned at v0.1.10).

- `ComposedRetriever` — drop-in wrapper: governed over-fetch, post-stage,
  top-k cut. A post-stage sees only the governed candidate set, so gate
  exclusions and mandatory injections are preserved by construction.
- `CrossEncoderReranker` — the released `BAAI/bge-reranker-base` as a
  post-stage. This is the measured composition (paper Table 21):
  `eval_reranker_composition.py` runs its arms through this layer, and the
  refactor was verified to reproduce the committed per-query results exactly
  on both corpora.
- `OutcomeReweightStage` — OATS-inspired outcome-aware reordering from
  per-item success priors. Illustrative adapter, not a reproduction of OATS.
- `GroupBoostStage` — Tool-to-Agent-inspired hierarchy grouping (sibling APIs
  of a strongly matched parent tool surface together). Illustrative adapter.

`evals/demo_composition.py` walks a few ToolBench queries through all four
configurations and prints the reordered top-k side by side (output committed
at `results/composition_demo.txt`). The demo is an illustration of
composability, not an evaluation; quantitative claims live in
`eval_reranker_composition.py`.

## Running Individual Evals

`./run_evals.sh` invokes every deterministic script; passing `--all` adds the LLM-required experiments. To reproduce a single table, run its script directly:

```bash
# Pet Simulation (deterministic, no LLM)
python evals/eval_retrieval.py                   # Table 10 (lexical)
python evals/eval_retrieval.py --semantic        # Table 10 (semantic)
python evals/eval_retrieval_backends.py --all    # Backend comparison
python evals/eval_governance_ablation.py         # Table 16
python evals/eval_governance_decomposed.py       # Table 17
python evals/eval_scope_excluded_safety.py       # Table 17 safety panel (scope-excluded variant)
python evals/eval_baseline_comparison.py         # Tables 13, 14
python evals/eval_baseline_comparison.py --semantic  # Table 14 semantic
python evals/eval_scalability.py                 # Table 13
python evals/eval_tool_scaling.py                # Tables 10, 11
python evals/eval_tool_composition.py            # Composer validation
python evals/eval_ablation.py                    # Parameter sensitivity (lexical)
python evals/eval_ablation.py --semantic         # Parameter sensitivity (semantic)
python evals/eval_alpha_sweep.py                 # Table 18

# ToolBench + MetaTool retrieval (deterministic; requires toolbench_setup.py first)
python evals/eval_toolbench.py --latex           # Tables 3, 5, 6
python evals/eval_toolbench_inferred_categories.py   # Table 4 (top-1)
python evals/eval_toolbench_multitag_categories.py   # Table 4 (multi-tag)
python evals/eval_toolbench_top5_categories.py       # Table 4 (top-5)

# Table 9 (monolithic configurations vs governance, full 1,100 queries, LLM required).
# Mistral cells reuse the Table 7/8 runs. Gemma models (~4-9 h each per driver):
MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_scaffold_nothink.sh   # scaffold, native off
MODEL=gemma4:31b LABEL=g4-31b bash evals/run_model_full1100.sh           # native-reasoning conditions
python evals/grid_from_full1100.py g4-31b                                # per-model grid + McNemar
python evals/scaffold_vs_single.py g4-31b                                # scaffold-vs-single analysis
# (repeat with MODEL=gemma4:12b LABEL=g4-12b)
# The eval aborts any condition whose responses come back empty (see
# --max-empty-rate); sanity-check the guard itself with:
bash evals/verify_empty_guard.sh

# End-to-end LLM experiments (requires an OpenAI-compatible endpoint with
# structured-output support; see "Serving the model")
python evals/eval_toolbench_e2e.py --all \       # Table 7
    --model mistral-nemo \
    --base-url http://127.0.0.1:11434/v1
python evals/eval_toolbench_react.py \           # Table 8
    --model mistral-nemo \
    --base-url http://127.0.0.1:11434/v1
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
