import json
import os
import sys

out = sys.argv[1]
for stage, root in (("stage1", "stage1"), ("stage2", "stage2-b1")):
    r = os.path.join(os.environ.get("WP7_AGENT_RUNS") or os.path.expanduser("~/tist-wp7/runs"), root)
    plan = json.load(open(f"{r}/logs/plan.json"))
    prov = json.load(open(f"{r}/provenance.json"))
    fp = {k: v for k, v in plan["reference_fingerprint"].items() if not k.endswith("_started_at")}
    doc = {"schema": "wp7.expected_fingerprint/1", "stage": stage,
           "source": f"reference fingerprint and provenance.json of the agent-run {root} root, {plan['created_utc']}",
           "harness_commit": plan["artifacts"]["commit"],
           "fingerprint": fp, "files_sha256": prov["files_sha256"]}
    with open(f"{out}/{stage}.json", "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    print(stage, plan["artifacts"]["commit"], len(prov["files_sha256"]), fp["bear_version"])
