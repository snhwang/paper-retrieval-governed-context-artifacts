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
    # 0.4.2 run (2026-10-30): forced-fallback reruns on 0.1.10 (lane fallback0110)
    "fb_alpha": ["results/alpha_sweep_*.json", "results/alpha_sweep_output.txt"],
    "fb_toolllm": ["results/wp0/toolbench_toolllm_fixed.json"],
}


# 0.4.2 run: steps that exited 3 because some rows were skipped (OOM at encode
# batch 8 inside the 11.2 GiB cap). Their completed rows are kept; the missing
# rows come from the *_fix steps at encode batch 2 (2026-10-31).
PARTIAL = {
    "tb_qwen4b": "rows done at encode batch 8; MetaTool Qwen3-4B (no gov) and both ToolBench rows were "
                 "skipped (OOM) and rerun at batch 2 in tb_qwen4b_mt_fix and tb_qwen4b_tb_fix. Its MetaTool "
                 "BEAR+Qwen3-4B (gov) row is superseded by tb_qwen4b_mt_gov_b2 (batch 2, so the base MetaTool "
                 "pair shares one batch size); it is kept as a record",
    "tb_qwen4b_v0110": "rows done at encode batch 8; MetaTool Qwen3-4B (no gov) and both ToolBench rows were "
                       "skipped (OOM) and rerun at batch 2 in tb_qwen4b_v0110_mt_fix and tb_qwen4b_v0110_tb_fix. "
                       "Its MetaTool BEAR+Qwen3-4B (gov) row is superseded by tb_qwen4b_v0110_mt_gov_b2 (batch 2); "
                       "it is kept as a record",
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


GZIP_OVER = 5 * 1024 * 1024  # files above 5 MB are stored gzipped (lossless), to keep the repo small


def store(src: Path, target: Path, repo: Path, rec: dict, files: list) -> None:
    """Copy src to target, gzipped when large. The manifest keeps the sha256 of
    the original content and, for a gzipped copy, of the stored file too."""
    import gzip
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = sha256(src)
    if src.stat().st_size > GZIP_OVER:
        gz = target.with_name(target.name + ".gz")
        with src.open("rb") as fi, gzip.open(gz, "wb", compresslevel=9) as fo:
            shutil.copyfileobj(fi, fo)
        files.append({**rec, "path": gz.relative_to(repo).as_posix(), "sha256_original": raw,
                      "sha256": sha256(gz), "gzipped": True, "original_bytes": src.stat().st_size})
    else:
        shutil.copy2(src, target)
        files.append({**rec, "path": target.relative_to(repo).as_posix(), "sha256": raw})


def patterns_for(step: str) -> list[str]:
    for key, pats in OUTPUTS.items():
        if fnmatch.fnmatch(step, key):
            return [p.replace("{step}", step) for p in pats]
    if step.startswith("fb_"):  # a forced-fallback rerun writes what the step it copies writes
        return patterns_for(step[3:])
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
            if step in PRE_TAG_FIX and ver_main == "v040":
                manifest["steps"][step]["note"] = PRE_TAG_FIX[step]
            if step in PARTIAL and ver_main != "v040" and state == "failed":
                state = "partial"
                manifest["steps"][step].update(state="partial", note=PARTIAL[step])
            # Result files only from finished steps. A killed or failed step
            # keeps its log, which says how far it got.
            pats = patterns_for(step) if state in ("done", "partial") else []
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
                store(f, target, repo, {"step": step, "version": ver}, manifest["files"])
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
                        ("lists/e2e_v0110", w / "lists_v0110" / "e2e")]
            # e2e lists under legacy switches (attribution of the BM25 prompt changes)
            for d in sorted(w.glob(f"lists_{ver_main}L_*")):
                sources.append((f"lists/e2e_{d.name[6:]}", d / "e2e"))
    if ver_main != "v040":
        # the k=50 lists of every clone, merged with one meta.json (merge_wp4_lists.py)
        sources += [("lists/wp4_toolbench", root / "wp4_lists_final" / "toolbench"),
                    ("lists/wp4_metatool-tags", root / "wp4_lists_final" / "metatool-tags")]
    sources += [("wp4", root / "wp4"), ("compare", root / "compare")]
    sources += [(d, Path(sdir)) for d, sdir in (e.split("=", 1) for e in args.extra)]
    for sub, s in sources:
        if not s.exists():
            continue
        for f in sorted(s.rglob("*")):
            if f.is_file() and not f.name.endswith(".tmp.npz") and not f.name.endswith(".tmp"):
                store(f, dest / sub / f.relative_to(s), repo, {"step": sub}, manifest["files"])
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
