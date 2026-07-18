#!/usr/bin/env python
"""Write the query-index split used to extend Gemma4:31b to full-1,100 coverage.

The pilot scale experiment evaluated Gemma on two stratified samples of 198
(seeds 42 and 43), covering 366 unique queries of the 1,100-query ToolBench test
set. This writes:

    results/g4_done_indices.json        366 already-evaluated indices
    results/g4_complement_indices.json  734 remaining indices to run

Feed the complement file to eval_toolbench_react.py --query-indices-file so only
the un-run queries are evaluated; merge_gemma_full1100.py then stitches pilot +
complement into the full standard test set. Deterministic (seeded), so re-running
this reproduces the exact same split.
"""
import json, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from eval_toolbench_react import stratified_sample_indices

N = 1100
R = pathlib.Path(__file__).resolve().parent.parent / "results"

i42 = set(stratified_sample_indices(N, 200, 42))
i43 = set(stratified_sample_indices(N, 200, 43))
done = sorted(i42 | i43)
todo = sorted(set(range(N)) - set(done))

json.dump(done, open(R / "g4_done_indices.json", "w"))
json.dump(todo, open(R / "g4_complement_indices.json", "w"))
print(f"seed42={len(i42)}  seed43={len(i43)}  overlap={len(i42 & i43)}")
print(f"done={len(done)}  complement={len(todo)}  (done+complement={len(done)+len(todo)})")
print(f"wrote {R/'g4_done_indices.json'}")
print(f"wrote {R/'g4_complement_indices.json'}")
