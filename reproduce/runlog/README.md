# Run records of the author's runs

Each script of the kit writes a run record when it starts and completes it when it ends. This folder holds the records of the author's runs of the kit for the revised paper, copied from `$REPRO_OUT/runlog` on the machine that ran them.

- One JSON file per start of a script, named by script and UTC start time.
- `records.jsonl` is the index that the kit keeps, one line per record.
- The records cover 12 to 23 November 2026.

Nothing was removed. Failed and repeated attempts are included, since they are part of the record. A run with a non-zero exit code is not an error in the log. Several steps stop on purpose, for example the final check (`90_verify`), which ends with a non-zero code while any file still differs.

One record is damaged, `56_e2e_long_context-20261121T070026Z.json`. Two queue jobs started in the same second on 21 November (jobs 418 and 419, which make the tags `mistral-nemo-131k` and `gemma4-31b-131k`) and wrote the same file. It is not valid JSON, and `records.jsonl` has no line for it. Job 418 failed on the shared file and made no tag. Job 419 made its tag. Since then each run gets its own record. Both tag steps ran once more under complete records on 21 November (jobs 453 and 454). The step for `gemma4-31b-131k` found the tag that job 419 made and recorded its digest.

On 23 November the final assembly and check ran three times. The first check (job 578, `90_verify-20261123T190115Z.json`) stopped because the assembly before it had left out seven of the author's result files that equal the committed copies. The kit was changed to gather them (`70_assemble.sh`, `lib/outputs_equal_committed.txt`). The author then entered the last block twice, so the clone update, the assembly and the check each ran twice more (jobs 601 to 603 and 619 to 621). Both checks ended with exit code 0 and the same totals.

## What a record holds

- The script, its arguments, its start and end times, its exit code and its status.
- The commit of this repository and of every clone the step used, the Python environment, and the BEAR sources.
- The Hugging Face snapshots of the local models, and what each server reported about itself (`endpoints`).
- The commands the step ran, with their exit codes.
- Notes. A run started by the job queue carries the queue's job number, its name and the purpose stated for it.

Most records carry such a queue note. The others date from 12 to 14 November, when the queue was being set up.

The records name the user account, the host and local paths of the machine. They hold no credentials.

## One change to the records

Until 22 November 2026 the queue's job page wrote the e-mail address of the person who entered a job into the job's comment, and the kit copied the comment into the record. In this folder that address is replaced by a placeholder, so the comments read `entered=web scott`. Nothing else in a record was changed. The kit no longer copies such an address (`lib/common.sh`).

## Commit hashes that changed on 22 November 2026

Removing the address also meant rewriting the history of this repository from the commit that first added this folder. Nineteen commits got new hashes. Each has the same author, dates, message and files as before, and its files differ only where the address stood. Earlier commits kept their hashes.

Records and queue comments written before the change name the old hashes, for example `kit e98cc49` or an `artifacts checkout` at `e98cc49`. This table links them to the commits that exist now.

| Old | Now | Commit |
|---|---|---|
| df70652 | e993eb3 | Add the run records of the author's kit runs as a log |
| 30d4db4 | 55175c8 | Results: the author's outputs replace 16 files and the Hermes tables |
| 51d2e82 | 838f401 | Plan for the end-to-end reruns (version 1, awaiting approval) |
| 60e2710 | 28d13d6 | End-to-end rerun plan: record Scott's answer of 20 Nov |
| ca6371e | 1d24456 | Kit: rerun all ten retrieval rows of Table 10 in one session |
| c490811 | c37ef89 | Run log: the final check passes under the author's run (job 317) |
| 381f3aa | 7226d4a | Kit: fixed-window Ollama tags and a measured load |
| 0462a68 | f9655a0 | End-to-end rerun plan, version 3 |
| b5ac798 | 2a9ba3d | Run log: the clone update and the ten-row Table 10 rerun |
| 1171be7 | e011bb6 | Kit: run parts for the long-context end-to-end reruns |
| 7472902 | 3b2caa2 | Run log: the fixed-window Gemma 12B tag and its measured load |
| 5e516cb | ecbd50e | Kit: night steps for the long-context reruns |
| 16c07ed | 3be589c | Kit: the night steps ask for the memory the client uses |
| 295c571 | 5397131 | Kit: a clone-update job that waits for the kit jobs in the queue |
| ae1b8f9 | 747fa83 | Kit: native runs one at a time, one queue job per night |
| 260f1cd | 7893922 | Kit: the plan's hash in a job comment does not depend on line ends |
| eeff01e | debf51f | Run log: the Gemma 12B runs of 20 Nov and the clone updates |
| 5fd725d | c2446cb | Plan v4 and run log note: the 31B tag exists |
| e98cc49 | a91576d | Plan v4: approval is Scott's own words by hash |

## What is not here

- The records of dry runs.
- The outputs of the runs. The kit writes them below `$REPRO_OUT`, and `verify.py` compares them with the committed files in `results/` (see `MANIFEST.md`, "State of the runs").
