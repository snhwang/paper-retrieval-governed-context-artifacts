# End-to-end reruns on BEAR 0.4.2 (20 to 23 November 2026)

This file covers three folders beside it: `e2e_rerun_all/`, `e2e_rerun_hash/` and `e2e_long/`. They hold the author's outputs of the end-to-end rerun plan (`evals/e2e_rerun/PLAN.md`, version 5, parts 1 to 5). The files are copied from the kit's assembled tree without change. Every end-to-end value in the revised paper is read from them (Table 10, the end-to-end text of Section 4.2, Supplement Section S1 and Supplement Table S1).

Each run was a job in the author's queue. `reproduce/runlog/` holds the run record of each kit step, and `reproduce/MANIFEST.md` maps each paper item to its files.

## What each folder feeds

| Folder | Plan part | Paper item | Kit step |
|:--|:--|:--|:--|
| `e2e_rerun_all/` | 1 | Table 10, the ten retrieval rows | `50_e2e_ollama.sh --all-rows` |
| `e2e_long/monolithic/` | 2 | Table 10, the monolithic row | `56_e2e_long_context.sh monolithic` |
| `e2e_long/react/` | 3 | The ReAct numbers of Section 4.2 and Supplement Section S1, and the Mistral-Nemo column of Supplement Table S1 | `56_e2e_long_context.sh react` |
| `e2e_long/g12-scaffold/`, `g12-native/`, `g31-scaffold/`, `g31-native/` | 4 | Supplement Table S1, the Gemma 4 columns | `56_e2e_long_context.sh g12-scaffold`, `g12-native`, `g31-scaffold`, `g31-native-s1` to `-s4` |
| `e2e_rerun_hash/` | 5 | Section 4.2, the hash backend's governed row (in the text, not in a table) | `50_e2e_ollama.sh --hash-row` |
| `e2e_long/monolithic-cap128/` | 5 | Section 4.2, the run with the first 128 schemas (in the text) | `56_e2e_long_context.sh monolithic-cap128` |
| `e2e_long/measure-g12/`, `measure-g31/`, `measure-nemo/` | none | No result. One measured load of each 131k tag before its runs | `56_e2e_long_context.sh measure-*` |

The four runs of `run_model_full1100.sh` are named s1 to s4.
- **s1.** Governed top 5, single-turn selection.
- **s2.** Governed top 5 with native reasoning.
- **s3.** Monolithic prompt, free-form, reasoning off. It ran with the script's check for empty answers lifted, and its value is not in the paper.
- **s4.** Monolithic prompt with native reasoning.

For the 12B model, s1 and s2 are in `e2e_long/g12-native/` itself (job 350), and s3 and s4 are in its subfolders (job 455). For the 31B model each run has its own subfolder.

## Serving, per run

All runs used one machine and one server, Ollama 0.40.16 on the author's workstation. As recorded on 20 Nov 2026, the key-value cache was f16, flash attention was on automatic, and Ollama served one request at a time. The base builds are `mistral-nemo` (digest `e7e06d107c6c`, Q4_0), `gemma4:12b` (`4eb23ef187e2`, Q4_K_M) and `gemma4:31b` (`6316f0629137`, Q4_K_M). Each tag below adds only a fixed window to its base build (`evals/e2e_rerun/Modelfile.*`).

Mistral-Nemo ran at temperature 0 with its output constrained by a JSON schema, and with no seed. The Gemma models ran at temperature 1.0, top-p 0.95 and top-k 64, with one draw per query and the seed 20261120.

The steps of `56_e2e_long_context.sh` write a serving record for each load (`serving.json`, and `serving.txt` as one line). The table is read from those files. Times are UTC. The card column gives the GPU memory in use, in MiB, before the load, after it and after the unload. "Port 8355" says whether another model server on the same card was up at the start and at the end of the run. "Cut prompts" counts the lines "truncating input prompt" in the Ollama log since the start of the run.

| Folder | Queue job | Start | End | Tag and digest | Window | Seed | Card MiB | Port 8355 | Cut prompts | Exit |
|:--|:--|:--|:--|:--|--:|:--|:--|:--|--:|--:|
| `e2e_long/g12-scaffold` | 349 | 21 Nov 00:10 | 21 Nov 01:14 | `gemma4-12b-131k` `e8408c45bfbc` | 131,072 | 20261120 | 67,599 / 79,521 / 67,436 | up | 0 | 0 |
| `e2e_long/g12-native` (s1, s2) | 350 | 21 Nov 01:27 | 21 Nov 07:00 | `gemma4-12b-131k` `e8408c45bfbc` | 131,072 | 20261120 | 67,441 / 79,369 / 67,524 | up | 0 | 1 |
| `e2e_long/g12-native/s3` | 455 | 21 Nov 19:52 | 21 Nov 21:00 | `gemma4-12b-131k` `e8408c45bfbc` | 131,072 | 20261120 | 68,075 / 80,038 / 67,848 | up | 0 | 0 |
| `e2e_long/g12-native/s4` | 455 | 21 Nov 21:00 | 22 Nov 04:06 | `gemma4-12b-131k` `e8408c45bfbc` | 131,072 | 20261120 | 67,848 / 79,784 / 68,162 | up | 0 | 0 |
| `e2e_long/react` | 456 | 22 Nov 07:44 | 22 Nov 10:09 | `mistral-nemo-131k` `70fa1233bae2` | 131,072 | none | 11,340 / 39,755 / 11,171 | down | 0 | 0 |
| `e2e_long/monolithic` | 456 | 22 Nov 10:10 | 22 Nov 10:41 | `mistral-nemo-131k` `70fa1233bae2` | 131,072 | none | 11,151 / 39,569 / 11,149 | down | 0 | 0 |
| `e2e_long/g31-scaffold` | 456 | 22 Nov 10:42 | 22 Nov 12:41 | `gemma4-31b-131k` `d0e8710a4e62` | 131,072 | 20261120 | 11,171 / 44,654 / 11,003 | down | 0 | 0 |
| `e2e_long/g31-native/s1` | 456 | 22 Nov 12:41 | 22 Nov 12:59 | `gemma4-31b-131k` `d0e8710a4e62` | 131,072 | 20261120 | 11,003 / 44,505 / 11,298 | down | 0 | 0 |
| `e2e_long/g31-native/s3` | 456 | 22 Nov 13:00 | 22 Nov 13:52 | `gemma4-31b-131k` `d0e8710a4e62` | 131,072 | 20261120 | 11,295 / 44,791 / 7,838 | down | 0 | 0 |
| `e2e_long/g31-native/s2` | 457 | 22 Nov 13:52 | 22 Nov 22:41 | `gemma4-31b-131k` `d0e8710a4e62` | 131,072 | 20261120 | 7,827 / 41,310 / 8,621 | down | 0 | 0 |
| `e2e_long/g31-native/s4` | 458 | 22 Nov 22:42 | 23 Nov 08:38 | `gemma4-31b-131k` `d0e8710a4e62` | 131,072 | 20261120 | 8,503 / 41,991 / 9,411 | down | 0 | 0 |
| `e2e_long/monolithic-cap128` | 576 | 23 Nov 18:58 | 23 Nov 19:00 | `mistral-nemo-32k` `d79a1e80980f` | 32,768 | none | 66,306 / 78,667 / 66,360 | up | 0 | 0 |

- **Job 350 ended with exit code 1.** Its first two runs (s1 and s2) finished and are reported. Its third run was stopped by the script's check for empty answers, and the fourth did not start. What the stopped attempt left is in `e2e_long/g12-native/unfinished/`. Job 455 made s3 and s4. The plan's version 4 records this.
- **In every run the model was unloaded at the end**, and no prompt was cut.

The two steps of `50_e2e_ollama.sh` write no serving record. Their facts are in each folder's `rerun.log` and in the step's run record.

| Folder | Queue job | Start | End | Tag and digest | Window | Seed | Model errors | Run record |
|:--|:--|:--|:--|:--|--:|:--|--:|:--|
| `e2e_rerun_all` (ten rows) | 327 | 20 Nov 20:39 | 20 Nov 21:07 | `mistral-nemo-32k` `d79a1e80980f` | 32,768 | none | 0 in each row | `50_e2e_ollama-20261120T203947Z.json` |
| `e2e_rerun_hash` (one row) | 575 | 23 Nov 18:55 | 23 Nov 18:58 | `mistral-nemo-32k` `d79a1e80980f` | 32,768 | none | 0 | `50_e2e_ollama-20261123T185526Z.json` |

Both ran on Ollama 0.40.16, and each folder holds the marker `UNLOADED` that the step writes after the model is unloaded.

## Notes for a reader of the files

- **Column heads in `report.md`.** The two `report.md` files head the rerun columns "2026-10-31". That is a fixed label of the report script, from the first rerun. The runs are those of 20 and 23 November 2026 listed above.
- **File names with "partial".** Some result files of the monolithic and native-reasoning runs have "partial" in their names, because the scripts write them as they go. Each run listed above is a complete pass over the 1,100 queries (`n_queries` in the monolithic files, `n=1100` in each `grid.txt`).
- **The earlier rerun.** `e2e_rerun/` beside these folders holds a rerun of five Table 10 rows of 31 October 2026, on Ollama 0.40.13. The paper's values are read from `e2e_rerun_all/`, where all ten rows ran in one session.
