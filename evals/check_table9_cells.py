#!/usr/bin/env python3
"""Check every Table 7/9 end-to-end cell against its committed metrics file.

Read-only consistency check: recomputes each printed accuracy from the
per-query correctness arrays produced by the author's LLM runs and compares
to the manuscript tables. File naming follows run_model_full1100.sh; the
Gemma 31B single/native cells come from the scaffold-run bundle and the
pilot+complement merge (merge_gemma_full1100.py).

Usage:  python evals/check_table9_cells.py
"""
import json
import pathlib

R = pathlib.Path(__file__).resolve().parents[1] / "results"
E = pathlib.Path(__file__).resolve().parents[1] / "evals" / "results"

# (label, printed value, file, per_query key)
CELLS = [
    # --- Table 7 / Table 9, Mistral-Nemo ---
    ("Mistral mono single-turn", 0.186, E / "toolbench_e2e_scores_partial.json", "_exact_scores"),
    ("Mistral mono ReAct      ", 0.035, R / "toolbench_react_metrics.json", "mono_react"),
    ("Mistral bear single     ", 0.719, R / "toolbench_react_metrics.json", "bear_single"),
    ("Mistral bear ReAct      ", 0.675, R / "toolbench_react_metrics.json", "bear_react"),
    # --- Table 9, Gemma 4 12B ---
    ("12B mono scaffold       ", 0.499, R / "toolbench_react_metrics_g4-12b-scaffold-nothink-full.json", "mono_react"),
    ("12B mono native         ", 0.475, R / "toolbench_react_metrics_g4-12b-mono-think-full_partial.json", "mono_react"),
    ("12B bear single         ", 0.735, R / "toolbench_react_metrics_g4-12b-bearsingle-nothink-full_partial.json", "bear_single"),
    ("12B bear scaffold       ", 0.723, R / "toolbench_react_metrics_g4-12b-scaffold-nothink-full.json", "bear_react"),
    ("12B bear native         ", 0.749, R / "toolbench_react_metrics_g4-12b-bear-full_partial.json", "bear_react"),
    # --- Table 9, Gemma 4 31B ---
    ("31B mono scaffold       ", 0.660, R / "toolbench_react_metrics_g4-31b-scaffold-nothink-full.json", "mono_react"),
    ("31B mono native         ", 0.620, R / "toolbench_react_metrics_g4-FULL1100_merged.json", "mono_on"),
    ("31B bear single         ", 0.768, R / "toolbench_react_metrics_g4-31b-scaffold-nothink-full.json", "bear_single"),
    ("31B bear scaffold       ", 0.745, R / "toolbench_react_metrics_g4-31b-scaffold-nothink-full.json", "bear_react"),
    ("31B bear native         ", 0.745, R / "toolbench_react_metrics_g4-FULL1100_merged.json", "bear_react"),
]


def per_query(path, key):
    d = json.loads(path.read_text(encoding="utf-8"))
    if "per_query_correct" in d:
        return d["per_query_correct"][key]
    # e2e scores file: list of per-condition dicts
    for s in d["scores"]:
        if key in s:
            return s[key]
    raise KeyError(key)


def main():
    ok = True
    for label, cell, path, key in CELLS:
        if not path.exists():
            print(f"{label} FILE NOT FOUND: {path.name}")
            ok = False
            continue
        a = per_query(path, key)
        m = sum(map(bool, a)) / len(a)
        match = round(m, 3) == cell
        ok &= match
        print(f"{label} table={cell:.3f}  file={m:.4f} (n={len(a)})  "
              f"{'OK' if match else 'MISMATCH'}")
    print("\nALL TABLE CELLS OK" if ok else "\nCHECK FAILED -- see above")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
