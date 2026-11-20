# End-to-end reruns: plan

Status: version 1, 2026-11-20. It awaits Scott's approval. Under "Specs yes, gates no" (9 Nov 2026) and "Re-run anything questionable" (12 Nov 2026), this file is fixed before the runs. Its sha256 at approval is recorded in the paper repo's `revision-plan.md`.

## Why

Part of the paper's end-to-end results is kept from July and August 2026. That part is seven rows of Table 10, its monolithic row, and Supplement Table S1 with the ReAct numbers. Three things about these results are in question.
- They ran on BEAR 0.1.10, and the paper reports 0.4.2. One comparison in Table 10, the BGE-M3 gain, sets a November row against a July row.
- The Ollama version was not recorded, and neither were the model builds.
- No run record shows who launched them. The paper says that the author launched every script that produces a reported result.

Scott, 20 Nov 2026: "Let's rerun all the questionable items".

## What is rerun

Four parts. Each uses all 1,100 ToolBench test queries.

1. **Table 10, the ten retrieval rows.** BGE, BGE-M3, Qwen3-Embedding-0.6B, Qwen3-Embedding-4B and BM25, each governed and ungoverned, with single-turn selection by Mistral-Nemo. All ten run in one session, including the three that were already rerun in November.
2. **Table 10, the monolithic row.** All 3,225 tools in the prompt, single-turn selection by Mistral-Nemo.
3. **The ReAct scaffold on Mistral-Nemo.** One batch with three conditions: the scaffold on the monolithic prompt, the scaffold on the governed top 5, and governed single-turn selection.
4. **Gemma 4 12B and 31B.** The two scripts behind the Gemma columns of Supplement Table S1, `run_model_scaffold_nothink.sh` and `run_model_full1100.sh`, for each model. Then `grid_from_full1100.py` and `scaffold_vs_single.py`.

## Fixed before the runs

- **BEAR.** v0.4.2 (commit `0d0718a`).
- **Tool lists.** Part 1 reads the top-5 lists of the author's kit run on 0.4.2 (`results/v042/lists/e2e_v042/`). Parts 3 and 4 retrieve the governed top 5 with BGE inside the script, on 0.4.2.
- **Server and builds.** Ollama as installed on the workstation. Each run records the Ollama version and the model digest. It stops if the digest is not the one given here.
  - `mistral-nemo`, digest `e7e06d107c6c`, Q4_0. Part 1 uses the tag `mistral-nemo-32k` (digest `d79a1e80980f`), which is the same weights with a window of 32,768 tokens.
  - `gemma4:12b`, digest `4eb23ef187e2`, Q4_K_M.
  - `gemma4:31b`, digest `6316f0629137`, Q4_K_M.
- **Decoding.** As the paper describes it.
  - Mistral-Nemo runs at temperature 0, with its output constrained by a JSON schema, and with at most 100 output tokens in single-turn selection.
  - The Gemma models run at temperature 1.0, top-p 0.95 and top-k 64, with one draw per query. Native reasoning is off, or runs within 8,192 tokens.
- **Context window.** A prompt with all 3,225 tools needs a window of at least 131,072 tokens. The scripts check the served window before they start, and stop if it is too small.
- **Scoring and statistics.** Unchanged. They are exact accuracy and tool accuracy, 95% bootstrap confidence intervals, and McNemar's test for paired conditions.

## What differs from the July runs, on purpose

- BEAR 0.4.2 in place of 0.1.10.
- All ten rows of Table 10 run in one session, on one Ollama version.
- The 31B run with native reasoning is one pass over the 1,100 queries. July merged a pilot of 366 queries with a later run of 734.
- A fixed seed, 20261120, goes with every sampled request, which means the Gemma runs. July sent none.
- Every run is a job in Scott's queue with a stated purpose, and it writes a run record.

## What is reported

- Every rerun value replaces the July or August value. That holds in Table 10, in the text of Section 4.2, and in Supplement Section S1 with Table S1. No earlier end-to-end value stays in the paper.
- No row and no condition is dropped for its result.
- The text follows the numbers. Four statements now in the paper are at stake. Each is kept, weakened or removed by what the reruns show.
  1. Governed retrieval beats ungoverned retrieval end to end on every backend.
  2. Every governed configuration beats the monolithic prompt.
  3. The one-step scaffold lowers Mistral-Nemo's accuracy, and lowers it most on the monolithic prompt.
  4. No monolithic configuration of the Gemma models reaches governed accuracy, and governance narrows the spread between models.
- The Summary of Differences and the response letter say that the end-to-end results were rerun, and why.
- After the runs, the author's outputs replace the committed copies in `results/` and `evals/results/`, as was done for the other results on 20 Nov 2026. The July files remain in the repository's history.

## Order and cost

One job at a time, each queued by Scott.

| Part | Model time |
|:--|:--|
| 1. Table 10, ten rows | about 30 minutes |
| 2. Monolithic row | about 6 hours |
| 3. ReAct | about 8 hours |
| 4. Gemma, four runs | 4 to 9 hours each |

That is about 30 to 50 hours in all. The times of parts 2 to 4 are those of the July runs.

## Changes to the kit before the runs

- `evals/wp0_v040/e2e_rerun.py` and `reproduce/50_e2e_ollama.sh` gain the five rows they lack.
- A new step runs parts 2 to 4 on BEAR 0.4.2. It is `55_e2e_previous_version.sh` with the BEAR pin changed and the digests checked.
- `evals/eval_toolbench_react.py` gains an option that sends a seed.
- `reproduce/lib/paper_map.py` and `reproduce/collect.py` read the reruns for the items T10b, T10c, T11 and T12. Their status changes from "previous version" to "this revision".
- Each script gets a dry run before a job is handed over.

## Decisions for Scott

1. **Server.** Ollama with the builds above. His own serving scripts use vLLM. Ollama is planned because the July runs used it, the paper describes it, and the kit already drives it.
2. **Seed.** A fixed seed for the Gemma runs, as above, or none as in July.
3. **Scope.** All four parts.

## Changes

None yet.
