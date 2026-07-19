# gemma4:31b vs Mistral-Nemo-12B: does scale/reasoning obviate governance?

Matched cross-model comparison on ToolBench tool selection. **Representative**
(stratified sample of 198 queries across all six ToolBench splits, seed 42) and
**matched** (Mistral-Nemo's saved per-query arrays subsampled to the identical
indices -- no Mistral re-run). Gemma 4 at its recommended sampling
(`--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64`), Ollama, ctx 131072.

An earlier probe used `queries[:200]` = the first split only (g1_instruction, the
easiest), which inflated every gemma4 number by +0.08 to +0.19; those biased
numbers are superseded by the stratified ones below.

## Final grid (FULL 1,100-query ToolBench test set, both models)

Reasoning is added in each model's native idiom: prompted ReAct scaffold for the
non-thinking Mistral-12B, native thinking channel for the thinking gemma4-31b.
Both "without reasoning" cells are the model's plain selection without its
reasoning boost. Mistral cells are its existing full-1,100 numbers (Tables 7/8:
e2e single-turn 0.186; react-eval scaffold 0.035, BEAR 0.719/0.675). Gemma cells
are the merged full-1,100 (`toolbench_react_metrics_g4-FULL1100_merged.json`),
assembled from the stratified pilot (seed42 u seed43 = 366) + the 734 complement.

| condition | Mistral-12B | gemma4-31b |
|---|--:|--:|
| Monolithic (3,225), without reasoning | 0.186 [0.163, 0.210] | 0.383 [0.354, 0.412] |
| Monolithic, with reasoning            | 0.035 [0.025, 0.045] | 0.620 [0.591, 0.648] |
| BEAR (top-5) single-turn              | 0.719 [0.693, 0.745] | 0.766 [0.741, 0.791] |
| BEAR + reasoning / ReAct              | 0.675 [0.648, 0.703] | 0.745 [0.720, 0.771] |

## Findings

1. **Reasoning flips sign with scale.** Adding reasoning to the monolithic prompt
   *drops* the 12B model (0.186 -> 0.035, -0.152, McNemar p=1.4e-36, paired) but
   *lifts* the 31B model (0.383 -> 0.620, +0.237, p=3.2e-44). Clean scale-emergent
   CoT (Wei 2022): the same intervention degrades selection at 12B, rescues it at 31B.
2. **Governance still wins on the same model**: gemma4 BEAR (0.745-0.766) beats
   its own monolithic-with-reasoning (0.620) by ~+0.14, and far cheaper
   (~5k vs ~82k prompt tokens; one call vs tens of seconds of reasoning/query).
3. **Governance collapses the model-scale gap**: on monolithic the 12B->31B gap is
   large in either condition (without reasoning 0.186 -> 0.383; with reasoning
   0.035 -> 0.620); on BEAR it is +0.047 (0.719 -> 0.766). A small governed model
   matches a 2.5x-larger reasoning model, because governance makes the decision
   tractable enough that scale and reasoning stop mattering.
4. Reasoning does not help once the set is narrow: gemma4 BEAR non-thinking
   (0.766) > reasoning (0.745), McNemar p=0.01 -- same direction as the 12B ReAct
   result, now significant at full n.

Each query scored on a single draw at temp=1.0 (stochastic). The earlier pilot
(two stratified 198-samples, seeds 42/43) confirmed independent draws agree; its
pooled n=396 grid (0.402/0.614/0.763/0.740) is superseded by the full 1,100 above.

Result files: `toolbench_react_metrics_g4-*-s4{2,3}_partial.json` (+ logs).

## Extending to full 1,100 (standard ToolBench test set)

To move Table 9 from the stratified pilot to the full 1,100-query test set without
re-running the 366 queries already collected:

```
# 1. write the index split (366 done, 734 complement); deterministic
python evals/make_complement_indices.py

# 2. run Gemma on ONLY the 734 complement (4 conditions, cheap -> expensive)
#    override BASE_URL / MODEL if your Ollama server differs
bash evals/run_gemma_complement.sh

# 3. stitch pilot (366) + complement (734) -> full 1,100 grid + paired McNemar
python evals/merge_gemma_full1100.py
```

Each query is evaluated exactly once at the same settings (temp 1.0, top_p 0.95,
top_k 64, cap 0); for the 30 queries in both seeds, seed 42's result is kept. The
merge writes `toolbench_react_metrics_g4-FULL1100_merged.json` and prints the
full-1,100 numbers to drop into Table 9. The `--query-indices-file` flag on
`eval_toolbench_react.py` (a JSON list of indices into the flat 1,100 order) is
the general mechanism.
