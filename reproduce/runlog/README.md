# Run records of the author's runs

Each script of the kit writes a run record when it starts and completes it when it ends. This folder holds the records of the author's runs of the kit for the revised paper, copied from `$REPRO_OUT/runlog` on the machine that ran them.

- One JSON file per start of a script, named by script and UTC start time.
- `records.jsonl` is the index that the kit keeps, one line per record.
- The records cover 12 to 20 November 2026.

Nothing was removed. Failed and repeated attempts are included, since they are part of the record. A run with a non-zero exit code is not an error in the log. Several steps stop on purpose, for example the final check (`90_verify`), which ends with a non-zero code while any file still differs.

## What a record holds

- The script, its arguments, its start and end times, its exit code and its status.
- The commit of this repository and of every clone the step used, the Python environment, and the BEAR sources.
- The Hugging Face snapshots of the local models, and what each server reported about itself (`endpoints`).
- The commands the step ran, with their exit codes.
- Notes. A run started by the job queue carries the queue's job number, its name and the purpose stated for it.

Most records carry such a queue note. The others date from 12 to 14 November, when the queue was being set up.

The records name the user account, the host and local paths of the machine. They hold no credentials.

## What is not here

- The records of dry runs.
- The outputs of the runs. The kit writes them below `$REPRO_OUT`, and `verify.py` compares them with the committed files in `results/` (see `MANIFEST.md`, "State of the runs").
