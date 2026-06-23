# `eval_governance_decomposed.py` — Runbook

This script produces the new **Table 14 (Decomposed Governance Ablation)** for the TIST revision. It addresses Reviewer 1 weakness #3 and Reviewer 4 #1 by isolating the contribution of each governance mechanism individually, in addition to the existing all-vs-none ablation already reported.

It also runs the off-the-shelf `instruction-tool-retrieval` library as a reference row (Reviewer 3 #5), with a prominent caveat that it is not a faithful re-implementation of the ITR paper's full pipeline.

## What it does

Starting from full governance, it switches off **one** governance mechanism at a time and measures the F1 drop on the 60-query standard Pet Sim test set. It also runs a separate 12-query adversarial-safety subset to characterize the mandatory-injection effect, which the standard distribution under-samples.

Conditions evaluated:

| # | Condition | What's switched off |
|---|---|---|
| 1 | Full governance | (baseline) |
| 2 | − required_tags | hard scope gate |
| 3 | − priority weighting | α = 0 (similarity-only ranking) |
| 4 | − conflict resolution | conflicts_with edges stripped |
| 5 | − mandatory injection | mandatory_tags = [] |
| 6 | No governance | all four off |
| 7 | ITR library (off-the-shelf) | optional reference row, ITR paper pipeline not reproduced |

For mandatory injection, the standard-query F1 effect is small because few queries activate safety. The adversarial-safety subset isolates the effect:

| Condition | Metric |
|---|---|
| Mandatory injection ON | safety-recall on 12 adversarial queries |
| Mandatory injection OFF | safety-recall on 12 adversarial queries |

## Requirements

```bash
# From inside the paper-retrieval-governed-context-artifacts repo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: ITR off-the-shelf comparison row
pip install instruction-tool-retrieval
```

If `instruction-tool-retrieval` is not installed, the script prints a warning and continues without the ITR row.

## How to run

**Default (multi-backend, recommended for the revision):**

```bash
cd /path/to/paper-retrieval-governed-context-artifacts
python evals/eval_governance_decomposed.py
```

Runs the same five backends used elsewhere in the paper: `bge`, `bge-m3`, `qwen3` (0.6B), `qwen3-4b`, `bm25`. Writes one JSON per backend plus a combined `results/governance_decomposed_all.json`, and prints a single combined LaTeX table at the end suitable for paste into the manuscript.

**Single backend (faster, for iteration):**

```bash
python evals/eval_governance_decomposed.py --backend bge
python evals/eval_governance_decomposed.py --backend bm25
python evals/eval_governance_decomposed.py --backend qwen3-4b
```

**Custom backend list:**

```bash
python evals/eval_governance_decomposed.py --backends bge bm25
```

**Custom output path (single-backend only):**

```bash
python evals/eval_governance_decomposed.py --backend bge --output results/governance_decomposed_bge.json
```

## What it prints

1. A startup block that auto-discovers the safety-tagged instruction IDs in the Pet Sim corpus.
2. Progress lines `[1/6] Full governance ...` etc., one per condition, plus `[+] ITR library` if available.
3. A per-condition standard-query table with mean F1, 95% bootstrap CI, Δ vs. full, Cohen's d, and a paired bootstrap p-value.
4. An adversarial-safety subset block showing safety-recall ON vs. OFF.
5. A ready-to-paste LaTeX `table` block — copy this into the manuscript at the location indicated in `revision-plan.md` Section E.9 (Section 4.8 "Decomposed Governance Ablation").
6. JSON output written to `results/governance_decomposed.json` (or wherever you point `--output`).

## Expected runtime (per backend)

- BGE-base: ~2 minutes (downloads BGE if first run)
- BGE-M3: ~3–4 minutes
- Qwen3-0.6B: ~3 minutes
- Qwen3-4B: ~6–10 minutes (largest model)
- BM25: ~30 seconds
- ITR off-the-shelf row: adds ~30 seconds per backend run

**Default multi-backend run: ~15–20 minutes total.** No GPU is required, but BGE/Qwen3 will use CUDA if available.

## What you need to enter

Nothing interactive — the script runs end-to-end. The default invocation runs all five backends in sequence and emits a combined LaTeX table at the end.

If you'd rather see one backend's result quickly first, run `--backend bge` for a ~2-minute sanity check, then run the multi-backend default once you're confident it works.

## Sanity-check expectations (from the June 23 BGE run)

For the BGE backend on Pet Sim standard queries, the actual measured values are:

| Condition | F1 [95% CI] | Δ vs. full | Cohen's d | p |
|---|---|---|---|---|
| Full governance | 0.780 [0.756, 0.806] | — | — | — |
| − required_tags | 0.522 [0.501, 0.541] | −0.258 | +1.91 | <0.0001 |
| − priority weighting | 0.778 [0.753, 0.804] | −0.002 | +0.13 | 0.63 (n.s.) |
| − conflict resolution | 0.774 [0.750, 0.799] | −0.006 | +0.32 | 0.01 |
| − mandatory injection | **0.418** [0.388, 0.450] | **−0.362** | +4.53 | <0.0001 |
| No governance | 0.162 [0.149, 0.177] | −0.618 | +5.80 | <0.0001 |
| ITR (off-the-shelf) | 0.182 [0.162, 0.203] | −0.598 | +4.72 | <0.0001 |

Key findings the multi-backend run is checking for robustness:

1. **`required_tags` and mandatory injection are the two dominant mechanisms** — together they account for the entire governance effect.
2. **Priority weighting and conflict resolution have minimal effect** on Pet Sim (likely because the corpus has few conflict edges and the default α=0.3 is close to the optimum).
3. **ITR off-the-shelf ≈ no-governance BGE** — confirms that retrieval-without-governance is the right comparison point.

If the BGE results above don't reproduce (e.g., full-governance F1 < 0.5), something is wrong — most likely the Pet Sim corpus didn't load, the safety-id discovery failed, or a backend model didn't download. Inspect the startup output for clues.

## How to share results

After running, share the printed output (especially the LaTeX block and the JSON summary). I will:

1. Drop the LaTeX block into `sample-manuscript.tex` at the new Section 4.8 location.
2. Update the response letter's "Reviewer 1 W3" and "Reviewer 4 #1" entries with the real numbers.
3. Cross-check the values against the discussion text I drafted (and rewrite if reality differs from expectations).
