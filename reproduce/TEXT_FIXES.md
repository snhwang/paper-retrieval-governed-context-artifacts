# Text fixes for the manuscript

Numbers in `sample-manuscript.tex` that no script produces, because the text is stale, the number is a prose estimate, or no data exist. A few are close to a computed value but do not match it. Each entry gives the location, the current text, what the files say and a proposed change. Nothing here edits the manuscript. Line numbers refer to the `.tex` as of 2026-10-31.

The checks below were made on the committed files with `collect.py`. Your runs give the final values, and `numbers/numbers.md` lists them.

## What became of each entry (23 Nov 2026)

This file records the text of 31 Oct 2026. Every entry is settled in the revised manuscript as built on 23 Nov 2026. The entries below keep their old wording, section numbers and line numbers.

1. Changed as proposed. Related Work says "NDCG@5 of 0.89 to 0.93 on the dense backends".
2. The abstract no longer has the sentence. It reports the mandatory-coverage test instead (recall 1.000 against 0.000 without injection).
3. The latency sentence was removed.
4. The ms/query column and its caption sentence were removed.
5. Changed as proposed ("in a single offline pass").
6. Changed, with the values of the November rerun of that run. The text says 96% for the right tool, 83% with the right endpoint, and "about fivefold".
7. The text no longer quotes this p value. It gives the recalls with their intervals.
8. Changed as proposed ("about 280 to 370 times", with Mistral-Nemo's tokenizer for both prompts).
9. Changed to 0.905 (now Supplement Table S2).
10. The sentence was replaced. The section "Use of Generative AI" names the kit.
11. Changed as proposed.
12. The sentence was removed.

The values under "Checked and matching" were computed on the files of the July and August 2026 runs. The reruns of November 2026 replaced the end-to-end values among them. The text now gives 3.3× and 4.1×, d = 0.89 to 1.04, and for the hash row against the monolithic row a difference of +0.032 with p = 0.048 and d = 0.06. McNemar's p for BEAR+Qwen3-0.6B against BEAR+Qwen3-4B is 0.36. The numbers file of the author's run lists the current values (items XE2Ea and XE2Eb).

The five values that waited for the author's run of `70_assemble.sh` are now checked:
- 14 sanitized names collide across 36 endpoints, which hold 21 of the 2,629 gold query-API pairs. The text said 22 endpoints and was changed to 36.
- BEAR v0.4.2 has eight tests in `TestEmitToolSummary`.
- The tool summary adds 13.0 to 17.0 tokens per admitted tool. The text said "roughly twenty" and was changed to "roughly 13 to 17".
- The MetaTool split is 20,614 single-target and 497 multi-target queries.
- No gold API of the 2,629 is gated out.

## Stale or unsupported

1. **Related Work, L297.** "yielding NDCG@5~=~0.905 without fine-tuning or outcome data."
   - No result file has 0.905. The governed MetaTool+Tags NDCG@5 under BEAR 0.4.2 is 0.903 (BGE) to 0.931 (Nemotron), and 0.928 for Qwen3-4B (Table 9).
   - Change to "yielding NDCG@5 of 0.89 to 0.93 on the dense backends (Table~\ref{tab:metatool-tags-results}) without fine-tuning or outcome data." Or drop the number.

2. **Abstract, L182.** "Mandatory injection of safety-tagged instructions adds no F1 once the gate admits them".
   - Table 17 (0.4.2) shows it adds 0.010 to 0.015 F1 on every backend (p 0.01 to 0.03).
   - Change to "Mandatory injection of safety-tagged instructions adds 0.010 to 0.015 F1 once the gate admits them".

3. **Section 4.5, L1193.** "Retrieval latency remains in the 4.2--10.4\,ms range (p95) even at $N{=}500$."
   - No file holds these values. The published CSV had p95 4.39 to 14.36 ms. The 0.4.2 run gives p95 0.37 to 3.28 ms (CPU, with an embedding cache). Timings depend on the machine and the cache.
   - Quote instead your run's p95 range from `numbers.md` (item T13, `retrieval_p95_ms`) and name the machine, for example "Retrieval stays under X ms (p95) at $N{=}500$ on one workstation CPU." Or drop the sentence.

4. **Table 16 (tab:governance-ablation), ms/query column, caption L1317.**
   - The column is "as measured for the previous version", and no committed file matches it. The 0.4.2 run measured latency with an embedding cache, so its values are not comparable either.
   - Drop the column and the caption sentence. If latency matters, measure it once on purpose, on one machine, without the cache.

5. **Section 5.5, L1891.** "produces tags for 199 tools in under three minutes".
   - No log of the tag generation records its duration.
   - Change to "produces tags for all 199 tools in a single offline pass".

## Close to a computed value, but not equal

6. **Section 4.2 end-to-end text, L1045.** "the gold tool is present for just 2.2\% of queries ($n{=}24$), but on those queries it is selected 91\% of the time" and "degrade its discrimination by a factor of five".
   - In `evals/results/toolbench_e2e_scores_cap128_superseded.json` the gold tool is present for 24 queries (2.2%). The model picks the right tool in 23 of them (96%), and the right tool and endpoint in 21 (88%). No reading gives 91%.
   - 0.875 / 0.186 = 4.7 (exact accuracy), 0.958 / 0.251 = 3.8 (tool accuracy).
   - Change to "on those queries it selects the right tool 96\% of the time (88\% with the right endpoint)" and "degrade its discrimination about fivefold" (exact accuracy).

7. **Section 4.5, L1200.** "McNemar $p{>}0.48$".
   - The method of `evals/compute_petsim_stats.py`, which `collect.py` repeats from the CSV, gives p = 0.4795 at N = 100, 200 and 500, and p = 1.0 below. So p is just under 0.48.
   - Change to "McNemar $p{\geq}0.47$".

8. **Section 4.11, L1655.** "That is about 280 to 390 times the size of a $k{=}5$ prompt."
   - The ratio mixes tokenizers. It divides Mistral-Nemo's count of the monolithic prompt (88,277) by cl100k counts of the k = 5 prompts. With Mistral-Nemo's tokenizer for both, the k = 5 prompts average 240 to 316 tokens, which gives 279 to 368 times.
   - Change to "That is about 280 to 370 times the size of a $k{=}5$ prompt (Mistral-Nemo's tokenizer for both)."

9. **Table 23 (tab:transfer), L1844.** Qwen3-4B, MetaTool, prints 0.906.
   - The off-the-shelf rows came from a dict hardcoded in `evals/eval_backend_transfer.py` with BEAR 0.1.10 values. `collect.py` now takes them from the ungated rows of Tables 6 and 8. Under 0.4.2, Qwen3-4B MetaTool is 0.9054, so 0.905, as in Table 8. The other cells agree.
   - Change 0.906 to 0.905 (and move the bold if the column maximum changes). A Nemotron row (0.668, 0.815) could be added.

## Wording that points at the wrong place

10. **Section 4.13, L1700.** "The author additionally re-executed the full deterministic evaluation suite end to end and confirmed that it reproduces the committed result files under the pinned environment (\texttt{evals/verify\_rerun.py} ...)."
    - `evals/verify_rerun.py` checks the July reruns only.
    - Change to "The author ran every script that produces a result with the reproduction kit in the artifacts repository (\texttt{reproduce/}), which records each run and compares its outputs with the committed result files (\texttt{reproduce/verify.py})."

11. **Data and Code Availability, L1991.** "with a table-to-script map in its README".
    - Change to "with a map from every table, figure and in-text result to its script in \texttt{reproduce/MANIFEST.md}".

12. **Section 5.4, L1880.** "The mandatory-only condition retrieves nothing (Recall@5~=~0.000 ...)".
    - October ran the mand-only rows on five backends. `20_gpu_local_embeddings.sh` now adds Qwen3-4B, so six. Nemotron, the seventh, has no mand-only row.
    - Keep the sentence once your run gives 0.000 for Qwen3-4B, and add "on the six backends run". Or add a Nemotron mand-only step (not in the kit).

## Checked and matching

These numbers had no script. `collect.py` and `reproduce/derive/` now compute them, and on the committed files they match the text:
- 3.3× and 4.0× (3.27 and 3.98, BEAR+Qwen3-0.6B over monolithic)
- d = 0.86 to 1.01 (governed rows vs monolithic, exact accuracy)
- d = 0.60 to 1.01 (every non-hash row vs monolithic, exact accuracy)
- hash vs monolithic, Δ +0.024, p 0.13, d 0.05 (the bootstrap CI is [-0.006, +0.056] with seed 42, against [-0.007, +0.056] printed)
- McNemar p = 0.48 (BEAR+Qwen3-0.6B vs BEAR+Qwen3-4B, tool accuracy)
- 0.53 to 0.67, 80% (70 to 87%), 0.07 to 0.15 (Table 10 as printed)
- 2.2% (n = 24)

These depend on your run of `70_assemble.sh` (part derived) and are unchecked until then:
- "14 sanitized function names that collide across 22 endpoints"
- "Eight unit tests" (BEAR v0.4.2 has eight in `TestEmitToolSummary`, read from the file)
- "roughly twenty tokens per admitted tool"
- the 20,614 / 497 split
- "none of the 2,629"
