# Retrieval-Governed Context — Paper Artifacts

**Provisional Patent Pending (filed April 15, 2026)** | Copyright (c) 2024-2026 The Pennsylvania State University. All rights reserved.
Inventor: Scott N. Hwang

Licensed under the [Open Core Ventures Source Available License (OCVSAL) v1.0](LICENSE). Production use requires a commercial agreement. For commercial licensing, contact the Penn State Office of Technology Transfer at ottinfo@psu.edu.

Evaluation scripts, frozen corpus, and result files for:

> "Retrieval-Governed Context for Instructions and Tools in LLMs and Intelligent Agents: Declared Rules, Guarantees, and Enforcement"

Uses the BEAR library at [snhwang/bear](https://github.com/snhwang/bear), pinned to `v0.4.2`.

The revised manuscript (TIST round 2) adds three things to this repository:
- `reproduce/` is the kit that reruns every result of the revised paper, one script per step. Start with `reproduce/README.md`.
- `hermes/` is the execution-level experiment in Hermes Agent (`hermes/REPRODUCE.md`).
- `docs/capability-evidence.md` holds the sources behind Table 1.

The revised paper's numbers come from the kit in `reproduce/`. `run_evals.sh`, described below, is the earlier one-command runner. It runs the same deterministic scripts as before. It does not cover the results added in the revision, such as the Nemotron backend, the mandatory-coverage rows of Table 11 and Tables 12 to 17.

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

# Run the deterministic evaluations (no LLM)
./run_evals.sh

# Add the end-to-end LLM experiments (Table 10, and the Mistral-Nemo cells of Supplement Table S1).
# Paper-exact reproduction: Mistral-Nemo-Instruct-2407 (12B, Q4_0) served by Ollama.
ollama pull mistral-nemo                            # ~7GB, one time
OLLAMA_CONTEXT_LENGTH=131072 ollama serve           # in one shell (fits the ~82k monolithic prompt)
./run_evals.sh --all \
    --base-url http://127.0.0.1:11434/v1 \
    --model mistral-nemo                            # in another
```

Any OpenAI-compatible endpoint works (Ollama, vLLM, LM Studio). See
[Serving the model](#serving-the-model) for the exact deployment behind Table 10,
and for alternatives.

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

Table 10 and the Mistral-Nemo cells of Supplement Table S1 were produced with
**Mistral-Nemo-Instruct-2407 (12B) at `Q4_0` quantization, served by
[Ollama](https://ollama.com)**. The Gemma 4 cells of Table S1 came from Ollama
too (`gemma4:12b`, `gemma4:31b`). The revision reran every end-to-end result in
November 2026 on tags that add only a fixed window to these builds
(`mistral-nemo-32k`, `mistral-nemo-131k`, `gemma4-12b-131k`, `gemma4-31b-131k`).
`results/v042/README_E2E_RERUNS.md` lists each run with its tag, digest, window
and seed. The Hermes experiment
(Table 16) and the second tagger (Table 17) use a different server, described in
`hermes/REPRODUCE.md` and `evals/authorship/README.md`.

Serve Mistral-Nemo as follows.

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

This map follows the revised manuscript (TIST round 2) as built on 20 Nov 2026. The article has Tables 1 to 19, and its online Supplement has Tables S1 to S4. Every retrieval result and every end-to-end result of the revision runs on BEAR v0.4.2. The end-to-end results (Table 10, the end-to-end text of Section 4.2 and Supplement Table S1) were rerun in November 2026 under `evals/e2e_rerun/PLAN.md`, and `results/v042/README_E2E_RERUNS.md` lists those runs. `reproduce/` reruns all of them by hand and records each run. `reproduce/MANIFEST.md` is the full map. It covers every table, figure and in-text number, the exact command, the output file, and whether a number comes from this revision or is kept from the July and August 2026 runs. Static tables and the figures have no backing script.

The kit files (`reproduce/MANIFEST.md`, `reproduce/README.md`, `reproduce/lib/paper_map.py`) follow the same numbering. `run_evals.sh` still prints the table numbers of the first submission in its progress lines. Labels and kit ids do not change. T14 and T15 belong to tables that the revision later removed. Their scripts and committed outputs remain. The kit's other ids are in-text numbers, listed in the MANIFEST.

The paper prints three backend labels differently from the scripts and the result files. Nemotron-Embed, Qwen3-Emb-0.6B and Qwen3-Emb-4B in the paper are `Nemotron`, `Qwen3-0.6B` and `Qwen3-4B` in the result keys (for example `BEAR+Qwen3-4B (gov)`), and `nemotron`, `qwen3-0.6b` and `qwen3-4b` in the backend options. The models are the same. The paper's labels say that they are embedding models. Appendix D of the paper (Table 19) lists every model with its identifier, precision or quantization, server and settings.

| Paper | Label | Backing script(s) in `evals/` | Kit script | Kit id | LLM required |
|:--|:--|:--|:--|:--|:--:|
| Table 1 | `tab:capabilities` | *(static, evidence in `docs/capability-evidence.md`)* | none | T01 | n/a |
| Figure 1 | `fig:instructions` | *(YAML example in the text)* | none | F1 | n/a |
| Table 2 | `tab:schema-cheatsheet` | *(static)* | none | T02 | n/a |
| Figure 2 | `fig:pipeline` | *(TikZ drawing, `Figure1.tex` in the paper repo)* | `80_figures.sh` | F2 | n/a |
| Table 3 | `tab:rq` | *(static)* | none | T03 | n/a |
| Table 4 | `tab:model-roles` | *(static)* | none | T04 | n/a |
| Table 5 | `tab:provenance` | *(static)* | none | T05 | n/a |
| Table 6 | `tab:toolbench-results` | `wp0_v040/eval_toolbench_v040.py` (all seven backends) | `10_`, `20_`, `30_` | T06 | no |
| Table 7 | `tab:toolbench-inferred` | `eval_toolbench_inferred_categories.py`, `eval_toolbench_multitag_categories.py`, `eval_toolbench_top5_categories.py` (categories cached from the Anthropic API) | `10_` | T07 | no (post-generation) |
| Table 8 | `tab:metatool-results` | `wp0_v040/eval_toolbench_v040.py` | `10_`, `20_`, `30_` | T08 | no |
| Table 9 | `tab:metatool-tags-results` | `wp0_v040/eval_toolbench_v040.py` with the tags of `metatool_generate_tags.py` and `metatool_generate_query_tags_top5.py` | `10_`, `20_`, `30_` | T09 | no (post-generation) |
| Table 10, and the hash row and the 128-schema run of Section 4.2 | `tab:e2e` | `wp0_v040/run_e2e_rerun.sh` (`e2e_rerun.py`) for the retrieval rows and the hash row. `eval_toolbench_e2e.py` for the monolithic row and the 128-schema run | `50_`, `56_` | T10a, T10b, T10c, XE2Ea | yes |
| Section 4.3, text | none (earlier `tab:token-efficiency`, `tab:tool-scaling`, `tab:token-savings`) | `eval_scalability.py`, `eval_baseline_comparison.py`, `eval_tool_scaling.py` | `10_` | T13, T26 | no |
| Table 11 | `tab:decomposed-ablation` | `eval_governance_decomposed.py`. Bottom rows: `eval_mandatory_coverage.py` | `10_`, `15_` to `40_` | T17, T17b | no |
| Table 12 | `tab:invariants` | `eval_invariants.py` (via `run_wp256.sh v042`) | `15_` | T18 | no |
| Table 13, and the CPA text of Section 4.6 | `tab:baselines` | `eval_metadata_filter_baseline.py`, `eval_cpa_maintained.py` | `15_`, `30_` | T19 | no |
| Table 14 | `tab:robustness` | `eval_tag_noise.py`, `eval_leakage_threat.py`, `eval_query_giveaways.py`, `check_bm25_v042.py` | `15_` to `40_` | T20 | no |
| Table 15 | `tab:tokens-recall` | `wp0_v040/dump_toolbench_lists.py`, `merge_wp4_lists.py`, `wp4_token_efficiency.py`, `wp4_summary.py` | `10_` to `30_`, `70_` | T21 | no |
| Table 16 | `tab:hermes` | `hermes/run.py`, `analyze_stage1.py`, `analyze_stage2.py` (see `hermes/REPRODUCE.md`) | `60_` | XH | yes |
| Table 17 (Appendix A) | `tab:second-tagger` | `authorship/tag.py`, `validate.py`, `eval_tagged.py`, `analyze.py` (see `evals/authorship/README.md`) | `65_` | XAUTH | yes (tagging) |
| Appendix B, text | none (earlier `tab:retrieval`) | `eval_retrieval.py` | `10_` | T25 | no |
| Table 18 (Appendix B) | `tab:governance-ablation` | `eval_governance_ablation.py` | `10_` | T16 | no |
| Table 19 (Appendix D) | `tab:models` | *(static, every model with its identifier and settings)* | none | TM | n/a |
| Supplement Table S1, and the ReAct numbers of Section 4.2 | `tab:e2e-scale` | `eval_toolbench_react.py`, alone for the Mistral-Nemo cells and via `run_model_full1100.sh` and `run_model_scaffold_nothink.sh` for the Gemma 4 cells, then `grid_from_full1100.py` and `scaffold_vs_single.py` | `56_` | T11, T12 | yes |
| Supplement Table S2 | `tab:transfer` | `eval_backend_transfer.py` (off-the-shelf rows: the ungated rows of Tables 6 and 8) | `10_` | T23 | no |
| Supplement Table S3 | `tab:reranker` | `eval_reranker_composition.py`, `eval_framework_baseline.py` | `10_` | T24 | no |
| Supplement Table S4 | `tab:alpha-sweep` | `eval_alpha_sweep.py` | `10_` | T28 | no |

Each script writes its result files with a provenance record (Python, numpy, scipy, BEAR version and source sha). The kit writes every output below `$REPRO_OUT` and never into `results/`. `reproduce/verify.py` compares those outputs with the committed files in `results/`, and `reproduce/collect.py` lists every manuscript number with its source file.

## Layout

```
evals/                                # evaluation scripts
  # Pet Simulation and the customer-support corpus (deterministic, no LLM)
  eval_retrieval.py                   # Appendix B (text): retrieval by query type
  eval_retrieval_backends.py          # Backend comparison across embeddings
  eval_governance_ablation.py         # Table 18: F1@10 governance ablation
  eval_governance_decomposed.py       # Table 11: decomposed governance by backend + ITR row
  eval_mandatory_coverage.py          # Table 11, bottom rows: mandatory-coverage test
  eval_scope_excluded_safety.py       # Earlier safety panel (not in the revised paper)
  eval_baseline_comparison.py         # Section 4.3 (text): CPA vs BEAR
  eval_scalability.py                 # Section 4.3 (text): token use at 10-500 agents
  eval_tool_scaling.py                # Section 4.3 (text): tool scaling + token savings
  eval_tool_composition.py            # Composer output validation
  eval_ablation.py                    # Parameter sensitivity (alpha, theta, K)
  eval_alpha_sweep.py                 # Supplement Table S4: alpha weight sweep
  compute_petsim_stats.py             # Pet Sim corpus descriptive statistics

  # ToolBench + MetaTool retrieval (deterministic, no LLM)
  eval_toolbench.py                   # Tables 6, 8, 9: ToolBench + MetaTool retrieval
  wp0_v040/                           # the revision's runs of Tables 6, 8, 9 (with Nemotron), the Table 10 reruns, Table 15
  eval_toolbench_inferred_categories.py  # Table 7: LLM-inferred categories (top-1)
  eval_toolbench_multitag_categories.py  # Table 7: LLM-inferred categories (multi-tag)
  eval_toolbench_top5_categories.py      # Table 7: LLM-inferred categories (top-5)

  # Guarantees, baselines and robustness (deterministic, no LLM)
  eval_invariants.py                  # Table 12: invariants on 2,000 random corpora
  eval_metadata_filter_baseline.py    # Table 13: metadata filters in LlamaIndex
  eval_cpa_maintained.py              # Section 4.6 (text): maintained vs stale CPA
  eval_tag_noise.py                   # Table 14: tag noise
  eval_leakage_threat.py              # Table 14: leakage
  eval_query_giveaways.py             # Table 14: query giveaways
  eval_backend_transfer.py            # Supplement Table S2: fine-tuned retriever in and out of domain
  eval_reranker_composition.py        # Supplement Table S3: reranker substitution and composition
  eval_framework_baseline.py          # Supplement Table S3: LlamaIndex retrieval path

  # Anthropic-API metadata generation (produces JSON consumed by the retrieval evals)
  metatool_generate_tags.py           # MetaTool tool-tag generation
  metatool_generate_query_tags.py     # MetaTool per-query top-1 tag generation
  metatool_generate_query_tags_top5.py# MetaTool per-query top-5 tag generation
  authorship/                         # Table 17: the same tags written again by a second model

  # End-to-end tool selection (requires OpenAI-compatible LLM endpoint)
  eval_toolbench_e2e.py               # Table 10: single-turn end-to-end
  eval_toolbench_react.py             # Supplement Table S1: ReAct end-to-end

  # Shared utilities
  toolbench_setup.py                  # Download ToolBench and MetaTool data
  stat_utils.py                       # Bootstrap CI / paired-sample tests
  repro_footer.py                     # Reproducibility metadata capture

pet_sim/instructions/                 # frozen Pet Simulation corpus (8 YAML files)
                                      # DO NOT MODIFY — these are exactly what the
                                      # paper measured against
hermes/                               # Table 16: the Hermes Agent experiment (hermes/REPRODUCE.md)
reproduce/                            # the kit that reruns the revised paper (reproduce/README.md)
docs/capability-evidence.md           # sources behind Table 1
results/                              # pre-computed result files referenced in the paper
run_evals.sh                          # one-command runner of the deterministic evals (predates the revision)
serve_mistral_nemo.sh                 # optional vLLM server (bf16). Table 10 used Ollama
requirements.txt                      # pinned dependency set
```

## Composition Layer

`evals/composition.py` packages the paper's composition claim as reusable
code: BEAR governs candidate-set construction, and external systems attach as
post-stages over the governed candidate set, through BEAR's public API, with
no changes to BEAR core (pinned at v0.4.2).

- `ComposedRetriever` — drop-in wrapper: governed over-fetch, post-stage,
  top-k cut. A post-stage sees only the governed candidate set, so gate
  exclusions and mandatory injections are preserved by construction.
- `CrossEncoderReranker` — the released `BAAI/bge-reranker-base` as a
  post-stage. This is the measured composition (Supplement Table S3):
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

`./run_evals.sh` runs the deterministic scripts listed below. Passing `--all` adds the two end-to-end experiments. The scripts added in the revision run through `reproduce/`. Each script can also be run directly.

```bash
# Pet Simulation (deterministic, no LLM)
python evals/eval_retrieval.py                   # Appendix B text (lexical)
python evals/eval_retrieval.py --semantic        # Appendix B text (semantic)
python evals/eval_retrieval_backends.py --all    # Backend comparison
python evals/eval_governance_ablation.py         # Table 18
python evals/eval_governance_decomposed.py       # Table 11
python evals/eval_scope_excluded_safety.py       # earlier safety panel (not in the revised paper)
python evals/eval_baseline_comparison.py         # Section 4.3 text (CPA vs BEAR)
python evals/eval_baseline_comparison.py --semantic  # the same, semantic
python evals/eval_scalability.py                 # Section 4.3 text
python evals/eval_tool_scaling.py                # Section 4.3 text
python evals/eval_tool_composition.py            # Composer validation
python evals/eval_ablation.py                    # Parameter sensitivity (lexical)
python evals/eval_ablation.py --semantic         # Parameter sensitivity (semantic)
python evals/eval_alpha_sweep.py                 # Supplement Table S4

# ToolBench + MetaTool retrieval (deterministic; requires toolbench_setup.py first)
python evals/eval_toolbench.py --latex           # Tables 6, 8, 9
python evals/eval_toolbench_inferred_categories.py   # Table 7 (top-1)
python evals/eval_toolbench_multitag_categories.py   # Table 7 (multi-tag)
python evals/eval_toolbench_top5_categories.py       # Table 7 (top-5)

# Supplement Table S1 (monolithic configurations vs governance, full 1,100 queries, LLM required).
# Mistral cells reuse the Table 10 and ReAct runs. Gemma models (~4-9 h each per driver):
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
python evals/eval_toolbench_e2e.py --all \       # Table 10
    --model mistral-nemo \
    --base-url http://127.0.0.1:11434/v1
python evals/eval_toolbench_react.py \           # Supplement Table S1 (Mistral-Nemo cells)
    --model mistral-nemo \
    --base-url http://127.0.0.1:11434/v1
```

## Troubleshooting

**`/usr/bin/env: 'bash\r': No such file or directory` or `$'\r': command not
found` when running a shell script.** The script has Windows (CRLF) line
endings, which Linux and WSL cannot execute. This can happen when the
repository is shared between Windows and WSL on the same working tree (for
example on `/mnt/c`) and a Windows-side tool, editor, or `git` with
`core.autocrlf=true` rewrites the file. `.gitattributes` pins `*.sh` to LF at
checkout, but it cannot repair a working-tree file that a Windows tool has
already rewritten, and `git pull` will report "already up to date" because
the committed content is unchanged. Fix in place:

```bash
sed -i 's/\r$//' run_evals.sh resume_rerun.sh
```

The same symptom in Python scripts is harmless (Python accepts CRLF), but
shell scripts, including any you add, should stay LF.

**`run_evals.sh` exits within seconds.** The script needs the project venv.
It prefers `.venv/bin/python` automatically and aborts with an explicit error
if `import bear` fails. Run it from the repo root inside WSL.

**`verify_rerun.py` reports "NO RE-RUN DETECTED".** The verifier only trusts
result files newer than `results/.rerun_started`, which `run_evals.sh` and
`resume_rerun.sh` write when they start. Run one of those first; the message
prevents the misleading case where untouched committed files are compared
against themselves and trivially "match."

## Regenerating LLM-Generated Metadata

Table 7 (LLM-inferred ToolBench categories) and Table 9 (MetaTool tag variants) use tag JSON that was generated once via the Anthropic Messages API and then committed. The retrieval evals that consume this JSON are deterministic. Only the generation step needs an API key. Table 17 repeats the tagging with a second, locally served model (`evals/authorship/README.md`).

To regenerate:

```bash
# ANTHROPIC_API_KEY may live in .env instead of being exported
python evals/metatool_generate_tags.py            # tool-level tags for Table 9
python evals/metatool_generate_query_tags_top5.py # per-query tags (up to 5) for Table 9
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

The revision adds a seventh backend, `nvidia/llama-nemotron-embed-vl-1b-v2` (2048-dim). It is served on port 8360 and is not downloaded by the scripts (`reproduce/README.md`). BM25 and the hash embedder need no model.

## Corpus Integrity

The `pet_sim/instructions/` directory is a frozen snapshot of the corpus used to generate all Pet Simulation results in the paper. Do not modify these files. Doing so will produce different numerical results.

## BEAR Version

Pinned to bear `v0.4.2` (commit `0d0718a`, see `requirements.txt`). Every retrieval result and every end-to-end result of the revision runs on it. The July and August 2026 runs used `v0.1.10`, and the revision reran every result that depends on BEAR (see `reproduce/MANIFEST.md`). Bumping the version can change numerical results. Update the pin and rerun the suite (`reproduce/`) before comparing to published numbers.
