"""After the reboot: compare the live fingerprint with the last one recorded before the outage
(the pilot's last cell_done). Only the BEAR version and sha (moved to v0.4.1 on purpose) and the
container start times may differ. Exit 1 on any other difference."""
import json
import os
import sys

H = os.environ.get("WP7_HERMES_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
TREE = os.environ.get("WP7_HERMES_TREE") or TREE
sys.path.insert(0, H)
import provenance  # noqa: E402

ALLOWED = {"bear_version", "bear_sha", "sglang_started_at", "embedder_started_at"}

log = os.path.join(RUNS, "stage1-pilot", "logs", "cells.jsonl")
ref = None
with open(log) as f:
    for line in f:
        r = json.loads(line)
        if r.get("event") == "cell_done" and r.get("fingerprint"):
            ref = r["fingerprint"]
cur = provenance.fingerprint(sys.executable, TREE)
keys = sorted(set(ref) | set(cur))
diff = {k: [ref.get(k), cur.get(k)] for k in keys if ref.get(k) != cur.get(k)}
bad = {k: v for k, v in diff.items() if k not in ALLOWED}
print(json.dumps({"reference": "stage1-pilot last cell_done (before the outage)",
                  "fields_compared": keys, "allowed_differences": {k: v for k, v in diff.items() if k in ALLOWED},
                  "unexpected_differences": bad,
                  "sglang_settings_now": cur.get("sglang_settings")}, indent=1))
sys.exit(1 if bad else 0)
