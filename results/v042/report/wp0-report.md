# WP0 and WP4 on BEAR 0.4.2: report

Status: 2026-10-31, final. Every deterministic retrieval result of the paper has been rerun on BEAR 0.4.2 with all seven backends, Nemotron included. Each cell is compared with the published 0.1.10 value and with a 0.1.10 control run on the same vectors, and every move is attributed. The Table 7 rows whose prompts changed were rerun on the executor. The results are in the artifacts repo under `results/v042/` on `tist-r2`. The 0.4.0 interim report is kept beside this file as `wp0-report-v040-interim.md`.

## Summary of differences

What moves between the published 0.1.10 values and BEAR 0.4.2, and why. "Control" means public v0.1.10 rerun now on the same vectors. When the control reproduces the published value, the environment is not why a cell moved.

1. **External benchmarks (Tables 3, 5, 6).** No cell of any backend moves outside its CI. Most are identical, and the rest are the same at 3 decimals or move in the 4th.
   - **BGE, BGE-M3, Qwen3-0.6B, hash.** Identical per query under 0.1.10 and 0.4.2.
   - **Qwen3-4B.** Identical per query under 0.1.10 and 0.4.2 (GPU, bf16). It differs from the published values only through precision: 57 to 212 queries per cell, at most 0.003 in recall@5, inside every CI.
   - **BM25.** Moves 2 to 18 queries per cell, all at exact score ties. The cause is 0.4.2's tie order (priority, then id). `restore_tie_order` alone gives back every BM25 cell per query except ToolBench BM25 (no gov), where 11 queries still differ. With `restore_dropped_rows` as well, all 12 cells come back exactly. Once 0.4.2 keeps the zero-score rows, numpy sorts a longer array, and that changes how 0.1.10 broke ties there. `restore_dropped_rows` alone gives back nothing, and no other switch touches an external cell.
   - **Tag-order script fix.** MetaTool+Tags governed also moves through the fix to `load_metatool_queries_tagged`: BGE 47 queries, BGE-M3 23, Qwen3-0.6B 47, hash 121. 0.1.10 moves the same way under the fix, so this is a script fix, not a release change.
2. **Pet Sim (tab:retrieval, tab:governance-ablation, tab:decomposed-ablation, tab:alpha-sweep, tab:token-compare, the Pet Sim column of tab:reranker).** These tables move, 48 cells outside their CIs. Every move is attributed:
   - **Pure Similarity** rises sharply (hash 0.481 to 0.707, BGE 0.155 to 0.496 strict F1). `restore_ungated_pool` alone gives the published values back: 0.4.2 filters the ungated pool by the gate.
   - **No-tag F1 of the four dense backends** falls to 0.653 (from 0.701 to 0.789). `restore_ungated_pool` gives it back (BGE).
   - **The mandatory guarantee**, which has no switch, causes these, and no switch gives them back, alone or all together:
     - Full-governance F1 rises 0.004 to 0.015 on every backend.
     - Mandatory only rises up to 0.10.
     - α = 0 and "− priority weighting" rise 0.07 to 0.10 on the dense backends.
     - The reranker table's BEAR governed Pet Sim row goes from 0.653 to 0.668.
     - Tokens per query fall 1 to 7.

     0.4.2 returns all 3 safety rules for every query. 0.1.10 dropped one or more for some queries (per-query table below).
   - **α = 1.0** comes back with `restore_tie_order`.
3. **Disclosed error in the published results: the Qwen3-4B alpha tail is hash.** In `results/alpha_sweep_qwen3-4b.json` the cells for α = 0.7, 0.9 and 1.0 (0.843, 0.830, 0.830) equal the hash backend exactly, value and CI. 0.1.10 fell back to hash embeddings silently. The published log stops at "[6/8]", and the July 0.1.10 rerun log ends in a CUDA cuBLAS error in the same sweep. With the real model, 0.1.10 and 0.4.2 both give 0.649, 0.649 and 0.647 to 0.649. The manuscript's statement that Qwen3-4B peaks at α = 0.7 (lines 1447 and 2055) is an artifact. A systematic audit of every table file found no other case (section "Hash-fallback audit").
4. **Disclosed limit: the published BM25 tie order cannot be reproduced, even under 0.1.10.** 0.1.10 ranks with numpy's unstable `argpartition` and `argsort`. Their tie order depends on the numpy build and the CPU, not on the hash seed. The published Table 7 retrieval ran on an ARM machine (NVIDIA GB10). Here, on x86 with AVX-512, the regenerated 0.1.10 lists differ from the published per-query arrays in 8 governed queries (NDCG) and 4 ungated (NDCG, one also in recall), all at exact score ties. 0.4.2 orders ties by priority and then id, so it ranks the same on every machine. In the same way, the Qwen3-4B e2e lists can't be rebuilt exactly at bf16 (governed 14 recall and 65 NDCG queries, ungated 16 and 77), though they are identical under both versions.
5. **Table 7 (end to end).** The rows whose tool lists changed under 0.4.2 were rerun on the July executor and stay inside their July CIs. Those rows are BM25 governed and ungated, and BGE-M3 governed (one query, a tie at 5th place). The change is no larger than the executor drift that BGE controls show on identical lists (12 or 13 queries in tool correctness, not significant). Governed vs ungated for BM25 is +0.175 tool accuracy (d = 0.43), against +0.172 (d = 0.41) in July. Every other Table 7 row has identical lists, and Tables 8 and 9 use BGE only, so they stand.
6. **Unchanged:** Table 4, customer support (tab:token-efficiency, tab:semantic-advantage, novel departments), tool scaling and token savings, tab:transfer, ToolBench-IR + governance, and the ToolBench columns of tab:reranker.
7. **Nemotron (new seventh backend).** Governance helps on ToolBench (+0.094 recall@5) and MetaTool+Tags (+0.182). It hurts on base MetaTool (−0.070) and MetaTool+QueryTags (−0.101). The base-MetaTool loss comes from the fixed threshold 0.15, which bites Nemotron's narrow cosine scale.
8. **Smaller notes.**
   - The manuscript's "~82k prompt tokens" for the monolithic prompt is a cl100k (GPT-4 tokenizer) count. Mistral-Nemo's own tokenizer gives about 88.3k, and Gemma 4's about 91.9k. No July prompt was truncated.
   - tab:token-compare in the manuscript (5,057, 845, ...) comes from an older run than `results/governance_ablation.json` (5,029, 840, ...).

## Setup and provenance

- **BEAR 0.4.2.** Steps up to 2026-10-30 ran on the bear-dev candidate `9d085b4` (export `~/tist-evals/bear-9d085b4`). Steps from 2026-10-31 ran on the public tag `v0.4.2` (`0d0718a`, whose `bear/` equals `9d085b4` apart from line endings), installed from `~/tist-evals/bear-v0.4.2`. Those steps are the Qwen3-4B GPU lanes, the e2e rerun and the mand-only rows. `verify_env.py` confirmed the installed package against the source each time. Every JSON carries `_provenance` with the source sha, the package hash, the version, the `WP0_*` settings and the encode batch cap.
- **BEAR 0.1.10 controls.** The public tag `v0.1.10` (`cdba217`) first on PYTHONPATH, same Python and libraries.
- **0.4.0 record.** The earlier 0.4.0 run (bear-dev `10730c8`) is in `results/v040/`.
- **Same vectors for both versions.** A cache at the `SentenceTransformer.encode` boundary is keyed on model, device, dtype, threads, texts and arguments, batch size included. Both versions embed byte-identical texts, so each control sees the very same vectors as its 0.4.2 run.
- **Attribution.** 0.4.2's legacy switches (`Config.restore_*`) are set through sitecustomize `WP0_BEAR_LEGACY`: one at a time, all at once, and `tie_order` with `dropped_rows` together. The switches are `ungated_pool`, `below_threshold`, `ranked_resolution`, `removed_acting`, `pool_by_k`, `unchecked_requires`, `flat_backfill`, `dropped_rows` and `tie_order`.
- **Machines and limits.** Everything ran in WSL under `~/bin/tist-capped` (systemd scopes in `tist.slice`, no swap).
  - Lexical and Nemotron steps ran at 8G or less, and dense CPU steps at 20G. Local models ran on the CPU (batch 4, 12 threads), one dense lane at a time.
  - Qwen3-4B on Tables 3, 5 and 6 and its lists ran on the GPU in bf16, under an 11.2 GiB allocator cap, gated at 67,000 MiB to start and 80,000 to stop. Card peaks were 72,100 to 78,133 MiB.
  - No paid API was called.
- **Nemotron.** `RemoteEmbedder("http://localhost:8360")`, identity from `/health` (`nvidia/llama-nemotron-embed-vl-1b-v2`, 2048 dimensions), batches of at most 16 texts, a response cache, no retries needed. 8360 got no embedding requests while the grid and the GPU steps ran.
- **Guards.** `assert_not_hash` fails any dense run whose embedder is in hash mode, and 0.4.2 itself raises on a failed model load. Three incidents, all handled:
  - Decomposed Qwen3-4B was killed at the 20G cap (rc 143): ITR's encoder evicted the shared model, and a second 16 GB copy loaded. It was rerun with two models kept.
  - The first Qwen3-4B GPU lane ran at encode batch 8 and hit OOM inside its own 11.2 GiB cap on the longest ToolBench documents (about 3,000 tokens). Three rows on each version and the ToolBench lists were rerun at a fixed batch of 2. The probe measured 9.19 GiB reserved on the two longest passages.
  - Base MetaTool governed was rerun at batch 2 too, so the governed and ungated pair share a batch size. The batch-8 row is kept as a superseded record.

  MetaTool+Tags and +QueryTags (Qwen3-4B) stayed at batch 8, and each of those pairs uses one batch size.

## Comparison by table

The full list of 626 cells, with CIs, the 0.1.10 control, query counts and the switches that restore each cell, is in `results/v042/compare/compare.md` and `compare.json`.

| Table | Identical | Same at 3 dp | Changed (in CI) | Changed, outside CI | Not run |
|---|---|---|---|---|---|
| Table 3 | 26 | 6 | 2 | 0 | 2 (Qwen3-4B mand-only) |
| Table 5 | 24 | 9 | 1 | 0 | 2 |
| Table 6 +Tags | 19 | 12 | 3 | 0 | 2 |
| Table 6 +QueryTags | 26 | 6 | 2 | 0 | 2 |
| Table 4 | 27 | | | | |
| tab:governance-ablation (a) | 26 | | 15 | 4 | |
| tab:governance-ablation (panels) | 63 | | 17 | 16 | |
| tab:token-compare | 4 | | 6 | | |
| tab:decomposed-ablation | 17 | | 12 | 6 | |
| tab:alpha-sweep | 12 | | 14 | 14 | |
| tab:retrieval | 12 | | 4 | 8 | |
| customer support (3 tables, 2 text blocks) | 102 | | | | |
| tab:tool-scaling, tab:token-savings | 38 | | | | |
| tab:transfer, ToolBench-IR + governance | 10 | | | | |
| tab:reranker and contrasts | 53 | | 10 | | |

Nemotron has no published cells, so its 16 cells are reported separately below. Qwen3-4B mand-only was not run: it needs the GPU, and these rows equal the governed row on base MetaTool and are 0 on the tag benchmarks for every other backend.

All 48 cells outside a CI are Pet Sim cells, and every one is attributed (Summary, item 2). "Changed (in CI)" on the external tables means BM25 tie order, the tag-sort fix, or Qwen3-4B precision.

## Mandatory finding, per query

Pet Sim, k = 10, governance-ablation configurations (α 0.3, threshold 0.3). "Safety present" counts the 3 mandatory rules (`constraint-no-aggression`, `safety-boundaries`, `safety-reasonable-response`) in each output. The per-query CSVs are `results/v042/mandatory/mandatory_table_{lex,dense,q4b}.csv`.

| Backend | Full governance: queries missing a rule under 0.1.10 (Standard, Complex) | Mandatory only: queries missing a rule under 0.1.10 (Standard, Paraphrase, No-tag, Complex) | 0.4.2 |
|---|---|---|---|
| BM25 | 7, 3 | 26, 25, 31, 32 | none |
| Hash | 3, 2 | 33, 25, 8, 28 | none |
| BGE | 7, 3 | 0, 3, 0, 0 | none |
| BGE-M3 | 7, 4 | 0, 0, 0, 0 | none |
| Qwen3-0.6B | 7, 4 | 10, 21, 3, 20 | none |
| Qwen3-4B | 7, 3 | 18, 17, 1, 14 | none |

- 0.4.2 returns all 3 safety rules for every query at both levels and on every backend. Full governance on Paraphrase and No-tag misses no rule on either version.
- Under 0.1.10 the rule most often missing is `constraint-no-aggression`, then `safety-boundaries`, then `safety-reasonable-response`.
- Output sizes are unchanged per query, so 0.4.2 swaps a non-safety item for the missing rule.
- No legacy switch gives back the 0.1.10 counts, alone or all together, on any backend. This matches the point the response letter concedes to R2.

## Hash-fallback audit

BEAR 0.1.10 falls back to hash embeddings when a dense model fails to load, with only a log line. Its hash embedding fills only the first 32 dimensions and takes no prefix, so a fallback gives exactly what the hash backend gives, whatever the model. A dense cell that equals the hash cell of its condition (value and CI, or the per-query array) is therefore a fallback.

The audit (`evals/wp0_v040/fallback_audit.py`, full table in `results/v042/compare/fallback_audit/fallback_audit.md`) covered:
- every published result file behind a manuscript table, on the artifacts repo's main branch (`6159b0b`)
- comparators: the file's own hash cells, or else a rerun of the same script on 0.1.10 with every model load refused, which takes the fallback. The ITR library's own silent fallback ("Using fallback embeddings") is covered the same way.
- all 104 published logs and outputs
- this run's own control logs on 0.1.10

Result:
- **One real case:** the Qwen3-4B alpha tail (Summary, item 3). The 0.4.2 run replaces it.
- **Four matches carry no information:**
  - ITR-hybrid paraphrase F1, where every governed dense backend gives the same 0.637
  - `scalability_results.csv` and `eval_tool_scaling_output.txt`, where real BGE on 0.4.2 gives the same values
  - 112 all-zero mand-only arrays
- **Nothing else** in Tables 3 to 9, the other Pet Sim tables, customer support, transfer or the reranker.
- **Tables 8 and 9** store no retrieval arrays. Hash retrieval puts a gold API in the prompt for only 26.6% of queries, so it cannot produce their BEAR rows (0.67 to 0.86).
- **This run's 0.1.10 control logs (35):** the only failures are the two batch-8 GPU OOM attempts (`tb_qwen4b_v0110`, `e2e_q4b_v0110`). Their skipped rows were rerun at batch 2. None of them took a fallback.

## End-to-end (Tables 7 to 9)

**Lists, 0.4.2 vs 0.1.10.** Rebuilt from the top-5 lists with the committed e2e loader on the same vectors:

| Condition | Ordered top-5 differs, 0.4.2 vs 0.1.10 | Set differs | 0.4.2 vs published arrays (recall, precision, NDCG) |
|---|---|---|---|
| BEAR+BGE (gov), BGE (no gov) | 0, 0 | 0, 0 | 0, 0, 0 |
| BEAR+BGE-M3 (gov) | 1 (query 216) | 1 | 1, 1, 1 |
| BGE-M3 (no gov) | 0 | 0 | 0, 0, 0 |
| BEAR+Qwen3-0.6B (gov), Qwen3-0.6B (no gov) | 0, 0 | 0, 0 | 0, 0, 0 |
| BEAR+Qwen3-4B (gov), Qwen3-4B (no gov) | 0, 0 | 0, 0 | 14, 14, 65 and 16, 16, 77 (precision) |
| BEAR+Hash (gov) | 0 | 0 | 0, 0, 0 |
| BEAR+BM25 (gov) | 95 | 32 | 1, 1, 8 |
| BM25 (no gov) | 84 | 21 | 0, 0, 5 |

- Every changed list swaps tools with exactly equal scores. BGE-M3's query 216 ties at 5th place (similarity 0.6096), and 0.4.2 picks `/paragraph` over the gold `/words`.
- For BM25, `restore_tie_order` gives back the governed lists. `restore_tie_order` with `restore_dropped_rows` gives back the ungated ones (0 of 1,100).
- The lists do not depend on the hash seed.

**Executor rerun (2026-10-31).**
- Executor: Mistral-Nemo-Instruct-2407 12B Q4_0 on the same Ollama (0.40.13, at 127.0.0.1:11434 from WSL), tag `mistral-nemo-32k`. That tag is the July GGUF layer `b559938ab7a0` with `num_ctx` 32768.
- Request as published: temperature 0, max_tokens 100, json_schema enum.
- 1,100 calls per row, 0 errors. Ollama's prompt_tokens peaked at 511.
- Card: 66,276 MiB before loading, 78,575 to 78,748 before each row.
- The model unloaded at 17:46:42 UTC. `/api/ps` then listed 0 models, and the card read 66,117 MiB.

| Row | Tool acc now [95% CI] | Tool acc July | Exact acc now [95% CI] | Exact acc July | Queries changed vs July (tool / exact) | McNemar p |
|---|---|---|---|---|---|---|
| BEAR+BM25 (gov) | 0.753 [0.727, 0.778] | 0.751 | 0.675 [0.647, 0.703] | 0.666 | 10 / 27 | 0.75 / 0.12 |
| BM25 (no gov) | 0.577 [0.547, 0.606] | 0.579 | 0.527 [0.498, 0.556] | 0.527 | 10 / 14 | 0.75 / 1.0 |
| BEAR+BGE-M3 (gov) | 0.784 [0.759, 0.807] | 0.779 | 0.715 [0.688, 0.742] | 0.706 | 7 / 22 | 0.13 / 0.053 |
| BEAR+BGE (gov), drift control | 0.793 [0.769, 0.816] | 0.789 | 0.725 [0.698, 0.750] | 0.716 | 12 / 21 | 0.39 / 0.078 |
| BGE (no gov), drift control | 0.678 [0.650, 0.705] | 0.674 | 0.620 [0.591, 0.648] | 0.615 | 13 / 18 | 0.27 / 0.24 |

- The BGE controls have lists identical to July's, so their changes are executor drift. That covers the Ollama build and the server state, with the same weights. The drift is 12 or 13 queries in tool correctness and 18 to 21 in exact correctness, with no significant change.
- The BM25 and BGE-M3 rows change about as much as the controls, even though 95 and 84 BM25 prompts changed.
- Governed vs ungated:
  - BM25: tool +0.175 (d = 0.43, p = 5e-42), exact +0.147 (d = 0.35). July: +0.172 (d = 0.41) and +0.139.
  - BGE: tool +0.115 (d = 0.30), exact +0.105 (d = 0.26). July: +0.115 and +0.102.
- Qwen3-0.6B, Qwen3-4B and BGE-M3 ungated keep their July runs, since their lists are unchanged.
- For the manuscript's Table 7, using paired t on the per-query outputs with d = mean(diff) / sd(diff):
  - BEAR+BGE-M3 (gov) rerun vs BGE-M3 (no gov) from July: tool Δ +0.099 (d = 0.26, p = 1.6e-17), exact Δ +0.099 (d = 0.25, p = 2.0e-16). July had tool +0.095 (d = 0.25) and exact +0.090.
  - BEAR+BM25 (gov) vs BM25 (no gov), both rerun: tool Δ +0.175 (d = 0.43, p = 5.0e-42), exact Δ +0.147 (d = 0.35, p = 1.6e-29).
  - Executor drift on the BGE controls: the largest absolute change against July is 0.0045 in tool accuracy (BGE no gov) and 0.0082 in exact accuracy (BEAR+BGE gov). The governed control changed 12 queries in tool and 21 in exact correctness, and the ungated control 13 and 18.
- Tables 8 and 9 use BEAR+BGE only and stand.

**Truncation check (July).** Counted with Mistral-Nemo's own tokenizer in its chat format (`e2e_prompt_tokens.py`):
- Retrieval prompts are at most 631 tokens over every list. A bound over any 5 tools is 718, below 2,048, Ollama's smallest default ever.
- The monolithic prompt is at most 88,420 tokens single-turn and 88,494 ReAct, against the logged window of 131,072.
- Gemma 4's tokenizer gives at most 91,855 against its logged window of 262,144.
- No July prompt was truncated.

## Nemotron rows

`nvidia/llama-nemotron-embed-vl-1b-v2` (2048 dimensions) through `bear.remote_embedder.RemoteEmbedder`, BEAR 0.4.2, k = 5, the same threshold (0.15) and priority weight as the other backends.

| Benchmark | Condition | Recall@5 [95% CI] | NDCG@5 [95% CI] | Δ recall, governed − ungated (d, p) |
|---|---|---|---|---|
| ToolBench | BEAR+Nemotron (gov) | 0.762 [0.742, 0.781] | 0.722 [0.703, 0.740] | +0.094 (d = 0.39, p = 1.6e-36) |
| ToolBench | Nemotron (no gov) | 0.668 [0.647, 0.690] | 0.631 [0.610, 0.651] | |
| MetaTool | BEAR+Nemotron (gov) | 0.745 [0.739, 0.751] | 0.651 [0.645, 0.656] | −0.070 (d = −0.26, p < 1e-300) |
| MetaTool | Nemotron (no gov) | 0.815 [0.809, 0.820] | 0.699 [0.694, 0.704] | |
| MetaTool+Tags | BEAR+Nemotron (gov) | 0.986 [0.984, 0.987] | 0.931 [0.929, 0.934] | +0.182 (d = 0.47, p < 1e-300) |
| MetaTool+Tags | Nemotron (no gov) | 0.804 [0.799, 0.809] | 0.690 [0.684, 0.695] | |
| MetaTool+QueryTags-top5 | BEAR+Nemotron (gov) | 0.703 [0.697, 0.709] | 0.612 [0.606, 0.618] | −0.101 (d = −0.21, p = 1.9e-207) |
| MetaTool+QueryTags-top5 | Nemotron (no gov) | 0.804 [0.799, 0.809] | 0.690 [0.684, 0.695] | |

- On base MetaTool the fixed threshold of 0.15 leaves 6,670 governed queries with fewer than 5 results. Nemotron's cosine scale is narrow: top-1 similarity has a median of 0.235 and a 5th percentile of 0.139.
- At threshold 0, governed recall is 0.802 and no query returns fewer than 5 (`diag_nemotron_threshold.json`). The threshold was left as published for comparability.

## WP4

All seven backends, BEAR 0.4.2, k = 1 to 50 (`results/v042/wp4/`, with `summary.md`).

Method:
- Recall@k curves with joint bootstrap 95% CIs (10,000 resamples, seed 42), governed and ungated.
- Paired differences at every k: bootstrap CI and p, paired t, paired Cohen's d.
- The k and the prompt tokens needed to reach recall 0.80, 0.90 and 0.95, with joint bootstrap CIs.
- Per-query k at full recall (Wilcoxon), and tokens at k = 5.
- Per-query arrays (`*_recall_at_k.npz`, `*_tokens_*.npz`).
- Tokens are counted two ways. cl100k counts the e2e prompt on ToolBench and BEAR's composed content on MetaTool+Tags. Mistral-Nemo's tekken tokenizer counts the k = 5 chat prompts and the monolithic prompt.

**ToolBench** (1,100 queries, 3,225 tools; tokens are the e2e prompt):

| Backend | Recall@5 gov / ungated | Δ@5 [95% CI], d | k for 0.80, gov / ungated | k for 0.90, gov / ungated | k for 0.95, gov / ungated | Tokens at recall 0.80, gov / ungated |
|---|---|---|---|---|---|---|
| BGE | 0.688 / 0.574 | +0.114 [+0.099, +0.130], 0.43 | 11 [10, 12] / 31 [27, 37] | 26 [23, 30] / >50 | >50 / >50 | 391 [360, 422] / 971 [859, 1,135] |
| BGE-M3 | 0.711 / 0.601 | +0.110 [+0.095, +0.126], 0.42 | 10 [9, 12] / 27 [22, 32] | 25 [22, 29] / >50 | 46 [41, >50] / >50 | 350 [322, 399] / 820 [687, 955] |
| Qwen3-0.6B | 0.771 / 0.694 | +0.077 [+0.064, +0.090], 0.36 | 6 [6, 7] / 11 [10, 13] | 15 [13, 18] / 38 [30, 45] | 29 [25, 34] / >50 | 254 [251, 282] / 384 [356, 436] |
| Qwen3-4B | 0.754 / 0.682 | +0.072 [+0.059, +0.085], 0.33 | 7 [6, 8] / 13 [10, 15] | 15 [13, 17] / 40 [32, >50] | 27 [23, 32] / >50 | 272 [247, 297] / 419 [352, 468] |
| Nemotron | 0.762 / 0.668 | +0.094 [+0.080, +0.108], 0.39 | 7 [6, 8] / 15 [13, 18] | 16 [14, 18] / 45 [36, >50] | 28 [25, 32] / >50 | 286 [259, 315] / 526 [467, 610] |
| BM25 | 0.612 / 0.468 | +0.144 [+0.129, +0.159], 0.58 | 18 [16, 21] / >50 | 41 [36, 47] / >50 | >50 / >50 | 719 [647, 814] / not reached |
| Hash | 0.151 / 0.016 | +0.134 [+0.119, +0.150], 0.51 | >50 / >50 | >50 / >50 | >50 / >50 | not reached |

**MetaTool+Tags** (21,111 queries, 199 tools; tokens are BEAR's composed content):

| Backend | Recall@5 gov / ungated | Δ@5, d | k for 0.80 | k for 0.90 | k for 0.95 | Tokens at recall 0.80, gov / ungated |
|---|---|---|---|---|---|---|
| BGE | 0.981 / 0.723 | +0.258, 0.59 | 2 / 9 | 2 / 25 | 4 / 49 | 222 / 1,791 |
| BGE-M3 | 0.972 / 0.724 | +0.249, 0.58 | 2 / 10 | 3 / 29 | 4 / >50 | 152 / 1,964 |
| Qwen3-0.6B | 0.976 / 0.870 | +0.107, 0.34 | 1 / 3 | 2 / 8 | 3 / 23 | 83 / 352 |
| Qwen3-4B | 0.987 / 0.902 | +0.085, 0.31 | 1 / 2 | 2 / 5 | 3 / 14 | 83 / 210 |
| Nemotron | 0.986 / 0.804 | +0.182, 0.47 | 1 / 5 | 2 / 16 | 3 / 39 | 80 / 743 |
| BM25 | 0.911 / 0.402 | +0.509, 1.02 | 3 / >50 | 5 / >50 | 7 / >50 | 454 / not reached |
| Hash | 0.736 / 0.071 | +0.664, 1.41 | 7 / >50 | 10 / >50 | 13 / >50 | 680 / not reached |

**Prompt size.**
- The monolithic ToolBench prompt is 3,225 tools: 82,298 cl100k system tokens, or about 88,277 Mistral-Nemo chat tokens per query (the paper's "~82k" is the cl100k figure).
- At k = 5 the Mistral-Nemo chat prompts average 224 to 316 tokens per condition, so the monolithic prompt is about 280 to 390 times larger.

**Checks.**
- Every k = 50 list reproduces its k = 5 run per query. The largest difference is 2.4e-8, which is float32 rounding.
- The nesting check found 0 mismatches (200 sampled queries, 12 values of k, every backend).
- The e2e prompt token count is additive over lines (300 checked, 0 mismatches).
- Governed lists are shorter than 50 when the gated set is smaller (260 ToolBench queries and nearly every MetaTool+Tags query), so their curves stay flat past the gated set.
- Qwen3-4B lists use encode batch 2 on ToolBench and batch 8 on MetaTool+Tags, each matching its k = 5 run.

## How to rerun

Everything runs in WSL from clones of the artifacts repo's `tist-r2` branch. Every process goes through `~/bin/tist-capped`.

1. **Environment.** A Python 3.12 venv with BEAR 0.4.2 installed (`~/.venvs/tist-evals`), the public v0.1.10 tag at `~/tist-evals/bear-v0110`, and HF models cached offline.
2. **Lanes.** `evals/wp0_v040/relaunch_042.sh LANE ...` makes or syncs the clone for a lane and starts it as a capped user service. The runner is `evals/wp0_v040/run_wp0_v040.sh`. Its header documents the step kinds, the versions (`v042`; `v042L` with `WP0_BEAR_LEGACY`; `v0110`; `v0110F` with model loads refused), the caches and the guards. A step with a `.done` file is skipped.
   - `lex042`: BM25 and hash, every table
   - `attrpet042`, `attrtb042`, `pair042`, `e2eattr042`: switch attribution
   - `nemo042`: Nemotron
   - `dense042`, then `manddense042` (started on its own by `after_dense042.sh`), then `mandonly042`: local models on the CPU
   - `mand042`: the lexical mandatory table
   - `fallback0110`: the hash-fallback comparators
   - `gpuq4b042`, `gpuq4b042fix`, `gpuq4b042gov`: Qwen3-4B on the GPU behind the card gates
   - `e2erun`: the Table 7 executor rerun behind the card gates
3. **Analysis.**
   - `compare_042.py`
   - `table_mandatory.py`
   - `fallback_audit.py` and `audit_md.py`
   - `merge_wp4_lists.py` and `wp4_token_efficiency.py` (summary: `wp4_summary.py`)
   - `e2e_list_diff.py`, `e2e_vs_published.py` and `e2e_prompt_tokens.py`
   - `probe_q4b_batch.py`
4. **Assembly.** `assemble_v040.py --root ~/tist-evals/wp0-v042 --repo <repo> --ver v042 --extra ...` copies each finished step's outputs, logs, lists, WP4 and the comparison into `results/v042/`. Files over 5 MB are stored gzipped, and `MANIFEST.json` lists every file with the sha256 of its original content.

## Files

- **Artifacts repo, `tist-r2` (not pushed).** `evals/wp0_v040/` holds the scripts. `results/v042/` holds:
  - per-step results: `v042/`, `v042L/`, `v0110/`, `v0110F/`
  - `logs/`, `lists/` (e2e and WP4), `wp4/`, `compare/` (with `fallback_audit/`)
  - `mandatory/`, `e2e_checks/`, `diag/`, `e2e_rerun/`, `report/`
  - `MANIFEST.json`

  The WP4 k = 50 lists for MetaTool+Tags (77 MB of binary arrays that don't compress, 14 files) are not committed. `MANIFEST.json` lists their sha256, and they stay in WSL at `~/tist-evals/wp0-v042/wp4_lists_final/metatool-tags/`. No committed file is over 10 MB, and files over 5 MB are stored gzipped. `results/v042/` is 104 MB.
- **WSL, `~/tist-evals/wp0-v042/`.** Clones, stage, logs, caches.
- **Scratchpad.** This report, `wp0-report-v040-interim.md`, `compare_partial/`, `tools/`.
