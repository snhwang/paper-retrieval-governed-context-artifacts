"""Write checks_summary.json and run_info.json for a stage-1 analysis (read-only on the run).

Usage: python3 results_extras.py RUN_ROOT OUT_DIR   (after checks.py wrote RUN_ROOT/checks)
"""
import json
import os
import sys
from collections import Counter

root = os.path.expanduser(sys.argv[1])
out = sys.argv[2]
ck = json.load(open(os.path.join(root, "checks", "checks.json")))
log = [json.loads(ln) for ln in open(os.path.join(root, "logs", "cells.jsonl"))]
done = [r for r in log if r.get("event") == "cell_done"]
timeouts = sorted(r["cell"] for r in done if r["returncode"] != 0)


def kind(r):
    if r["cell"] in timeouts:
        return "timeout cell (no result file, so dependent checks fail)"
    if r["check"] == "run.no_traceback":
        err = open(os.path.join(root, "logs", r["cell"] + ".stderr"), errors="replace").read()
        if err.count("Traceback") == err.count("--- Logging error ---"):
            return "Hermes logging-format error printed to stderr (run completed)"
        return "other traceback"
    if r["check"] == "metrics.worker_counts_match_audit":
        return ("arm B: worker counts bridge-reached calls with no gate decision" if r["cell"].startswith("B__")
                else "audit counts calls missing from the final transcript")
    return "other"


by = Counter((r["check"], r["ok"]) for r in ck)
fails = [r for r in ck if not r["ok"]]
summary = {
    "checks": {name: {"pass": by[(name, True)], "fail": by[(name, False)]}
               for name in sorted({r["check"] for r in ck})},
    "total": len(ck), "failed": len(fails),
    "failures_by_kind": dict(Counter(kind(r) for r in fails)),
    "failures": [{"cell": r["cell"], "check": r["check"], "kind": kind(r), "detail": r["detail"][:300]}
                 for r in fails if r["cell"] not in timeouts],
    "timeout_cells": timeouts,
}
with open(os.path.join(out, "checks_summary.json"), "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=1)

plan = json.load(open(os.path.join(root, "logs", "plan.json")))
prov = json.load(open(os.path.join(root, "provenance.json")))
starts = [r for r in log if r.get("event") == "batch_start"]
ends = [r for r in log if r.get("event") == "batch_end"]
refusals = [r for r in log if r.get("event") == "flush_cache" and r.get("http_status") != 200]
walls = [r["wall_s"] for r in done]
info = {
    "plan": {k: plan[k] for k in ("created_utc", "argv", "order", "seed", "sandbox", "artifacts",
                                  "reference_fingerprint")},
    "planned_cells": len(plan["cells"]),
    "batch_start_utc": starts[0]["utc"] if starts else None, "batch_end_utc": ends[-1]["utc"] if ends else None,
    "batch_starts": len(starts), "cells_done": len(done), "errors": len(timeouts),
    "cell_wall_s": {"mean": round(sum(walls) / len(walls), 1), "max": max(walls), "sum_h": round(sum(walls) / 3600, 1)},
    "flush": {"refusals": len(refusals), "max_attempts": max(r.get("flush_attempts", 1) for r in done),
              "max_wait_s": max(r.get("flush_wait_s", 0) for r in done)},
    "sandbox_in_every_cell": all(r.get("sandbox") == "bwrap" for r in done),
    "fingerprint_changes": sorted({k for r in done for k, v in (r.get("fingerprint") or {}).items()
                                   if v != plan["reference_fingerprint"].get(k)}),
    "provenance": {k: prov.get(k) for k in ("recorded_at", "host", "python", "hermes", "artifacts", "bear")},
    "sglang": {k: prov["sglang"].get(k) for k in ("version", "model_path", "revision", "served_model_name",
                                                    "kv_cache_dtype", "enable_cache_report", "random_seed",
                                                    "tool_call_parser", "reasoning_parser")},
    "sglang_image_id": (prov["sglang"].get("container") or {}).get("image_id"),
    "embedder": {"health": prov["embedder"].get("health"),
                 "image_id": (prov["embedder"].get("container") or {}).get("image_id")},
}
with open(os.path.join(out, "run_info.json"), "w", encoding="utf-8") as f:
    json.dump(info, f, indent=1, default=str)
print(json.dumps({"failures_by_kind": summary["failures_by_kind"], "fingerprint_changes": info["fingerprint_changes"],
                  "flush": info["flush"], "cell_wall_s": info["cell_wall_s"], "start": info["batch_start_utc"],
                  "end": info["batch_end_utc"], "sandbox_all": info["sandbox_in_every_cell"]}, indent=1))
