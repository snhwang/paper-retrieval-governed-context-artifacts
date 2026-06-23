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

The default invocation uses BGE-base (`BAAI/bge-base-en-v1.5`), which is the default backend in the rest of the paper:

```bash
cd /path/to/paper-retrieval-governed-context-artifacts
python evals/eval_governance_decomposed.py
```

To reproduce with a different backend (any key from `BACKEND_CONFIGS` in `eval_retrieval_backends.py`):

```bash
python evals/eval_governance_decomposed.py --backend bm25
python evals/eval_governance_decomposed.py --backend qwen3-4b
python evals/eval_governance_decomposed.py --backend bge-m3
```

To write the JSON results elsewhere:

```bash
python evals/eval_governance_decomposed.py --output results/governance_decomposed_bge.json
```

## What it prints

1. A startup block that auto-discovers the safety-tagged instruction IDs in the Pet Sim corpus.
2. Progress lines `[1/6] Full governance ...` etc., one per condition, plus `[+] ITR library` if available.
3. A per-condition standard-query table with mean F1, 95% bootstrap CI, Δ vs. full, Cohen's d, and a paired bootstrap p-value.
4. An adversarial-safety subset block showing safety-recall ON vs. OFF.
5. A ready-to-paste LaTeX `table` block — copy this into the manuscript at the location indicated in `revision-plan.md` Section E.9 (Section 4.8 "Decomposed Governance Ablation").
6. JSON output written to `results/governance_decomposed.json` (or wherever you point `--output`).

## Expected runtime

- BGE-base: ~3 minutes (downloads BGE if first run)
- BM25: ~30 seconds
- Qwen3-4B: ~6–10 minutes (largest model)
- ITR row adds ~30 seconds on top of any of the above

No GPU is required, but BGE/Qwen3 will use CUDA if available.

## What you need to enter

Nothing interactive — the script runs end-to-end. The only choice is `--backend`. For the manuscript table I recommend running BGE first (matches the rest of the paper) and including that as Table 14. If you want a sensitivity check that the conclusions are not backend-specific, also run BM25 and one Qwen3 variant and add a one-sentence note ("the same ordering of components holds for BM25 and Qwen3-4B").

## Sanity-check expectations

You should see roughly:

- **Full governance:** F1 in the 0.75–0.85 range (matches the existing eval_retrieval_backends.py output for BGE).
- **− required_tags:** large drop (Δ ≈ −0.25 to −0.40); should be the largest single decrement.
- **− priority weighting:** small drop (Δ ≈ −0.03); the existing α-ablation in `eval_retrieval.py` shows the system is robust to α in [0.3, 0.7].
- **− conflict resolution:** very small drop (Δ < 0.05); Pet Sim has few conflict_with edges.
- **− mandatory injection:** very small drop on standard queries (Δ < 0.05) — this is the expected null result. The adversarial subset is where the mandatory effect shows up; expect safety-recall to drop from ~1.00 to ~0.10–0.25 when mandatory is off.
- **No governance:** F1 should drop to ~0.10–0.20, matching panel (c) of the existing Table 12.
- **ITR (off-the-shelf):** F1 in the 0.65–0.80 range based on the prior `eval_retrieval_backends.py` output.

If any of these are wildly off (e.g., full governance F1 < 0.5), something is wrong — most likely the Pet Sim corpus didn't load, the safety-id discovery failed, or a backend model didn't download. Inspect the startup output for clues.

## How to share results

After running, share the printed output (especially the LaTeX block and the JSON summary). I will:

1. Drop the LaTeX block into `sample-manuscript.tex` at the new Section 4.8 location.
2. Update the response letter's "Reviewer 1 W3" and "Reviewer 4 #1" entries with the real numbers.
3. Cross-check the values against the discussion text I drafted (and rewrite if reality differs from expectations).
