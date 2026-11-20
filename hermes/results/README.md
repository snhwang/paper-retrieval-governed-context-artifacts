# Hermes results

These are the analysis outputs behind Section 4.9 and Table 16 of the paper.

- `stage1/` and the files directly in `stage2/` are the author's runs of the steps in `hermes/REPRODUCE.md`, made in November 2026 on BEAR v0.4.2 and the current harness. `tables.md` in each folder is the file the paper's numbers were read from.
- `stage2/ksweep.*` and `stage2/annotation_cost.*` come from the author's run of the stage-2 settings step.
- `stage2/smoke/` holds an earlier smoke run that an agent launched. It is not a reported result.

They replaced the agent-run tables on 20 Nov 2026. `reproduce/verify.py` compares a rerun with these files.
