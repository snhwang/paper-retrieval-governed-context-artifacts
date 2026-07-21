# Does any monolithic configuration substitute for governance?

Cross-model comparison on ToolBench tool selection: Mistral-Nemo-12B (dense,
non-thinking) vs gemma4:12b and gemma4:31b (both dense, natively thinking). All
three on the **full 1,100-query test set**, matched query-for-query. Gemma at its
recommended sampling (`--temperature 1.0 --llm-top-p 0.95 --llm-top-k 64`),
Ollama, ctx 131072.

Two earlier measurement errors, both superseded by the grid below:
- `queries[:200]` took only the first split (g1_instruction, the easiest),
  inflating every gemma4 number by +0.08 to +0.19. Fixed by stratified sampling,
  then by moving to the full 1,100.
- A stratified 198x2 two-seed pilot, superseded once all models ran on the full
  1,100.

A third error -- an entire condition that measured silence rather than
selection -- is documented next; it is the reason two previously reported numbers
are retracted.

## IMPORTANT: a retracted condition (empty-response bug)

The condition `--reasoning-mode --reasoning-effort none` (free-form reasoning
prompt with the native thinking channel DISABLED) makes Gemma return **no content
at all** on a large fraction of queries. Measured empty rates: **43%** on
gemma4:31b (13/30) and **67%** on gemma4:12b (4/6). Empty responses score 0, so
the condition was reported as accuracy 0.383 (31b) / 0.145 (12b) when it was
largely measuring silence -- gemma4:31b is 88% accurate on the queries where it
does answer.

Those two numbers are **retracted** and must not be used. The valid replacement is
the constrained {thought, action} scaffold with the native channel off
(0.660 / 0.499), which produces valid output on every query.
The native-reasoning cells were verified clean (0/30 empty on both models).

Note on terminology: the scaffold with `--reasoning-effort none` is **not** a
"no reasoning" condition. `reasoning-effort none` disables only the *native*
channel; the scaffold's `thought` field still elicits brief prompted reasoning
(e.g. `{"thought": "To get Messi's career info I first need his Transfermarkt
slug", "action": "..."}`). For the Gemma models there is therefore **no**
reasoning-free condition here -- only Mistral's single-turn function call, which
has no thought field, is genuinely reasoning-free. Do not describe any Gemma cell
as "without reasoning."

Guarded against recurrence in `eval_toolbench_react.py` (commit 10659ab): empty
responses are now counted separately, reported per condition with
`accuracy_when_answered`, persisted as `response_health`, and a run aborts after
25 queries if the empty rate exceeds `--max-empty-rate` (default 0.10). Verify
with `bash evals/verify_empty_guard.sh`.

## Final grid (FULL 1,100-query test set, three models)

Each model was given several ways to succeed on the crowded monolithic prompt, so
the result does not hinge on one prompting choice.

| configuration | Mistral-12B | gemma4:12b | gemma4:31b |
|---|--:|--:|--:|
| **Monolithic (3,225)** | | | |
| single-turn | 0.186 [0.163, 0.210] | -- | -- |
| constrained ReAct scaffold | 0.035 [0.025, 0.045] | 0.499 [0.469, 0.528] | **0.660** [0.632, 0.687] |
| + native reasoning | -- | 0.475 [0.445, 0.505] | 0.620 [0.591, 0.648] |
| **BEAR (governed top-5)** | | | |
| single-turn | **0.719** [0.693, 0.745] | 0.735 [0.709, 0.760] | **0.768** [0.743, 0.793] |
| constrained ReAct scaffold | 0.675 [0.648, 0.703] | 0.723 [0.696, 0.749] | 0.745 [0.718, 0.770] |
| + native reasoning | -- | 0.749 [0.724, 0.774] | 0.745 [0.720, 0.771] |

## Findings

1. **No monolithic configuration reaches governed accuracy.** Best monolithic
   anywhere (0.660, 31b scaffold) < weakest governed anywhere (0.719, Mistral).
2. **Governance compresses the between-model spread**: monolithic 0.186-0.660
   (0.47) vs governed 0.719-0.768 (0.05). Model choice nearly stops mattering.
3. **Model quality, not scale, is the operative variable.** Two same-size models
   given the identical scaffold differ >10x (0.035 vs 0.499), so the monolithic
   gap does not track parameter count. We make no reasoning-vs-no-reasoning claim
   for the Gemma models: their configurations differ in output format as well as
   reasoning, and (see terminology note above) none of them is reasoning-free.
4. **Reasoning does not help once the set is narrow**: the scaffold costs Mistral
   0.044 (p=3.1e-5) and gemma4:31b 0.024 (p=3.1e-4); gemma4:12b 0.012 (p=0.17, ns).
   (Do not confuse this with gemma4:12b's native-reasoning delta on BEAR, which is
   +0.015 -- a different comparison.)

Each query scored on a single draw at temp=1.0 (Gemma's recommended sampling).

Superseded: the earlier two-seed pilot grid (198x2) and the scale-emergence
framing built on the retracted condition above.
