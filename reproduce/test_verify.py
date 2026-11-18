"""Checks of verify.py's rules of 18 Nov 2026 on small synthetic files.

    python reproduce/test_verify.py      # exit 0 when every case behaves

Needs numpy, as verify.py does for .npz files. Writes only to a temporary folder.
"""
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify as v

T = Path(tempfile.mkdtemp())
fails = 0
def case(name, cls, c, r, want_fail, fname="x.json"):
    global fails
    cp, rp = T / "c" / fname, T / "r" / fname
    cp.parent.mkdir(exist_ok=True); rp.parent.mkdir(exist_ok=True)
    if fname.endswith(".json"):
        cp.write_text(json.dumps(c)); rp.write_text(json.dumps(r))
    elif fname.endswith(".npz"):
        np.savez(cp, **c); np.savez(rp, **r)
    else:
        cp.write_text(c); rp.write_text(r)
    d = v.compare_file(cp, rp, cls)
    ok = bool(d.fail) == want_fail
    fails += not ok
    print(("ok  " if ok else "BAD ") + name, d.fail[:2])

A, B = "9d085b49c004cb03e2bede9055fdc3810cf260c0", "0d0718a39a0b0788ef5cca4689352462b830494c"
# spec pairing
tasks = [{"spec": {"seed": i}, "recall": [1.0] * 25} for i in range(3)]
case("per_task in another order passes", "exact", {"per_task": tasks}, {"per_task": tasks[::-1]}, False)
t2 = json.loads(json.dumps(tasks)); t2[1]["recall"][3] = 0.0
case("per_task with a changed value fails", "exact", {"per_task": tasks}, {"per_task": t2[::-1]}, True)
# delta with ci
case("gpu delta inside the CI passes", "gpu", {"x": {"delta": 0.08, "ci": [0.07, 0.09], "cohens_d_paired": 0.4}},
     {"x": {"delta": 0.081, "ci": [0.069, 0.093], "cohens_d_paired": 0.39}}, False)
case("gpu delta outside the CI fails", "gpu", {"x": {"delta": 0.08, "ci": [0.07, 0.09]}}, {"x": {"delta": 0.095, "ci": [0.08, 0.1]}}, True)
# x beside x_ci, and x_mean beside x_ci
case("gpu x/x_ci inside passes", "gpu", {"gov": 83.05, "gov_ci": [80.8, 85.3], "gov_mean": 1.0},
     {"gov": 83.0, "gov_ci": [80.7, 85.2], "gov_mean": 1.0}, False)
case("gpu x_mean/x_ci outside fails", "gpu", {"gov_mean": 495.7, "gov_ci": [488.8, 502.6]}, {"gov_mean": 503.0, "gov_ci": [490, 510]}, True)
case("gpu int count beside a rate CI is noted only", "gpu", {"items_out_of_scope": 1930, "items_out_of_scope_ci": [0.338, 0.364]},
     {"items_out_of_scope": 1929, "items_out_of_scope_ci": [0.3375, 0.3635]}, False)
case("gpu float without CI still 0.0005", "gpu", {"ratio": 2.5293}, {"ratio": 2.5265}, True)
# hash rule
case("hash file float 1e-7 passes", "exact", {"final_score": [[0.4974292, 0.42]]}, {"final_score": [[0.4974291, 0.42]]}, False, "bear_hash_gov.json")
case("hash file float 1e-5 fails", "exact", {"m": 70.28501}, {"m": 70.28506}, True, "bear_hash_gov.json")
case("hash file int differs fails", "exact", {"n": 0}, {"n": 1}, True, "hash_no_gov.json")
case("hash key float 1e-7 passes", "exact", {"backends": {"hash": {"sim": 0.5}}}, {"backends": {"hash": {"sim": 0.5000001}}}, False)
case("hash key per-query ints exact", "exact", {"backends": {"hash": {"pool": [47] * 30}}}, {"backends": {"hash": {"pool": [47] * 29 + [48]}}}, True)
case("non-hash key float 1e-7 fails", "exact", {"backends": {"bm25": {"sim": 0.5}}}, {"backends": {"bm25": {"sim": 0.5000001}}}, True)
case("hashing word not hash scope", "exact", {"hashing_sim": 0.5}, {"hashing_sim": 0.5000001}, True)
case("hash npz float passes, int same", "exact", {"sim": np.array([0.5, 0.4], dtype=np.float32), "idx": np.array([1, 2])},
     {"sim": np.array([0.5000001, 0.4], dtype=np.float32), "idx": np.array([1, 2])}, False, "hash_no_gov.npz")
case("hash npz idx swap fails", "exact", {"idx": np.array([1, 2])}, {"idx": np.array([2, 1])}, True, "hash_no_gov.npz")
case("non-hash npz float 1e-7 fails", "exact", {"sim": np.array([0.5])}, {"sim": np.array([0.5000001])}, True, "bge_no_gov.npz")
# labels and text
case("BEAR sha alias in JSON passes", "exact", {"bear_source_sha": A, "export_sha": "9d085b4"}, {"bear_source_sha": B, "export_sha": B}, False)
case("other sha in JSON fails", "exact", {"bear_source_sha": A}, {"bear_source_sha": "1234567abcdef"}, True)
ctext = f"BEAR 0.4.2 {A}\ngit commit:      6ae764af\ngit status:      unknown\n  25/314 tasks, 41s\n  [toolbench: 68.1s]\nRan in 610.9s. Corpus 39.6\nR@5 0.905\n"
rtext = f"BEAR 0.4.2 {B}\ngit commit:      5cf0bb19\ngit status:      DIRTY (40 files modified)\n  25/314 tasks, 24s\n  [toolbench: 34.0s]\nRan in 677.6s. Corpus 39.6\nR@5 0.905\n"
case("text run facts, times and sha pass", "exact", ctext, rtext, False, "x_output.txt")
case("text result change fails", "exact", ctext, rtext.replace("R@5 0.905", "R@5 0.906"), True, "x_output.txt")
case("text command line change fails", "exact", ctext + "Command line: a\n", rtext + "Command line: a --workers 8\n", True, "x_output.txt")
# path keys
pc = {"retrieval": {"/home/u/tist-evals/wp0-v042/artifacts-dense/results/wp0/e2e/bge.json": {"t": 5}}}
pr = {"retrieval": {"/home/u/tist-repro/wp0/artifacts-dense/results/wp0/e2e/bge.json": {"t": 5}}}
case("path keys from the folder on pass", "exact", pc, pr, False)
pr2 = {"retrieval": {"/home/u/tist-repro/wp0/artifacts-nemo/results/wp0/e2e/bge.json": {"t": 5}}}
case("path keys in another folder fail", "exact", pc, pr2, True)
print("FAILED CASES:", fails)
sys.exit(1 if fails else 0)
