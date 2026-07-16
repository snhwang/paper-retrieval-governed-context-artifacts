# gemma4:31b reasoning exploration (preliminary, NOT in the paper)

Exploratory probe of the question: does a larger, natively-thinking model's
reasoning substitute for governed retrieval on ToolBench tool selection?

**Status: preliminary.** 200-query seeded subsample (not the paper's 1,100),
`temperature=1.0` (Gemma 4's recommended sampling, so results are stochastic),
single model, single run each. These numbers are **not** paper-table quality and
are held out of the resubmission; they are kept for the record and as support if
a reviewer asks about reasoning models. They are consistent with the manuscript's
scale-emergent-reasoning caveat (Wei 2022) in the ReAct section.

Model: `gemma4:31b` (Q4), Ollama, `OLLAMA_CONTEXT_LENGTH=131072`,
`--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64`. Thinking is on by default via
Ollama's Gemma 4 template; disabled with `--reasoning-effort none`.

| condition | file | exact acc (n=200) |
|---|---|---|
| Monolithic + native reasoning ON | `..._gemma4-31b-reason_partial.json` | 0.755 |
| Monolithic + reasoning prompt, native OFF | `..._gemma4-31b-mono-nothink_partial.json` | 0.550 |
| BEAR + native reasoning (bear_react) | `..._gemma4-31b-bear_partial.json` | 0.820 |

Takeaways (preliminary):
- On the hard monolithic condition, native reasoning adds ~+0.20 (0.550 -> 0.755;
  non-overlapping CIs). Reasoning *helps* at 31B, opposite to the *hurt* at 12B
  (Mistral-Nemo, Table 8) -- a clean illustration of scale-emergent CoT benefit.
- On the same model, governance still wins on accuracy (BEAR 0.820 > monolithic
  reasoning 0.755) and does so ~15x cheaper (5k vs ~82k prompt tokens, one call
  vs ~29 s/query of reasoning). Governance is not obviated by reasoning.

**Known artifact:** the `bear_single` row in `..._gemma4-31b-bear_partial.json`
reads 0.005 and is INVALID -- the constrained single-turn path used
`max_tokens=100`, which a thinking model exhausts on reasoning before emitting the
`{tool}` JSON. Fixed in `call_llm_with_tools` (default budget 2048 +
`reasoning_effort` passthrough); a clean `bear_single` needs a re-run with
`--reasoning-effort none`. Only `bear_react` (0.820) in that file is valid.
