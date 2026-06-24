# TIST Revision Runbook

This runbook lists every new evaluation script added to the artifacts repository in support of the TIST major revision and explains how to run and commit each one.

All five scripts write **two committable outputs** to `results/`:

- **A JSON file** with structured per-condition metrics (means, CIs, effect sizes, classifier accuracy, etc.).
- **A text log** that captures everything printed to stdout, including a reproducibility footer at the end (timestamp, git commit, Python and library versions, command line, key parameters).

Each script also prints a `git add` command at the end so you know exactly what to commit.

---

## Quick reference

| Script | Resource needs | Reviewer concern | Status |
|---|---|---|---|
| `eval_governance_decomposed.py` | CPU only, ~15-20 min (full set) | R1.W3, R4.1 | Already run, committed |
| `eval_alpha_sweep.py` | CPU only, ~15-20 min (full set) | R1.W3, follow-up | Already run, committed |
| `eval_metatool_subset_analysis.py` | CPU only, <10 sec | R1.5 | Ready to run |
| `eval_toolbench_inferred_categories.py` | CPU + LLM API (~30 min, ~$0.10) | R3.7 | Ready to run |
| `eval_toolbench_react.py` | GPU + local vLLM (~3 hours) | R4.2 | Ready to run |

---

## 1. `eval_metatool_subset_analysis.py`

**Reviewer 1 #5** asked whether the 10,051-query retained subset of MetaTool+Tags differs systematically from the 11,060 excluded queries. This script answers that question with statistical tests.

### Run

```bash
cd /path/to/paper-retrieval-governed-context-artifacts
python evals/eval_metatool_subset_analysis.py
```

Deterministic, no LLM calls, ~10 seconds.

### Outputs

- `results/metatool_subset_analysis.json` — structured per-property output.
- `results/metatool_subset_output.txt` — printed log including a LaTeX block ready to paste into Appendix A, Table `tab:metatool-subset`.

### What to commit

The script prints the exact `git add` command at the end. Typical output:

```bash
git add results/metatool_subset_analysis.json \
        results/metatool_subset_output.txt
git commit -m "Add MetaTool retained-vs-excluded subset analysis results"
git push
```

---

## 2. `eval_toolbench_inferred_categories.py`

**Reviewer 3 #7** said the ToolBench comparison is unfair because BEAR uses oracle category labels as `required_tags` while ToolLLM operates zero-shot. This script answers the structural-equivalence question with an LLM-classifier substitute for the oracle.

### Prerequisites

- An LLM API key. The default provider is Anthropic, requiring `ANTHROPIC_API_KEY` in the environment (or in a `.env` file in the repo root). For an OpenAI-compatible endpoint, pass `--provider openai`, `--base-url`, and `--model`, with `OPENAI_API_KEY` set.

### Quick smoke test (50 queries, ~1 minute, ~$0.01)

```bash
python evals/eval_toolbench_inferred_categories.py --max-queries 50
```

### Full run (all 1,100 queries, ~30 minutes, ~$0.10)

```bash
python evals/eval_toolbench_inferred_categories.py
```

The script caches every LLM classification to `results/toolbench_inferred_categories.json`. Reruns are free unless you pass `--clear-cache`.

### Outputs

- `results/toolbench_inferred_metrics.json` — Recall@k, NDCG@k, F1@k with 95% bootstrap CIs for the three conditions: oracle / inferred / no-governance.
- `results/toolbench_inferred_categories.json` — the LLM classification cache (per-query category choice). Useful for diagnostics and for re-runs without re-spending API budget.
- `results/toolbench_inferred_output.txt` — printed log including a LaTeX block ready to paste into Section 5.3.

### What to commit

The script prints the exact `git add` command at the end. Typical output:

```bash
git add results/toolbench_inferred_metrics.json \
        results/toolbench_inferred_output.txt \
        results/toolbench_inferred_categories.json
git commit -m "Add ToolBench LLM-inferred-categories results (R3.7)"
git push
```

The cache file is worth committing because future readers can re-run the downstream retrieval without spending API budget.

---

## 3. `eval_toolbench_react.py`

**Reviewer 4 #2** asked whether BEAR's gains over the monolithic baseline hold under iterative reasoning paradigms like ReAct. This script evaluates three conditions: monolithic+ReAct, BEAR retrieval+ReAct, BEAR retrieval+single-turn.

### Prerequisites

- An OpenAI-compatible local LLM endpoint (LM Studio, vLLM, Ollama). The paper used `mistralai/Mistral-Nemo-Instruct-2407` 12B via vLLM. Pass `--model` and `--base-url` to override.

### Quick smoke test (50 queries, ~5 minutes)

```bash
python evals/eval_toolbench_react.py --max-queries 50
```

### Full run (~1,100 queries, ~3 hours on a single GPU)

```bash
python evals/eval_toolbench_react.py
```

### Outputs

- `results/toolbench_react_metrics.json` — per-condition tool-selection accuracy with 95% bootstrap CIs.
- `results/toolbench_react_output.txt` — printed log including a LaTeX block ready to paste into the manuscript as the new Table 5b.

### What to commit

```bash
git add results/toolbench_react_metrics.json \
        results/toolbench_react_output.txt
git commit -m "Add ToolBench ReAct end-to-end results (R4.2)"
git push
```

### Resume / partial runs

If the LLM endpoint dies partway through, you can skip already-completed conditions with `--skip`. Example:

```bash
python evals/eval_toolbench_react.py --skip mono-react
```

---

## Reproducibility footer

Every committed log file ends with a `=== Reproducibility ===` block that includes:

- UTC timestamp
- Command line as typed
- Python and platform version
- Versions of numpy, scipy, and bear
- Git commit hash, branch, and clean/dirty status
- Per-script extras (model name, n queries, classifier accuracy, etc.)

This makes the committed log self-documenting. A reviewer who clones the repo and inspects the log can reproduce the exact run.

---

## After the revision

When all five scripts have been run and their results committed, the artifacts repository will contain:

- 5 new evaluation scripts under `evals/`
- 1 shared utility module (`evals/repro_footer.py`)
- 10+ per-condition JSON files under `results/` (per-backend governance decomposed, per-backend alpha sweep, MetaTool subset, ToolBench inferred-categories, ToolBench ReAct)
- 5 text log files under `results/` with reproducibility footers
- 1 ITR-library classification cache (`results/toolbench_inferred_categories.json`)

This is the complete reproducibility package for the TIST revision.
