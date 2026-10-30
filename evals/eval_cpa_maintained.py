#!/usr/bin/env python3
"""Maintained CPA next to the stale CPA, on novel contexts (WP5, R2-3).

R2 says the CPA baseline is set up to lose. On novel contexts it is: its
lookup tables were deliberately left without the new "fraud" department
(eval_baseline_comparison.py, phase 2). This script adds the arm R2 asks for.

Arms, on the procedural customer-support corpus at each scale point
(10 to 500 agents), over the published novel-context queries:

  bear              BEAR (BGE-base, k = 25, theta 0.3, priority weight 0.3,
                    mandatory "safety" and "global"), as published. The new
                    department's instructions carry required_tags, nothing else.
  cpa_stale         the published CPA: tables built before the department exists.
  cpa_maintained    CPA whose tables are rebuilt after the department is added,
                    so its constraints are in the department lookup. Same
                    wiring as published, which reads only the first department
                    tag of a context.
  cpa_maintained_multi
                    maintained tables plus a one-time wiring change that reads
                    every department tag in the context (the cross-department
                    queries need it).

Novel query types (from generate_novel_queries): unknown_dept (the new
fraud department, the primary measure here), cross_dept, unseen_modifier and
conflict.

Maintenance cost per new department, read from the code rather than
asserted:
  * CPA: lookup keys and entries added between the stale and maintained
    tables, and the published wiring-line formula's change
    (3 + departments + agents + discount branches).
  * The multi-department arm's one-time wiring change, counted as changed
    lines between the two retrieve() methods.
  * BEAR: lines of wiring changed (0) and tag annotations written with the new
    instructions (one required tag per instruction).

Statistics: per scale point and pooled, mean recall with bootstrap 95% CIs,
paired bootstrap of the differences with paired Cohen's d, and McNemar on
"every expected instruction retrieved". Per-query arrays are saved.

CPU only (BGE-base on the CPU):
    CUDA_VISIBLE_DEVICES= python evals/eval_cpa_maintained.py
"""

from __future__ import annotations

import argparse
import difflib
import inspect
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tistr2_common import (  # noqa: E402
    REPO_ROOT, Tee, bear_provenance, ci_summary, fmt, fmt_delta, json_default,
    mcnemar_summary, paired_summary, refuse_overwrite, require_bear_040,
)
from bear import Config, EmbeddingBackend, Instruction, Retriever, ScoredInstruction  # noqa: E402
from bear.retriever import Embedder  # noqa: E402
from eval_baseline_comparison import (  # noqa: E402
    ConditionalPromptAssembler, add_novel_department, count_unresolved_conflicts,
    generate_novel_queries,
)
from eval_scalability import (  # noqa: E402
    EMBEDDING_MODEL, PRIORITY_WEIGHT, SCALE_POINTS, THRESHOLD, TOP_K, generate_corpus,
)
from repro_footer import print_repro_footer  # noqa: E402

ARMS = ["bear", "cpa_stale", "cpa_maintained", "cpa_maintained_multi"]
TYPES = ["unknown_dept", "cross_dept", "unseen_modifier", "conflict"]


class MultiDeptCPA(ConditionalPromptAssembler):
    """Maintained CPA whose wiring reads every department tag.

    A minimal edit of the published retrieve(): the department lookup and
    the discount branch loop over the context's departments. Everything
    else is unchanged, so the AST diff counts only the wiring change.
    """

    def retrieve_multi(
        self,
        agent_idx: int,
        dept_names: list[str],
        context_tags: list[str],
    ) -> list[ScoredInstruction]:
        """Deterministic instruction selection via lookup tables."""
        selected: list[ScoredInstruction] = []

        def _wrap(inst: Instruction) -> ScoredInstruction:
            return ScoredInstruction(
                instruction=inst,
                similarity=1.0,
                scope_match=True,
                final_score=inst.priority / 100.0,
            )

        # Always include safety
        for inst in self.safety_instructions:
            selected.append(_wrap(inst))

        # Always include global policies
        for inst in self.global_instructions:
            selected.append(_wrap(inst))

        # Department constraints (lookup), every department in the context
        for dept_name in dept_names:
            if dept_name in self.constraints_by_dept:
                for inst in self.constraints_by_dept[dept_name]:
                    selected.append(_wrap(inst))

        # Agent persona (lookup)
        if agent_idx in self.persona_by_agent:
            selected.append(_wrap(self.persona_by_agent[agent_idx]))

        # Conditional: discount tag present, every department in the context
        for dept_name in dept_names:
            if "discount" in context_tags and dept_name in self.discount_by_dept:
                selected.append(_wrap(self.discount_by_dept[dept_name]))

        return selected


def table_entries(cpa: ConditionalPromptAssembler) -> dict:
    return {
        "safety": {"*": sorted(i.id for i in cpa.safety_instructions)},
        "global": {"*": sorted(i.id for i in cpa.global_instructions)},
        "persona": {str(k): [v.id] for k, v in cpa.persona_by_agent.items()},
        "constraints": {k: sorted(i.id for i in v) for k, v in cpa.constraints_by_dept.items()},
        "discount": {k: [v.id] for k, v in cpa.discount_by_dept.items()},
    }


def table_diff(old: dict, new: dict) -> dict:
    keys = entries = 0
    detail = {}
    for table in new:
        added_keys = [k for k in new[table] if k not in old[table]]
        added_entries = sum(len(set(new[table][k]) - set(old[table].get(k, []))) for k in new[table])
        keys += len(added_keys)
        entries += added_entries
        if added_keys or added_entries:
            detail[table] = {"keys_added": added_keys, "entries_added": added_entries}
    return {"keys_added": keys, "entries_added": entries, "by_table": detail}


def multi_wiring_change() -> dict:
    """Changed statements between the published retrieve() and retrieve_multi().

    Compared as AST-unparsed lines of the function bodies (docstrings and
    comments dropped), so formatting cannot inflate the count. The call site
    changes by one line as well (pass all departments, not the first).
    """
    import ast
    import textwrap

    def body_lines(fn):
        node = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None),
                                                                  ast.Constant):
            body = body[1:]
        return "\n".join(ast.unparse(st) for st in body).splitlines()

    a = body_lines(ConditionalPromptAssembler.retrieve)
    b = body_lines(MultiDeptCPA.retrieve_multi)
    sm = difflib.SequenceMatcher(a=a, b=b)
    changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return {"published_body_lines": len(a), "multi_body_lines": len(b),
            "changed_body_lines": changed, "call_site_lines": 1}


def parse_ctx(ctx):
    agent_tags = [t for t in ctx.tags if t.startswith("agent-")]
    dept_tags = [t for t in ctx.tags if t.startswith("dept-")]
    agent_idx = int(agent_tags[0].split("-")[1]) if agent_tags else -1
    depts = [t.replace("dept-", "", 1) for t in dept_tags]
    return agent_idx, depts


def run_scale(num_agents: int, embedder) -> dict:
    corpus, meta = generate_corpus(num_agents)
    config = Config(embedding_model=EMBEDDING_MODEL, embedding_backend=EmbeddingBackend.NUMPY,
                    embedding_device="cpu", priority_weight=PRIORITY_WEIGHT,
                    default_threshold=THRESHOLD, default_top_k=TOP_K,
                    mandatory_tags=["safety", "global"])
    cpa_stale = ConditionalPromptAssembler(corpus, meta)
    stale_tables = table_entries(cpa_stale)
    stale_wiring = cpa_stale.wiring_lines
    new_ids = add_novel_department(corpus)
    meta_new = dict(meta, num_departments=meta["num_departments"] + 1)
    cpa_maint = ConditionalPromptAssembler(corpus, meta_new)
    cpa_multi = MultiDeptCPA(corpus, meta_new)
    r = Retriever(corpus, config=config, embedder=embedder)
    r.build_index()

    queries = generate_novel_queries(num_agents, meta)
    per = {a: {"recall": [], "complete": [], "conflicts": []} for a in ARMS}
    qtypes = []
    for text, ctx, expected, qtype in queries:
        qtypes.append(qtype)
        agent_idx, depts = parse_ctx(ctx)
        first = depts[0] if depts else ""
        bear_ids = [s.id for s in r.retrieve_with_trace(text, ctx, top_k=TOP_K)[0]]
        outs = {
            "bear": bear_ids,
            "cpa_stale": [s.instruction.id for s in cpa_stale.retrieve(agent_idx, first, ctx.tags)],
            "cpa_maintained": [s.instruction.id for s in cpa_maint.retrieve(agent_idx, first, ctx.tags)],
            "cpa_maintained_multi": [s.instruction.id
                                     for s in cpa_multi.retrieve_multi(agent_idx, depts, ctx.tags)],
        }
        by_id = {i.id: i for i in corpus}
        for a, ids in outs.items():
            hits = len(set(ids) & expected)
            per[a]["recall"].append(hits / len(expected))
            per[a]["complete"].append(int(hits == len(expected)))
            ids_set = set(ids)
            per[a]["conflicts"].append(sum(
                1 for x in ids for c in by_id[x].conflicts_with if c in ids_set and x < c))
    res = {"num_agents": num_agents, "num_departments_before": meta["num_departments"],
           "corpus_size_with_new_dept": len(corpus), "n_queries": len(queries),
           "query_types": qtypes, "new_department_ids": new_ids,
           "maintenance": {
               "cpa_table_diff": table_diff(stale_tables, table_entries(cpa_maint)),
               "cpa_wiring_lines_stale": stale_wiring,
               "cpa_wiring_lines_maintained": cpa_maint.wiring_lines,
               "cpa_wiring_lines_added": cpa_maint.wiring_lines - stale_wiring,
               "bear_wiring_lines_added": 0,
               "bear_tag_annotations_with_new_instructions": sum(
                   len(i.scope.required_tags) for i in corpus if i.id in new_ids)},
           "arms": {}, "per_query": {a: {k: np.asarray(v) for k, v in d.items()} for a, d in per.items()}}
    for a in ARMS:
        rec = np.asarray(per[a]["recall"], float)
        res["arms"][a] = {"recall": ci_summary(rec),
                          "complete_rate": float(np.mean(per[a]["complete"])),
                          "unresolved_conflicts": int(np.sum(per[a]["conflicts"])),
                          "by_type": {t: float(np.mean([v for v, qt in zip(rec, qtypes) if qt == t]))
                                      for t in TYPES if t in qtypes}}
    return res


def pooled(results: list[dict]) -> dict:
    out = {"arms": {}, "contrasts": {}, "by_type": {}}
    cat = {a: {k: np.concatenate([r["per_query"][a][k] for r in results]) for k in
               ("recall", "complete")} for a in ARMS}
    types = np.concatenate([np.asarray(r["query_types"]) for r in results])
    for a in ARMS:
        out["arms"][a] = {"recall": ci_summary(cat[a]["recall"]),
                          "complete": ci_summary(cat[a]["complete"])}
    for t in TYPES:
        m = types == t
        if not m.any():
            continue
        out["by_type"][t] = {a: ci_summary(cat[a]["recall"][m]) for a in ARMS}
        out["by_type"][t]["n"] = int(m.sum())
        out["by_type"][t]["contrasts"] = {
            f"bear_vs_{b}": paired_summary(cat["bear"]["recall"][m], cat[b]["recall"][m])
            for b in ARMS[1:]}
    for b in ARMS[1:]:
        out["contrasts"][f"bear_vs_{b}"] = {
            "recall": paired_summary(cat["bear"]["recall"], cat[b]["recall"]),
            "mcnemar_complete": mcnemar_summary(cat["bear"]["complete"], cat[b]["complete"])}
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale-points", nargs="+", type=int, default=SCALE_POINTS)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "results" / "cpa_maintained.json")
    ap.add_argument("--log-file", type=Path,
                    default=REPO_ROOT / "results" / "cpa_maintained_output.txt")
    args = ap.parse_args()
    require_bear_040()
    refuse_overwrite(args.output, args.log_file)
    log = args.log_file.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        t0 = time.time()
        print("=== Maintained CPA vs stale CPA vs BEAR on novel contexts (WP5), BEAR 0.4.0 ===")
        print(f"BGE-base on the CPU, k={TOP_K}, theta {THRESHOLD}, priority weight {PRIORITY_WEIGHT}, "
              f"mandatory safety+global. Scale points {args.scale_points}.")
        embedder = Embedder(model_name=EMBEDDING_MODEL, dim=768,
                            query_prefix="Represent this sentence for retrieving relevant documents: ",
                            device="cpu")
        wiring = multi_wiring_change()
        results = []
        for n in args.scale_points:
            res = run_scale(n, embedder)
            results.append(res)
            m = res["maintenance"]
            line = "  ".join(f"{a} {res['arms'][a]['recall']['mean']:.3f}"
                             f" (fraud {res['arms'][a]['by_type'].get('unknown_dept', float('nan')):.3f})"
                             for a in ARMS)
            print(f"\n{n:>4} agents ({res['corpus_size_with_new_dept']} instructions, "
                  f"{res['n_queries']} novel queries): {line}")
            print(f"     maintenance per new department: CPA tables +{m['cpa_table_diff']['keys_added']} "
                  f"key(s), +{m['cpa_table_diff']['entries_added']} entries, wiring formula "
                  f"+{m['cpa_wiring_lines_added']} line(s); BEAR wiring +0, "
                  f"{m['bear_tag_annotations_with_new_instructions']} required tags written with "
                  f"the new instructions")
        pool = pooled(results)
        print(f"\nMulti-department wiring change (one time): {wiring}")
        print("\n--- Pooled over scale points (novel-context recall, 95% bootstrap CI) ---")
        for a in ARMS:
            print(f"  {a:<22} recall {fmt(pool['arms'][a]['recall'])}   "
                  f"all-expected {pool['arms'][a]['complete']['mean']:.3f}")
        for t, e in pool["by_type"].items():
            print(f"  {t:<16} (n={e['n']}): " + "  ".join(f"{a} {e[a]['mean']:.3f}" for a in ARMS))
        print("\n--- Paired contrasts, pooled ---")
        for k_, c in pool["contrasts"].items():
            mc = c["mcnemar_complete"]
            print(f"  {k_:<32} recall {fmt_delta(c['recall'])}   McNemar(all expected) "
                  f"b={mc['b_a_right_b_wrong']} c={mc['c_a_wrong_b_right']} p={mc['p_value']:.4f}")
        if "unknown_dept" in pool["by_type"]:
            print("  New department only:")
            for k_, c in pool["by_type"]["unknown_dept"]["contrasts"].items():
                print(f"    {k_:<30} {fmt_delta(c)}")
        out = {"settings": {"k": TOP_K, "theta": THRESHOLD, "priority_weight": PRIORITY_WEIGHT,
                            "embedding_model": EMBEDDING_MODEL, "device": "cpu"},
               "multi_dept_wiring_change": wiring, "scale_points": results, "pooled": pool,
               "provenance": bear_provenance()}
        args.output.write_text(json.dumps(out, indent=1, default=json_default), encoding="utf-8")
        print(f"\nWrote {args.output}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "cpa_maintained", **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
