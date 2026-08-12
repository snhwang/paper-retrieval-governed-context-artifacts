> **HISTORICAL PLAN — COMPLETED/SUPERSEDED.** Kept for provenance. The
> multi-step compounding experiment explored here did not enter the paper;
> the reported ReAct comparison is eval_toolbench_react.py (Tables 8-9).

# Experiment plan: does governance's advantage compound with task complexity?

## Question and hypothesis

R4.2 asked for a comparison against reasoning/tool-use paradigms (CoT, ReAct,
Toolformer) to highlight BEAR's advantages. The current single-step
`tab:e2e-react` cannot support the claim "ReAct adds nothing," because it is a
single Thought/Action step, not a multi-step reason-act-observe loop.

A stronger and more honest claim is available: **governance's benefit compounds
with the number of tools a task requires.** A multi-tool task succeeds only if
*all* its required tools are retrieved into context, so per-tool recall gains
multiply. This predicts:

- **Retrieval level (Tier 0):** the governed advantage in *full-coverage rate*
  (all ground-truth tools present in the top-k) grows as the ground-truth tool
  count grows (1 -> 2 -> 3+).
- **End-to-end (Tier 1):** governance improves multi-step task completion by
  more than single-step, because a missing tool at step k derails steps k+1..n.

This makes governance look *more* important in the agentic setting, which is
exactly what R4.2 was asking to demonstrate. Either outcome is publishable:
compounding is the strong result; "helps equally" is still a positive result.

## Tier 0 -- retrieval-level compounding (cheap, deterministic, no LLM)

The mechanism is testable without any agent loop, LLM, or simulator.

- **Data:** the existing ToolBench test queries, bucketed by ground-truth tool
  count |GT| in {1, 2, 3+} (ToolBench groups G1/G2/G3 correspond to increasing
  multi-tool complexity).
- **Metric:** full-coverage rate = fraction of queries where every ground-truth
  API is in the top-k (k=5), governed vs ungoverned, same off-the-shelf backend.
  Report per-tool recall as a secondary measure.
- **Conditions:** BEAR-governed (scope gate, oracle category tags) vs ungoverned
  (pure similarity), BGE and optionally Qwen3.
- **Prediction:** governed minus ungoverned full-coverage gap increases with
  |GT|. A flat gap falsifies the compounding mechanism.
- **Effort:** hours; reuses `eval_toolbench.py`. Deterministic.
- **Status:** prototype run in progress (result to be pasted here).

If Tier 0 shows a growing gap, that alone is a strong, deterministic,
LLM-free result that answers R4.2: governance matters more as tasks require
more tools. Tier 1 then confirms it translates to task completion.

If Tier 0 shows a flat gap, the compounding hypothesis is wrong at the
mechanism level. Do not build Tier 1; reword the single-step ReAct claim and
stop.

## Tier 1 -- end-to-end multi-step (StableToolBench, expensive, conditional)

Only pursue if Tier 0 is positive.

- **Why StableToolBench:** the only setup with both a large tool corpus (so
  retrieval/governance matters) and reliable multi-step execution. It replaces
  ToolBench's dead RapidAPI endpoints with a simulated API server (cached real
  responses plus LLM-simulated behavior).
- **Tasks:** ToolBench I2 (intra-category multi-tool) and I3 (cross-category
  multi-tool).
- **Agent:** the existing Mistral-Nemo-Instruct-2407 ReAct loop
  (`eval_toolbench_react.py`), extended to a genuine retrieve -> act -> observe
  loop against the simulated server.
- **Conditions:** governed candidate set vs ungoverned, both under ReAct.
- **Metric:** Solvable Pass Rate (ToolEval, an LLM-as-judge; disclose the judge
  and its reliability caveat).
- **Prototype first:** ~20 I2/I3 tasks end to end (sim server answering, ReAct
  loop retrieving per step, one governed-vs-ungoverned comparison) before any
  full run. If the sim server or judge integration is unworkable, fall back to
  the reword with zero loss.

### Costs and risks (Tier 1)
- Standing up the StableToolBench simulated server.
- ToolEval is LLM-as-judge -> API cost and a judge-reliability caveat.
- Harness work to make the ReAct loop genuinely multi-step.
- The compounding effect may not appear end-to-end even if Tier 0 is positive
  (LLM behavior is noisier than retrieval); a null end-to-end result is still
  reportable.

## Decision gates

1. Tier 0 positive -> report it as the compounding result; decide whether Tier 1
   is worth the integration for this revision or is a follow-up.
2. Tier 0 negative -> reword the single-step ReAct claim; no Tier 1.
3. Tier 1 prototype smooth -> scale to full I2/I3; Tier 1 prototype blocked ->
   reword and cite Tier 0.

## Framing regardless of outcome

BEAR (context construction) and ReAct (reasoning) operate at different layers.
The comparison is not "BEAR vs ReAct" but "does governance matter under a
reasoning paradigm," and the answer is yes. Tier 0 makes that quantitative and
deterministic; Tier 1, if pursued, confirms it end to end.
