# gemma4:31b vs Mistral-Nemo-12B: does scale/reasoning obviate governance?

Matched cross-model comparison on ToolBench tool selection. **Representative**
(stratified sample of 198 queries across all six ToolBench splits, seed 42) and
**matched** (Mistral-Nemo's saved per-query arrays subsampled to the identical
indices -- no Mistral re-run). Gemma 4 at its recommended sampling
(`--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64`), Ollama, ctx 131072.

An earlier probe used `queries[:200]` = the first split only (g1_instruction, the
easiest), which inflated every gemma4 number by +0.08 to +0.19; those biased
numbers are superseded by the stratified ones below.

## Final matched grid (same 198 stratified queries, seed 42)

| condition | Mistral-12B | gemma4-31b |
|---|--:|--:|
| Monolithic (3,225) + constrained scaffold | 0.035 | -- |
| Monolithic + reasoning OFF | -- | 0.364 |
| Monolithic + reasoning ON | -- | 0.621 |
| BEAR (top-5) single-turn, non-thinking | 0.727 | 0.768 |
| BEAR + reasoning / ReAct | 0.677 | 0.742 |

## Findings

1. **Native reasoning helps the hard monolithic condition at 31B**: 0.364 -> 0.621
   (+0.258, McNemar p=1.6e-11, paired). Opposite to the 12B, where the ReAct
   scaffold *hurt* -- a clean demonstration of scale-emergent CoT (Wei 2022).
2. **Governance still wins on the same model**: gemma4 BEAR (0.742-0.768) beats
   its own monolithic-with-reasoning (0.621) by ~+0.12, and far cheaper
   (~5k vs ~82k prompt tokens; one call vs ~29 s/query of reasoning).
3. **Governance collapses the model-scale gap**: on monolithic the 12B->31B gap
   is +0.586 (0.035 -> 0.621); on BEAR it is +0.040 (0.727 -> 0.768). A small
   governed model matches a 2.5x-larger reasoning model, because governance makes
   the decision tractable enough that scale and reasoning stop mattering.
4. Reasoning does not help once the set is narrow: gemma4 BEAR non-thinking
   (0.768) >= reasoning (0.742), same pattern as the 12B ReAct result.

Caveat: temp=1.0, single seed. Effects are large (0.26, p=1e-11), so a second
seed would not change conclusions, but one more seed would fully lock it if this
goes into the paper.

Result files: `toolbench_react_metrics_g4-*-strat_partial.json` (+ logs).
