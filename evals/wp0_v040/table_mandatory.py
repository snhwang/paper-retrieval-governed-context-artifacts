"""Per-query table: safety rules present in each Pet Sim output, 0.1.10 vs 0.4.2.

Reads diag_mandatory_petsim.py outputs, one per BEAR version or legacy switch:
    --run v0110=<json> --run v042=<json> --run L_ungated_pool=<json> ...
Writes
  <out>.csv  one row per backend x governance level x query set x query, with
             the number of the 3 safety rules present and which ones are
             missing, under 0.1.10, 0.4.2 and each switch
  <out>.md   per backend x level x query set: mean safety rules present, the
             queries missing at least one, F1, and the switches whose per-query
             counts equal 0.1.10's ("none" if no single switch does)
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True, help="label=path")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    runs = {}
    for r in a.run:
        lab, path = r.split("=", 1)
        runs[lab] = json.loads(Path(path).read_text(encoding="utf-8"))
    base, new = runs["v0110"], runs["v042"]
    switches = [k for k in runs if k.startswith("L_")]
    safety = base["safety_ids"]
    rows_csv = []
    md = ["| Backend | Level | Query set | n | Safety present 0.1.10 (mean) | queries missing any (0.1.10) "
          "| Safety present 0.4.2 (mean) | F1 0.1.10 | F1 0.4.2 | Switch restoring 0.1.10 counts |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for key in base["rows"]:
        if key not in new["rows"]:
            continue
        level, qs, b = key.split(" / ")
        pb, pn = base["rows"][key]["per_query"], new["rows"][key]["per_query"]
        n = len(pb["mandatory"])
        for i in range(n):
            row = {"backend": b, "level": level, "query_set": qs, "query_index": i,
                   "query": pb["query"][i] if "query" in pb else "",
                   "safety_present_v0110": pb["mandatory"][i],
                   "missing_v0110": " ".join(sorted(set(safety) - set(pb.get("safety_present", [[]] * n)[i]))),
                   "safety_present_v042": pn["mandatory"][i],
                   "returned_v0110": pb["returned"][i], "returned_v042": pn["returned"][i]}
            for sw in switches:
                ps = runs[sw]["rows"].get(key, {}).get("per_query")
                row[f"safety_present_{sw}"] = ps["mandatory"][i] if ps else ""
            rows_csv.append(row)
        restoring = [sw[2:] for sw in switches
                     if runs[sw]["rows"].get(key, {}).get("per_query", {}).get("mandatory") == pb["mandatory"]]
        moved = pb["mandatory"] != pn["mandatory"]
        mean = lambda xs: sum(xs) / len(xs)
        md.append(f"| {b} | {level} | {qs} | {n} | {mean(pb['mandatory']):.2f} | "
                  f"{sum(1 for x in pb['mandatory'] if x < len(safety))} | {mean(pn['mandatory']):.2f} | "
                  f"{base['rows'][key]['mean_f1']:.3f} | {new['rows'][key]['mean_f1']:.3f} | "
                  f"{(', '.join(restoring) or 'none') if moved else '(unchanged)'} |")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out.with_suffix(".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_csv[0]))
        w.writeheader()
        w.writerows(rows_csv)
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
