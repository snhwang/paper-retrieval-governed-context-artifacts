# gemma4:31b vs Mistral-Nemo-12B: does scale/reasoning obviate governance?

Matched cross-model comparison on ToolBench tool selection. **Representative**
(stratified sample of 198 queries across all six ToolBench splits, seed 42) and
**matched** (Mistral-Nemo's saved per-query arrays subsampled to the identical
indices -- no Mistral re-run). Gemma 4 at its recommended sampling
(`--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64`), Ollama, ctx 131072.

An earlier probe used `queries[:200]` = the first split only (g1_instruction, the
easiest), which inflated every gemma4 number by +0.08 to +0.19; those biased
numbers are superseded by the stratified ones below.

## Final matched grid (pooled over two stratified samples, seeds 42+43, n=396)

Reasoning is added in each model's native idiom: prompted ReAct scaffold for the
non-thinking Mistral-12B, native thinking channel for the thinking gemma4-31b.
The two "without reasoning" cells differ in instrument (Mistral single-turn,
gemma4 native-off) but both are the model's plain selection without its reasoning
boost. Mistral cells come from its saved per-query arrays subsampled to the same
indices (e2e single-turn; react-eval scaffold) -- no Mistral re-run.

| condition | Mistral-12B | gemma4-31b |
|---|--:|--:|
| Monolithic (3,225), without reasoning | 0.199 [0.159, 0.240] | 0.402 [0.356, 0.449] |
| Monolithic, with reasoning            | 0.035 [0.018, 0.056] | 0.614 [0.566, 0.662] |
| BEAR (top-5) single-turn              | 0.722 [0.677, 0.765] | 0.763 [0.720, 0.803] |
| BEAR + reasoning / ReAct              | 0.677 [0.629, 0.722] | 0.740 [0.697, 0.783] |

## Findings

1. **Reasoning flips sign with scale.** Adding reasoning to the monolithic prompt
   *drops* the 12B model (0.199 -> 0.035, -0.164, McNemar p=3.4e-15, paired) but
   *lifts* the 31B model (0.402 -> 0.614, +0.212, p=3.8e-14). Clean scale-emergent
   CoT (Wei 2022): the same intervention degrades selection at 12B, rescues it at 31B.
2. **Governance still wins on the same model**: gemma4 BEAR (0.740-0.763) beats
   its own monolithic-with-reasoning (0.614) by ~+0.13, and far cheaper
   (~5k vs ~82k prompt tokens; one call vs tens of seconds of reasoning/query).
3. **Governance collapses the model-scale gap**: on monolithic the 12B->31B gap is
   large in either condition (without reasoning 0.199 -> 0.402; with reasoning
   0.035 -> 0.614); on BEAR it is +0.041 (0.722 -> 0.763). A small governed model
   matches a 2.5x-larger reasoning model, because governance makes the decision
   tractable enough that scale and reasoning stop mattering.
4. Reasoning does not help once the set is narrow: gemma4 BEAR non-thinking
   (0.763) >= reasoning (0.740), same pattern as the 12B ReAct result.

Two seeds (42, 43), samples 85% disjoint (30/198 overlap), so the pooled n=396 is
near-independent. Effects are large and hold on each seed separately.

Note: the earlier seed-42-only grid reported 0.364/0.621 for gemma4 monolithic and
0.035 for Mistral (its ReAct scaffold as the only monolithic cell); superseded by
the pooled, symmetric grid above (Mistral monolithic single-turn 0.199 is its fair
baseline; its scaffold 0.035 is the "with reasoning" cell).

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
