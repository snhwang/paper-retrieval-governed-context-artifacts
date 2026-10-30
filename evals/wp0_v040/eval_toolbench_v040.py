"""eval_toolbench.py plus a Nemotron backend, for the BEAR 0.4.0 rerun (WP0).

Runs ``eval_toolbench.main()`` unchanged, with three additions:

* Backend ``nemotron``: BEAR's RemoteEmbedder against model-server's
  embedding service (default http://localhost:8360, which reports
  nvidia/llama-nemotron-embed-vl-1b-v2, 2048-dim; override with NEMOTRON_URL).
  The Config mirrors the in-process dense backends of eval_toolbench.py
  (threshold 0.15, priority weight 0.3 governed and 0.0 ungated, k=5).
* Experiments ``BEAR+Nemotron (gov)``, ``BEAR+Nemotron (mand-only)`` and
  ``Nemotron (no gov)``, selectable with --backends like the others.
* The output JSON gains a ``_provenance`` key with the BEAR version, source
  sha, package hash and the embedding service's identity from /health.

Every other backend goes through eval_toolbench.build_retriever unchanged, so
this wrapper reproduces eval_toolbench.py exactly for the existing rows.

Usage (same flags as eval_toolbench.py):
    python evals/wp0_v040/eval_toolbench_v040.py --top-k 5 \
        --metatool-query-tags-file evals/data/external_benchmarks/metatool/query_tags_top5.json \
        --backends "BEAR+Nemotron (gov)" "Nemotron (no gov)" \
        --output results/v040/toolbench_eval_nemotron_v040.json
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # evals/
sys.path.insert(0, str(HERE))

import eval_toolbench as et  # noqa: E402
import wp0_common  # noqa: E402

_orig_build = et.build_retriever


def build_retriever(corpus, backend="bge", governance=True, mandatory_tags=None):
    if backend != "nemotron":
        r = _orig_build(corpus, backend=backend, governance=governance,
                        mandatory_tags=mandatory_tags)
        wp0_common.assert_not_hash(r, backend)
        return r
    return wp0_common.nemotron_retriever(
        corpus,
        priority_weight=et.PRIORITY_WEIGHT if governance else 0.0,
        threshold=et.THRESHOLD,
        top_k=et.DEFAULT_TOP_K,
        mandatory_tags=mandatory_tags,
    )


et.build_retriever = build_retriever
et.EXPERIMENTS.extend([
    {"name": "BEAR+Nemotron (gov)", "backend": "nemotron", "governance": True,
     "use_tags": True, "strip_scope": False},
    {"name": "BEAR+Nemotron (mand-only)", "backend": "nemotron", "governance": True,
     "use_tags": False, "strip_scope": False},
    {"name": "Nemotron (no gov)", "backend": "nemotron", "governance": False,
     "use_tags": False, "strip_scope": True},
])


def _output_arg() -> str | None:
    argv = sys.argv[1:]
    for i, a in enumerate(argv):
        if a == "--output" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--output="):
            return a.split("=", 1)[1]
    return None


def _requested_backends() -> list[str]:
    argv = sys.argv[1:]
    if "--backends" not in argv:
        return []
    out = []
    for a in argv[argv.index("--backends") + 1:]:
        if a.startswith("--"):
            break
        out.append(a)
    return out


if __name__ == "__main__":
    et.main()
    out = _output_arg()
    if out and Path(out).exists():
        wp0_common.stamp_json(out, {"script": "evals/wp0_v040/eval_toolbench_v040.py"})
        print(f"Provenance stamped into {out}")
        # eval_toolbench prints SKIPPED and carries on when a retriever cannot
        # be built (an unreachable service, out of memory). Fail the run then.
        import json as _json
        data = _json.loads(Path(out).read_text(encoding="utf-8"))
        missing = [(b, n) for b, exps in data.items() if not b.startswith("_")
                   for n in _requested_backends() if n not in exps]
        if missing:
            print(f"MISSING EXPERIMENTS: {missing}")
            sys.exit(3)
    try:
        from repro_footer import print_repro_footer
        print_repro_footer(extra={k: v for k, v in wp0_common.bear_identity().items()})
    except Exception:  # noqa: BLE001
        pass
