import json, sys
s = json.load(open(sys.argv[1] + "/summary.json"))
print("done", s["done"], "planned", s["planned"], "errors", len(s["errors"]))
print("version", s["version_checks"])
print("secondary", s["secondary_sessions"], "digest", s["digest_match"])
for cd, c in s["checks"].items():
    print(cd, "failed", len(c["failed"]), "fail sum", sum(v["fail"] for v in c["checks"].values()))
    print({k: v for k, v in c["verify_combined"].items() if "total" in k or "differ" in k})
    print({k: v for k, v in c["verify_per_cell_sum"].items() if "total" in k or "differ" in k})
