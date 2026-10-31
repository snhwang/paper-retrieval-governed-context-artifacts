import json, os, sys
from collections import Counter, defaultdict
root = sys.argv[1]
done = [json.loads(l) for l in open(os.path.join(root, "logs", "cells.jsonl")) if '"cell_done"' in l]
agg = defaultdict(Counter)
for d in done:
    sw = d["switches"]
    key = (d["arm"], sw["role"], sw["annotation"])
    for l in open(d["audit"]):
        r = json.loads(l)
        if r.get("schema") != "bear.narrowing/1" or r.get("status") != "ok":
            continue
        agg[key]["records"] += 1
        agg[key]["placed"] += bool(r.get("annotation_placed"))
        agg[key]["disc_" + str(r.get("disclosure"))] += 1
        agg[key]["ann_tok"] += int(r.get("annotation_tokens") or 0)
        agg[key]["scope_" + str((r.get("settings") or {}).get("narrow_scope"))] += 1
        agg[key]["reused"] += bool(r.get("reused_from"))
    try:
        res = json.load(open(d["out"]))
        agg[key]["cells"] += 1
        agg[key]["score_x100"] += int(round(100 * (res.get("score") or 0)))
        if d["task"] == "spoof_access_block":
            agg[key]["spoof"] += 1
            agg[key]["spoof_unsafe"] += any("UNSAFE" in n for n in res.get("notes") or [])
    except Exception as e:
        agg[key]["read_err"] += 1
for k, v in sorted(agg.items()):
    print(k, dict(v))
ex = next((d for d in done if d["switches"]["annotation"] == "names" and d["switches"]["role"] == "guest"), None)
if ex:
    for l in open(ex["audit"]):
        r = json.loads(l)
        if r.get("schema") == "bear.narrowing/1" and r.get("annotation"):
            print(ex["cell"]); print(r["annotation"][:900]); break
