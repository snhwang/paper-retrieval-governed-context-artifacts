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

The paper used `Mistral-Nemo-Instruct-2407` 12B at **Q4_0 quantization, served by Ollama** on port 11434.

**Terminal 1 (Ollama):**

```bash
ollama pull mistral-nemo                                    # ~7 GB, one time
OLLAMA_CONTEXT_LENGTH=131072 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_HOST=0.0.0.0 ollama serve
```

`OLLAMA_CONTEXT_LENGTH` is not optional. The monolithic baseline injects all 3,225 tool schemas (~82k tokens), so the window must be ~131072. Unset, Ollama sizes the KV cache from *free* VRAM and reserves tens of gigabytes it never uses, starving the embedders the eval loads onto the same card. Set the variable in the same shell as `ollama serve`, and quit the Ollama tray app first or it keeps serving the old window. The eval preflights the prompt against the window and aborts if it is too small, so a wrong value fails loudly rather than truncating.

Under WSL, `localhost` is not the Windows loopback. If the eval runs in WSL and Ollama on Windows, add `OLLAMA_HOST=0.0.0.0` and use the host's LAN address.

`serve_mistral_nemo.sh` (vLLM, bf16, port 8355) is an alternative, but quantization is not output-preserving, so it will not reproduce Tables 7 and 8 exactly.

### Quick smoke test (50 queries, ~5 minutes)

**Terminal 2:**

```bash
python evals/eval_toolbench_react.py --max-queries 50
```

The script defaults to `http://127.0.0.1:11434/v1` and `--model mistral-nemo`, matching the paper. Pass `--base-url` / `--model` to override.

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

## ToolLLM retriever baseline on ToolBench (R1.4 / R3.5 / R3.7)

Runs ToolLLM's publicly released fine-tuned ToolBench retriever as a plain
no-governance backend on the identical ToolBench eval (same 3,225-API split,
same 1,100 queries, same Recall@5 / NDCG@5 / F1@5). Gives the same-metric,
same-split learned-retriever reference point the reviewers asked for.

    # downloads the ToolBench IR encoder on first run
    python evals/eval_toolbench_toolllm.py \
        --model ToolBench/ToolBench_IR_bert_based_uncased \
        --top-k 5 --output results/toolbench_toolllm.json

    # quick wiring check (no full corpus embed):
    python evals/eval_toolbench_toolllm.py --max-queries 50

Compare the reported Recall@5 against (same split/metric, already in the paper):
  BEAR+BGE oracle categories   0.679   (Table 3)
  BEAR+BGE inferred (best)     0.502   (Table 4)
  BEAR+BGE no governance       0.574   (floor)
Note: confirm the exact HF model id / access before the full run; override with
--model if ToolBench publishes under a different name or you use a local path.

### ToolBench-IR governance-composition follow-up (BEAR 0.1.10)

The baseline script also runs BEAR governance *on top of* the ToolBench-IR
encoder, to test whether the scope gate composes with a fine-tuned in-domain
retriever:

    python evals/eval_toolbench_toolllm.py \
        --model ToolBench/ToolBench_IR_bert_based_uncased \
        --top-k 5 --mode both \
        --output results/toolbench_toolllm_fixed.json

    # isolate the scale-free hard gate from the similarity floor:
    python evals/eval_toolbench_toolllm.py --mode governed --threshold 0.0

Result (BEAR 0.1.10): ToolBench-IR alone Recall@5 = 0.847 [0.832, 0.862];
BEAR governance + ToolBench-IR = 0.842 [0.826, 0.858] -- statistically
indistinguishable (overlapping CIs), and the gate excludes 0 of 2,629
ground-truth APIs (see diag_gate_coverage.py). Governance is recall-neutral on
a strong in-domain retriever and gates out zero correct tools.

    # verifies the hard gate admits every ground-truth API (no model needed):
    python evals/diag_gate_coverage.py

## Retrieval re-run on BEAR 0.1.10 (over-fetch fix) -- 2026-07-06

Background. While building the ToolBench-IR composition run we found that BEAR's
retriever depressed retrieval quality under a hard gate on large corpora. The
gate prunes the candidate pool in Step 3; with the fixed top_k*3 over-fetch, an
admissible item ranked just outside that window was recovered only by the
flat-priority backfill in Step 3.5 (final_score = priority/100 = 0.5), which on
a large single-category corpus outranked genuinely-similar matches whose cosine
was below ~0.5 and displaced them from the top-k. Fixed in bear 0.1.10
(retriever widens the over-fetch to the full corpus when a gate is active, so
the admissible set is ranked by real similarity; the backfill becomes a no-op).
See bear-dev commit "retriever: widen over-fetch when hard-gated".

Scope of the change. Only the (gov) conditions -- use_tags=True with scope
intact -- are affected, and only on tag-passing benchmarks (ToolBench,
MetaTool+Tags, MetaTool+QueryTags). The (no gov) rows (scope stripped) and the
(mand-only) rows (no context tags) engage neither the gate nor the injection and
are unchanged. Direction is one-way: gov rows can only rise or stay.

Install the fixed build into the eval env (deps already satisfied):

    uv pip install -e /path/to/bear-dev --no-deps
    python -c "import bear; print(bear.__version__)"   # expect 0.1.10

Full clean re-run (writes a new file so the pre-fix JSON is preserved for
diffing):

    python evals/eval_toolbench.py --top-k 5 --latex \
        --output results/toolbench_eval_v0110.json

Faster gov-only re-run (skips the unchanged no-gov / mand-only rows):

    python evals/eval_toolbench.py --top-k 5 \
        --backends "BEAR+BGE (gov)" "BEAR+BGE-M3 (gov)" \
                   "BEAR+Qwen3-0.6B (gov)" "BEAR+Qwen3-4B (gov)" \
        --output results/toolbench_eval_gov_v0110.json

Verification. Diff results/toolbench_eval_v0110.json against the pre-fix
results/toolbench_eval.json: every (no gov) and (mand-only) row must be
identical; only (gov) rows should move (upward or unchanged). Any movement in a
non-gov row indicates an unintended side effect and should be investigated
before updating the manuscript.

Note. The public bear release must be advanced to 0.1.10 (propagate the fix to
bear-public-prep, tag v0.1.10) and requirements.txt repinned to @v0.1.10 before
the artifacts are published, so a fresh clone reproduces these numbers.

## Mandatory-injection guarantee (isolated demonstration) -- BEAR 0.1.10

Why. Under BEAR 0.1.10 the widened gated over-fetch surfaces every
gate-eligible safety rule on the small Pet-Sim corpus, so the decomposed
ablation's mandatory-injection pathway no longer shows an effect (redundant
there). Mandatory injection is a guarantee, so it only shows an effect when
ordinary retrieval would otherwise MISS the instruction. This script isolates
that case with a scope-excluded safety rule (a required_tags gate the
adversarial queries never provide): ordinary retrieval cannot reach it at any
corpus size, and only mandatory injection surfaces it.

    # default: bge only
    python evals/eval_mandatory_injection.py

    # all five backends (Pet-Sim is tiny; still fast even for qwen3-4b):
    python evals/eval_mandatory_injection.py \
        --backends bge bge-m3 qwen3 qwen3-4b bm25

Expected (deterministic, backend-independent for the scoped columns):

    backend    | unscoped OFF unscoped ON | scoped OFF scoped ON
    bge        |        1.000       1.000 |      0.000     1.000
    bge-m3     |        1.000       1.000 |      0.000     1.000
    bm25       |        1.000       1.000 |      0.000     1.000

Reading. unscoped OFF ~= 1.0 (small corpus + no scope gate: ordinary retrieval
already finds the safety rule, so force-inclusion is redundant here). scoped
OFF = 0.0 (the scope gate excludes the rule from retrieval, independent of
corpus size or over-fetch width); scoped ON = 1.0 (only mandatory injection
surfaces it). The scoped column is the architectural guarantee in isolation.
No LLM; writes results/mandatory_injection.json with a reproducibility footer.

## Out-of-domain transfer of the ToolBench-fine-tuned retriever

Why. ToolBench-IR (ToolLLM's retriever) reaches Recall@5 = 0.847 on ToolBench
because it was fine-tuned there. This measures how it transfers to a corpus it
was NOT optimized for (MetaTool), against off-the-shelf encoders, to test the
claim that fine-tuned retrievers are corpus-specific (strong in-domain, weak
out-of-domain, needing per-corpus retraining) while off-the-shelf encoders +
governance generalize. No governance -- isolates retriever quality.

    # out-of-domain: the fine-tuned retriever on MetaTool
    python evals/eval_backend_transfer.py --corpus metatool

    # in-domain reference (should reproduce ~0.847)
    python evals/eval_backend_transfer.py --corpus toolbench

The script prints the off-the-shelf no-governance Recall@5 references inline
(MetaTool: BGE 0.723, BGE-M3 0.728, Qwen3-0.6B 0.871, Qwen3-4B 0.906). If
ToolBench-IR lands near or below the off-the-shelf encoders on MetaTool, that is
the generalization gap: fine-tuning does not transfer, whereas off-the-shelf +
governance does. Hypothesis, to be confirmed by the run -- not yet measured.

## Composite-score scale audit (Pet Simulation)

Why. BEAR ranks by score = (1-a)*cosine + a*(priority/100). cosine is raw
(~[-1,1]); priority/100 is [0,1]. On varying-priority corpora (Pet Sim) this
scale mix could let priority matter more than the nominal weight a implies.
External tables are immune (uniform priority => monotonic in cosine). This audit
re-ranks each query two ways -- raw cosine vs cosine rescaled to [0,1] -- and
reports whether F1 moves. Scores are recomputed externally; no bear change.

    python evals/eval_composite_scale_audit.py \
        --backends bge bge-m3 qwen3 qwen3-4b bm25

Preview (bge, indicative): at alpha=0.30 (the decomposed ablation's operating
point) raw vs normalized differ by ~0.004 F1 -- negligible, so the decomposed
numbers are robust. At alpha=0.10 they differ ~0.028 with ~23% reorder, because
normalization compresses cosine and thus shifts what alpha *means*. Takeaway:
the decomposed ablation (alpha=0.30) needs no change; the alpha-sweep's peak F1
is scale-invariant but the best-alpha coordinate is a convention of the raw
cosine scale. Keep raw cosine, document the choice.

## Multi-step ReAct on StableToolBench (Tier 1) -- setup

Purpose. A genuine multi-step reason-act-observe evaluation (unlike the
single-step tab:e2e-react), to test whether governance's advantage compounds
end to end: governed vs ungoverned BEAR retrieval feeding a ReAct agent on
ToolBench I2/I3 multi-tool tasks, scored by pass rate. Gated on the Tier-0
retrieval-level result (eval_compounding_coverage.py). See
PLAN_governance_compounding.md for the full plan. Scaffold:
evals/eval_stabletoolbench_react.py (four TODOs to fill against the sim server).

Machine layout.
  * agent LLM  : Mistral-Nemo via vLLM on the x86 main box (serve_mistral_nemo.sh)
  * sim server : StableToolBench simulated API server (on a Spark)
  * simulator  : Claude Sonnet 5 (Anthropic) for cache-miss API responses
  * judge      : Claude Sonnet 5 (Anthropic) for ToolEval SoPR/SoWR
  * retrieval  : BEAR governed vs ungoverned (this repo)

Dependencies.
  * Python (already in requirements.txt): anthropic, openai, python-dotenv.
    IMPORTANT: verify the installed anthropic SDK supports the claude-sonnet-5
    model id and the `thinking` parameter (adaptive thinking is on by default on
    Sonnet 5; the scaffold disables it for the simulator and leaves it on for the
    judge). Bump the SDK if a call rejects `thinking` or the model id.
  * External (NOT pip-installable from here): clone StableToolBench
    (github THUNLP-MT/StableToolBench), install ITS requirements, and download
    its cached API-response data artifact. The sim server and its config live in
    that repo; point its simulator client at Anthropic/Sonnet 5 rather than the
    default GPT-4.

.env (artifacts-repo .env, which the scaffold loads via load_dotenv):
    ANTHROPIC_API_KEY=...            # already present
    AGENT_BASE_URL=http://<main-box-ip>:8000/v1
    SIM_SERVER_URL=http://127.0.0.1:8080   # match the sim server's port

Setup order.
  1. Main box: bash serve_mistral_nemo.sh  (agent LLM).
  2. Spark: clone StableToolBench, install its requirements, download cached data.
  3. Configure + start its sim server with Sonnet 5 as the cache-miss simulator.
  4. MILESTONE: verify the server answers one sample API call. Everything
     downstream is blocked on this.
  5. Fill the scaffold TODOs (task loading, execute_tool, react loop, judge)
     against the live server, then prototype:
         python evals/eval_stabletoolbench_react.py --max-tasks 20
  6. Scale to the full I2/I3 set only after the 20-task prototype is clean.

Methodology caveat to disclose in the paper. Simulator and judge are Sonnet 5,
not GPT-4, so absolute pass rates are not comparable to the StableToolBench
leaderboard. The controlled comparison is governed vs ungoverned under the SAME
simulator and judge, so that choice cancels out.
