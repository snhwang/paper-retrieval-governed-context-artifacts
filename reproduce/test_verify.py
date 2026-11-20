"""Checks of verify.py's rules of 18 and 19 Nov 2026 on small synthetic files.

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
# the bm25 check: hash similarity counts read as similarity values (19 Nov 2026)
BJ, BT = "bm25_v042_check_default.json", "bm25_v042_check_default_output.txt"
def rec(differing=0, presence=0, present=157, digest="9b5bcfb91b49fa68", examples=()):
    return {"pairs": 738, "pairs_differing": differing, "presence_differing": presence,
            "present_new": present, "present_old": 157, "digest": digest, "examples": list(examples)}
def ex(sim_new=0.2143001, sim_old=0.2143, **new):
    old = {"q": 3, "rule": "safety-1", "present": False, "admitted_by": None, "excluded_reason": "below_threshold",
           "similarity": sim_old}
    return {"new": dict(old, similarity=sim_new, **new), "old": old}
def mc(backend, r):
    return {"mandatory_coverage": {backend: {"A_off": r, "theta_b_new": 0.665, "theta_b_old": 0.665}}}
moved = rec(682, digest="10cbce6b80fe4fbd", examples=[ex(), ex(0.31, 0.31 + 2e-7), ex(None, None)])
case("bm25 check: hash count, digest and examples pass", "exact", mc("hash", rec()), mc("hash", moved), False, BJ)
case("bm25 check: hash presence change fails", "exact", mc("hash", rec()),
     mc("hash", rec(682, presence=1, present=158, digest="10cb")), True, BJ)
case("bm25 check: example with a changed decision fails", "exact", mc("hash", rec()),
     mc("hash", rec(682, digest="10cb", examples=[ex(present=True)])), True, BJ)
case("bm25 check: example similarity 1e-5 apart fails", "exact", mc("hash", rec()),
     mc("hash", rec(682, digest="10cb", examples=[ex(0.21431, 0.2143)])), True, BJ)
case("bm25 check: example similarity gone fails", "exact", mc("hash", rec()),
     mc("hash", rec(682, digest="10cb", examples=[ex(None, 0.2143)])), True, BJ)
case("bm25 check: BM25 count stays exact", "exact", mc("bm25", rec(7)), mc("bm25", rec(8)), True, BJ)
case("bm25 check: attribution layout passes", "exact",
     {"mandatory_coverage": {"hash/A_on": {"default": rec(), "tie_order": rec()}}},
     {"mandatory_coverage": {"hash/A_on": {"default": rec(136, digest="10cb"), "tie_order": rec(136, digest="10cb")}}},
     False, "bm25_v042_check_attribution.json")
case("another file: hash count stays exact", "exact", mc("hash", rec()), mc("hash", rec(682)), True)
tc = "  bm25: A_on 0/738 (0), A_off 7/738 (7); theta_b 0.33 -> 0.33\n  hash: A_on 0/738 (0), A_off 0/738 (0), D_on 0/738 (0); theta_b 0.665 -> 0.665\n"
tr = tc.replace("hash: A_on 0/738 (0), A_off 0/738 (0), D_on 0/738 (0)", "hash: A_on 136/738 (0), A_off 682/738 (0), D_on 501/738 (0)")
case("bm25 check text: hash counts pass", "exact", tc, tr, False, BT)
case("bm25 check text: hash presence change fails", "exact", tc, tr.replace("682/738 (0)", "682/738 (1)"), True, BT)
case("bm25 check text: hash pair total change fails", "exact", tc, tr.replace("682/738", "682/737"), True, BT)
case("bm25 check text: hash theta change fails", "exact", tc, tr.replace("-> 0.665", "-> 0.664"), True, BT)
case("bm25 check text: BM25 count stays exact", "exact", tc, tr.replace("A_off 7/738 (7)", "A_off 8/738 (7)"), True, BT)
ta = "  hash/A_on                       present 0.4.0 738/738  default: 0 (0) | flat_backfill: 0 (0)\n"
case("bm25 check text: attribution line passes", "exact", ta, ta.replace(": 0 (0)", ": 136 (0)"), False,
     "bm25_v042_check_attribution_output.txt")
case("bm25 check text: attribution present count fails", "exact", ta, ta.replace("738/738", "737/738"), True,
     "bm25_v042_check_attribution_output.txt")
case("another text file: hash counts stay exact", "exact", tc, tr, True, "x_output.txt")
print("FAILED CASES:", fails)
sys.exit(1 if fails else 0)
