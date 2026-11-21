# End-to-end reruns: plan

Status: version 4, 2026-11-21 (see Changes). Versions 1 to 3, 2026-11-20. Scott read the three decisions below and answered on 20 Nov 2026: "It doesn't really matter how we do it. We just need to rerun and document." The session took that as approval of versions 1 to 3 with the planned choices: Ollama, a fixed seed, and all four parts. Version 4 changes how part 4 is run, after job 350 stopped at its third run. Scott approves version 4 by queueing a job whose plan line names this file's sha256. Under "Specs yes, gates no" (9 Nov 2026) and "Re-run anything questionable" (12 Nov 2026), this file is fixed before the runs it describes. Its sha256 is recorded in the paper repo's `revision-plan.md`.

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
4. **Gemma 4 12B and 31B.** The two scripts behind the Gemma columns of Supplement Table S1, `run_model_scaffold_nothink.sh` and `run_model_full1100.sh`, for each model. Then `grid_from_full1100.py` and `scaffold_vs_single.py`. Since version 4 the four runs of `run_model_full1100.sh` are made one at a time (see Changes).

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
- The server software is newer. Ollama is 0.40.16 on 20 Nov 2026, and July's version was not recorded. The GPU driver is 621.24 since 20 Nov 2026, and July's was older.
- Since version 4, the third run of `run_model_full1100.sh` is made with the script's check for empty answers lifted. In July the script had no such check.

## What each run records

Scott, 20 Nov 2026: "We just need to rerun and document", and in the model-server session, "Make sure we documenet the model and serving method."

- **From the run itself.** The Ollama version, the tag and its digest, the tag's parameters (`num_ctx`), the request settings (temperature, top-p, top-k, seed, output limit, response format), the card before and after the load, and the server's own prompt token counts.
- **From the queue.** Since 20 Nov 2026 15:45 EST, model-server writes `run-<job>.json` for every job that holds the GPU licence. It records what Ollama and the servers on ports 8355 and 8360 served at the start and at the end of the job, the image digests and the GPU driver.
- **Server settings.** On 20 Nov 2026, from `model-server/machines/serving-record.md`: the key-value cache is f16 (`OLLAMA_KV_CACHE_TYPE` is unset), flash attention is on automatic, and Ollama serves one request at a time.
- **The Qwen3.8 server.** Whether the server on port 8355 was up or down during the run.

The results' README in the repository gets one table with these facts per run.

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

That is about 30 to 50 hours in all. The times of parts 2 to 4 are those of the July runs. Version 4 (see Changes) gives the times measured on 20 Nov 2026.

## Changes to the kit before the runs

- `evals/wp0_v040/e2e_rerun.py` and `reproduce/50_e2e_ollama.sh` gain the five rows they lack.
- A new step runs parts 2 to 4 on BEAR 0.4.2. It is `55_e2e_previous_version.sh` with the BEAR pin changed and the digests checked.
- `evals/eval_toolbench_react.py` gains an option that sends a seed.
- `reproduce/lib/paper_map.py` and `reproduce/collect.py` read the reruns for the items T10b, T10c, T11 and T12. Their status changes from "previous version" to "this revision".
- Each script gets a dry run before a job is handed over.

## Decisions for Scott

All three take the planned choice (see Status).

1. **Server.** Ollama with the builds above. His own serving scripts use vLLM. Ollama is planned because the July runs used it, the paper describes it, and the kit already drives it.
2. **Seed.** A fixed seed for the Gemma runs, as above, or none as in July.
3. **Scope.** All four parts.

## Changes

- **2026-11-20, version 2.** Version 1 (sha256 b2e21cebff8336222cb5d13de39787eef69629de61117fd3c146d3f9e395ade7) said that a prompt with all 3,225 tools needs a window of at least 131,072 tokens. Version 2 fixes how that window is set. Nothing else changes.
  - **Fixed-window tags.** Parts 2 to 4 run on tags that only add `num_ctx 131072` to the July builds: `mistral-nemo-131k` (from `mistral-nemo`), `gemma4-12b-131k` (from `gemma4:12b`) and `gemma4-31b-131k` (from `gemma4:31b`). The Modelfiles are `evals/e2e_rerun/Modelfile.<tag>`. A tag adds no weights. The run record of the step that makes a tag holds its digest.
  - **Why.** The Ollama server defaults to a window of 262,144 tokens. The model-server session worked out that with it the larger models do not fit on the card (its note is `model-server/machines/ollama-long-context-room.md`). The July runs used that default.
  - **The prompt's size.** The ReAct and Gemma scripts list each tool as its name and the first 400 characters of its description. That prompt is 82,540 cl100k tokens with the longest query (`count_prompts.py`). Ollama cuts a prompt that is longer than the window without failing, so each model's own count is read from the server before a run is booked, and the Ollama log is searched for "truncating input prompt" after every run.
  - **Measured loads first.** `reproduce/56_e2e_long_context.sh` makes each tag and measures one guarded load of it. The 12B model fits beside the Qwen3.8 server. Mistral-Nemo at this window and the 31B model need that server stopped, in nights booked through the model-server session.
  - If a model's own count leaves less than 8,704 tokens of the window free, that model's tag gets a larger window, and this file says so before the run.
- **2026-11-20, version 3.** Version 2 had sha256 bddc45e1c4c08f2770e85fb4c02cb13f20b4af81791d5fb3cac15a60c8bf03dc. Version 3 adds the section "What each run records" and names the newer Ollama and GPU driver as differences from July. No run setting changes.
- **2026-11-21, version 4.** Version 3 had sha256 114cf0d71765d3a65f83939c8b0612d9a9cbcbfadfc3f81188211b6bfaaa3252. Version 4 changes how the native-reasoning script of part 4 is run. No model, prompt, seed or decoding setting changes.
  - **What happened.** Job 349 ran the scaffold script on Gemma 4 12B on 20 Nov and finished in 1 h 05. Job 350 then ran `run_model_full1100.sh` on the same model. Its first two runs finished (governed single-turn, and governed with native reasoning). Its third run is the monolithic prompt in free-form mode with the reasoning channel off. The script's check for empty answers stopped that run, because 15 of the first 25 answers were empty. The check was added to the script after July. In July the same run completed and scored 0.145, a value that is not in the paper. The fourth run did not start. It is the monolithic prompt with native reasoning, a cell of Table S1.
  - **One run per load.** The four runs of the script are made one at a time. Each has its own guarded load and its own serving record. Each is one pass over the 1,100 queries. A run that finished is not made again.
  - **Why.** On the 12B model the four runs need about 12.5 hours. The first two took 5 minutes and 5 h 06 on 20 Nov, and in July the last two took 40 minutes and 6 h 28. The 31B model was about 1.5 times slower in July's scaffold runs, so its four runs need about 18 hours. No booked night is longer than 10 h 50. Made one at a time, the runs spread over several nights, and no run is put together from pieces.
  - **The finished runs of job 350 stand.** They are the 12B values for their two conditions, and they are not made again. So each condition has one value. The serving record of job 350 shows no cut prompt, and the model was unloaded at its end. There is evidence that a repeat would give the same answers. The governed single-turn condition ran in job 349 and in job 350 with the same seed, and all 1,100 answers agree.
  - **The third run.** For both models it is made with the check for empty answers lifted (`--max-empty-rate 1.0`). It then completes, and its count of empty answers is on record. No condition of the script is dropped. Its value is not in the paper, as in July. Table S1's monolithic cells come from the scaffold script and from the fourth run.
  - **A run that is stopped.** A run that the end of a night stops keeps no result. It is made again in a later night, and what the stopped attempt left is kept apart in the output folder.
  - **Nights.** One queue job per booked night runs that night's parts in order and skips the parts already done. Until 21 Nov each part was its own queue job, chained to the others. On 21 Nov two tag jobs started in the same second and shared one run record. One of them failed, and the queue cancelled the measured load of Mistral-Nemo and the ReAct job, which depended on it. No run had started, so no result was affected. The kit now gives each run its own record. Job 419 made the tag `gemma4-31b-131k` before its record was damaged. The tag step runs once more, so that a complete run record holds the tag's digest.
  - **Times measured on 20 Nov 2026.** Part 1 took 27 minutes (job 327). The 12B scaffold batch took 1 h 05 (monolithic prompt 40 minutes, about 2.2 s per query). The table above said 4 to 9 hours for each Gemma run.
