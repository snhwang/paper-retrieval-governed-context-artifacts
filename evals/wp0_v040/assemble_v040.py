"""Copy the WP0/WP4 outputs from the run clone into the artifacts repo.

Destination: <repo>/results/v040/ (new folder; no existing file is touched).

Each step's outputs are taken only from that step's own stage folder and only
if they match what the step's command writes (OUTPUTS below). Lanes ran side
by side, so a step's stage folder can also hold a file another lane wrote in
the same window. Those copies are left out.

Layout
  results/v040/<version>/<step>/...   result files, as the scripts named them
  results/v040/logs/<step>.log        one log per step (header: sha, command, env)
  results/v040/lists/                 e2e top-5 lists (v040, v0110) and WP4 k=50 lists
  results/v040/wp4/                   WP4 analysis
  results/v040/compare/               0.1.10 vs 0.4.0 comparison
  results/v040/MANIFEST.json          every file with its sha256, step, version and BEAR sha
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
from pathlib import Path

OUTPUTS = {
    "verify": ["results/wp0/run_provenance.json"],
    "tb*": ["results/wp0/toolbench_eval_{step}.json"],
    "t4_inferred": ["results/toolbench_inferred_metrics.json", "results/toolbench_inferred_output.txt"],
    "t4_multitag": ["results/toolbench_multitag_metrics.json", "results/toolbench_multitag_output.txt"],
    "t4_top5": ["results/toolbench_top5_metrics.json", "results/toolbench_top5_output.txt"],
    "transfer_toolbench": ["results/wp0/backend_transfer_toolbench_*.json"],
    "transfer_metatool": ["results/wp0/backend_transfer_metatool_*.json"],
    "toolllm_both": ["results/wp0/toolbench_toolllm_fixed.json"],
    "framework_toolbench": ["results/wp0/framework_baseline_toolbench.json"],
    "framework_petsim": ["results/wp0/framework_baseline_petsim.json"],
    "reranker_toolbench": ["results/wp0/reranker_composition_toolbench.json"],
    "reranker_petsim": ["results/wp0/reranker_composition_petsim.json"],
    "scalability": ["results/scalability_results.csv"],
    "baseline_comparison*": ["results/baseline_comparison_results.csv"],
    "backends*": ["results/wp0/backend_comparison*.json*"],
    "gov_ablation*": ["results/wp0/governance_ablation*.json"],
    "diag_*": ["results/wp0/diag_*.json"],
    "decomposed*": ["results/governance_decomposed_*.json", "results/governance_decomposed_output.txt"],
    "alpha_sweep*": ["results/alpha_sweep_*.json", "results/alpha_sweep_output.txt"],
}


# Steps finished before the MetaTool+Tags tag-order fix in eval_toolbench.py
# (load_metatool_queries_tagged iterated a set). Their MetaTool+Tags governed
# rows depend on the hash seed for the 497 two-tool queries, except BM25,
# which is order-invariant. They are rerun after the fix.
PRE_TAG_FIX = {
    "tb_bm25": "MetaTool+Tags (gov) made before the tag-order fix; BM25 is order-invariant, so unaffected",
    "tb_hash": "MetaTool+Tags (gov) made before the tag-order fix; hash rows for two-tool queries depend on the hash seed",
    "wp4_mt_lex": "MetaTool+Tags lists made before the tag-order fix",
}


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def patterns_for(step: str) -> list[str]:
    for key, pats in OUTPUTS.items():
        if fnmatch.fnmatch(step, key):
            return [p.replace("{step}", step) for p in pats]
    return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="~/tist-evals/wp0-v040")
    ap.add_argument("--repo", required=True, help="artifacts repo (destination)")
    ap.add_argument("--ver", default="v040", help="BEAR version label of the run (folder results/<ver>)")
    ap.add_argument("--extra", nargs="*", default=[],
                    help="more folders to copy, as dest_subdir=source_dir (absolute)")
    args = ap.parse_args()
    root, repo = Path(args.root), Path(args.repo)
    ver_main = args.ver
    dest = repo / "results" / ver_main
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"files": [], "steps": {}}
    logs = root / "logs"
    for ver_dir in sorted((root / "stage").iterdir()):
        ver = ver_dir.name
        for step_dir in sorted(ver_dir.iterdir()):
            step = step_dir.name
            state = ("done" if (logs / f"{step}.done").exists() and not (logs / f"{step}.skipped").exists()
                     else "skipped" if (logs / f"{step}.skipped").exists()
                     else "blocked" if (logs / f"{step}.blocked").exists()
                     else "failed" if (logs / f"{step}.failed").exists() else "unknown")
            manifest["steps"][step] = {"version": ver, "state": state}
            if step in PRE_TAG_FIX:
                manifest["steps"][step]["note"] = PRE_TAG_FIX[step]
            # Result files only from finished steps. A killed or failed step
            # keeps its log, which says how far it got.
            pats = patterns_for(step) if state == "done" else []
            for f in sorted(step_dir.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(step_dir).as_posix()
                if f.suffix == ".log" and f.parent == step_dir:
                    target = dest / "logs" / f.name
                elif f.name == "IDENTICAL_TO_COMMITTED.txt" and pats:
                    target = dest / ver / step / f.name
                elif any(fnmatch.fnmatch(rel, p) for p in pats):
                    target = dest / ver / step / Path(rel).name
                else:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                manifest["files"].append({"path": target.relative_to(repo).as_posix(), "step": step,
                                          "version": ver, "sha256": sha256(target)})
    sources = []
    if ver_main == "v040":
        sources = [("lists/e2e_v040", root / "artifacts/results/wp0/lists_v040/e2e"),
                   ("lists/e2e_v0110", root / "artifacts/results/wp0/lists_v0110/e2e"),
                   ("lists/wp4_toolbench", root / "artifacts/results/wp0/wp4_lists/toolbench"),
                   ("lists/wp4_metatool-tags", root / "artifacts/results/wp0/wp4_lists/metatool-tags")]
    else:
        # Lanes ran in separate clones (artifacts, artifacts-nemo, artifacts-dense, ...).
        for clone in sorted(root.glob("artifacts*")):
            w = clone / "results" / "wp0"
            sources += [(f"lists/e2e_{ver_main}", w / f"lists_{ver_main}" / "e2e"),
                        ("lists/e2e_v0110", w / "lists_v0110" / "e2e"),
                        ("lists/wp4_toolbench", w / f"wp4_lists_{ver_main}" / "toolbench"),
                        ("lists/wp4_metatool-tags", w / f"wp4_lists_{ver_main}" / "metatool-tags")]
    sources += [("wp4", root / "wp4"), ("compare", root / "compare")]
    sources += [(d, Path(sdir)) for d, sdir in (e.split("=", 1) for e in args.extra)]
    for sub, s in sources:
        if not s.exists():
            continue
        for f in sorted(s.rglob("*")):
            if f.is_file() and not f.name.endswith(".tmp.npz") and not f.name.endswith(".tmp"):
                target = dest / sub / f.relative_to(s)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, target)
                manifest["files"].append({"path": target.relative_to(repo).as_posix(), "step": sub,
                                          "sha256": sha256(target)})
    for extra in ("logs/vram.jsonl",):
        s = root / extra
        if s.exists():
            t = dest / "logs" / s.name
            shutil.copy2(s, t)
    prov = root / "stage" / ver_main / "verify" / "results" / "wp0" / "run_provenance.json"
    if prov.exists():
        manifest["run_provenance"] = json.loads(prov.read_text())
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(f"{len(manifest['files'])} files under {dest}")


if __name__ == "__main__":
    main()
