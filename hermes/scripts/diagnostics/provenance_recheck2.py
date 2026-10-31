"""Stage 2 pre-grid check: the live fingerprint against stage 1's plan reference. Only the BEAR
version and sha (0.4.1 to 0.4.2 on purpose) and the container start times may differ."""
import json
import os
import sys

H = os.environ.get("WP7_HERMES_DIR") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNS = os.environ.get("WP7_RUNS") or os.path.expanduser("~/wp7-runs")
TREE = os.environ.get("WP7_HERMES_TREE") or TREE
sys.path.insert(0, H)
import provenance  # noqa: E402

ALLOWED = {"bear_version", "bear_sha", "sglang_started_at", "embedder_started_at"}
ref = json.load(open(os.path.join(RUNS, "stage1", "logs", "plan.json")))["reference_fingerprint"]
cur = provenance.fingerprint(sys.executable, TREE)
keys = sorted(set(ref) | set(cur))
diff = {k: [ref.get(k), cur.get(k)] for k in keys if ref.get(k) != cur.get(k)}
bad = {k: v for k, v in diff.items() if k not in ALLOWED}
print(json.dumps({"reference": "stage-1 plan.json reference_fingerprint (2026-10-30 11:13 UTC)",
                  "allowed_differences": {k: v for k, v in diff.items() if k in ALLOWED},
                  "unexpected_differences": bad, "sglang_settings_now": cur.get("sglang_settings")}, indent=1))
sys.exit(1 if bad else 0)
