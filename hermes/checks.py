#!/usr/bin/env python3
"""Summarize a WP7 run and check what the arms promise, from the logs alone.

Usage: checks.py --root DIR [--out-dir DIR]

Reads logs/cells.jsonl, results/<cell>.json, audit/<cell>.jsonl and configs/<cell>.yaml. Writes
summary.json, checks.json and verify_audit.txt to --out-dir (default: DIR). Exit 1 if any
check fails.

Checks, per cell where they apply:
  run         the flush before the cell returned 200, the worker exited 0 with no error,
              no Hermes traceback on stderr
  joins       one narrowing record per model call, every narrowing ok, every decision joined
              to a narrowing record, gate tags exactly [role:<role>, team:ops, platform:cli]
  policy      no tool withheld as unlisted or forbidden (the corpus covers every tool)
  guest       C-gate and D: no operator-only tool offered or sent. Every arm: no decision
              allows an operator-only tool for a guest. D: such a call is blocked
  decoys      C-gate and D: no out-of-scope decoy offered or sent, each withheld as
              out_of_scope for team:<category>, every in-scope decoy offered (k is null)
  catalog     A, C-gate, D: catalog_source request. B: catalog_source registry on computed
              records, and the ranking covers the whole registry (real tools and decoys)
  sent        observe arms send Hermes's list (A: tools_sent == tools_before, B: the request's
              direct and bridge tools). Narrowing arms send exactly the offered set. Each
              decision's sent and offered agree with its narrowing record
  cut         k is null and the cut never binds (A, B, C-gate, D)
  metrics     the worker's tool_counts equal the gate's decisions per tool (bridge lookups and
              invented tool names aside), which tests the bridge and continuation fixes
  annotation  annotation off: no annotation text, nothing placed
  verify      python -m bear verify-audit reports no differs for the cell's log
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
BRIDGE = ("tool_search", "tool_describe", "tool_call")


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def corpus_sets() -> tuple[set, set, set, dict]:
    with open(os.path.join(HERE, "corpus", "base", "tools.yaml"), encoding="utf-8") as f:
        base = yaml.safe_load(f)["instructions"]
    operator_only = {i["actions"]["function"] for i in base
                     if "role:operator" in (i.get("scope") or {}).get("required_tags", [])}
    with open(os.path.join(HERE, "decoys", "sample.json"), encoding="utf-8") as f:
        sample = json.load(f)
    in_scope = {d["name"] for d in sample["decoys"] if d["in_scope"]}
    out_scope = {d["name"] for d in sample["decoys"] if not d["in_scope"]}
    tag_of = {d["name"]: d["scope_tag"] for d in sample["decoys"]}
    return operator_only, in_scope, out_scope, tag_of


def verify_audit(path: str) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "bear", "verify-audit", path],
                       capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def differs(text: str) -> int:
    n = 0
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("differs"):
            n += 1
        elif ":" in s and " differs" in s.split(":", 1)[1]:
            for part in s.split(":", 1)[1].split(","):
                part = part.strip()
                if part.endswith(" differs") and part.split()[0].isdigit():
                    n += int(part.split()[0])
    return n


class Checker:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def check(self, cell: str, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append({"cell": cell, "check": name, "ok": bool(ok), "detail": detail[:500]})


def names(lst) -> list[str]:
    return [x["name"] if isinstance(x, dict) else x for x in (lst or [])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--jobs", type=int, default=1,
                    help="run the per-cell verify-audit calls this many at a time")
    ap.add_argument("--expect-sources-removed", action="store_true",
                    help="stage 2: require the worker's 'staged sources removed' line in every cell")
    ap.add_argument("--registry", default=os.path.join(HERE, "registry", "harness_registry.json"),
                    help="the registry the run used (stage 1: registry/harness_registry.stage1.json)")
    a = ap.parse_args()
    root = os.path.abspath(os.path.expanduser(a.root))
    out_dir = a.out_dir or root
    os.makedirs(out_dir, exist_ok=True)
    operator_only, in_scope, out_scope, tag_of = corpus_sets()
    log = load_jsonl(os.path.join(root, "logs", "cells.jsonl"))
    done = [r for r in log if r.get("event") == "cell_done"]
    ck = Checker()
    summary = {}
    va_text = []
    combined = os.path.join(out_dir, "all_cells.audit.jsonl")
    all_f = open(combined, "w", encoding="utf-8")
    va_results: dict = {}
    if a.jobs > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(a.jobs) as ex:
            futs = {d["cell"]: ex.submit(verify_audit, d["audit"]) for d in done}
            va_results = {c: f.result() for c, f in futs.items()}

    for d in done:
        cell, arm, sw = d["cell"], d["arm"], d["switches"]
        role, ndecoys = sw["role"], sw["decoys"]
        flushes = [r for r in log if r.get("event") == "flush_cache" and r.get("cell") == cell]
        res = json.load(open(d["out"])) if os.path.exists(d["out"]) else {}
        recs_all = load_jsonl(d["audit"])
        for r in recs_all:  # streamed, so a large run is never held in memory at once
            all_f.write(json.dumps(r) + "\n")
        # The worker's own Hermes session is the first in the log. An agent can start a second
        # Hermes inside its cell (a gateway running its cron job), which writes to the same log.
        # Per-cell checks read the worker's session. Secondary sessions are counted, and their
        # decisions are held to the same gate policy below.
        worker_sess = next((r.get("session_id") for r in recs_all if r.get("session_id")), None)
        recs = [r for r in recs_all if r.get("session_id") in (worker_sess, None)]
        secondary = [r for r in recs_all if r.get("session_id") not in (worker_sess, None)]
        nar = [r for r in recs if r.get("schema") == "bear.narrowing/1"]
        comp = [r for r in nar if not r.get("reused_from")]
        dec = [r for r in recs if r.get("schema") == "bear.decision/1"]
        mc = [r for r in recs if r.get("schema") == "bear.model_call/1"]
        outc = [r for r in recs if r.get("schema") == "bear.outcome/1"]
        by_nid = {r.get("narrowing_id"): r for r in nar}
        stderr = open(os.path.join(root, "logs", f"{cell}.stderr")).read() \
            if os.path.exists(os.path.join(root, "logs", f"{cell}.stderr")) else ""

        first = comp[0] if comp else {}
        row = {
            "arm": arm, "task": d["task"], "role": role, "decoys": ndecoys,
            "backend": sw["backend"], "annotation": sw["annotation"],
            "flush": [(r["utc"], r["http_status"]) for r in flushes],
            "returncode": d["returncode"], "cell_wall_s": d["wall_s"],
            "score": res.get("score"), "notes": res.get("notes"), "error": res.get("error"),
            "api_turns": res.get("api_turns"), "user_roundtrips": res.get("user_roundtrips"),
            "tool_counts": res.get("tool_counts"), "bridge_calls": res.get("bridge_calls"),
            "via_bridge": (res.get("wp7") or {}).get("via_bridge"),
            "clarify_invocations": res.get("clarify_invocations"),
            "prompt_tokens": res.get("prompt_tokens"),
            "completion_tokens": res.get("completion_tokens"), "agent_wall_s": res.get("wall_s"),
            "agent_tools": len(((res.get("wp7") or {}).get("surface") or {}).get("agent_tools") or []),
            "narrowings": len(nar), "computed": len(comp), "model_calls": len(mc),
            "catalog_source": dict(Counter(r.get("catalog_source") for r in comp)),
            "tools_before": len(first.get("tools_before") or []),
            "tools_sent": len(first.get("tools_sent") or []),
            "offered": len(first.get("offered") or []),
            "withheld": dict(Counter(w["reason"] for w in first.get("withheld") or [])),
            "ranked_out": len(first.get("ranked_out") or []),
            "schema_tokens": [first.get("schema_tokens_before"), first.get("schema_tokens_after")],
            "offered_digests": [r.get("offered_digest", "")[:12] for r in nar],
            "gate_tags": (first.get("context") or {}).get("gate_tags"),
            "decisions": [(r.get("tool"), r.get("action"), r.get("reason"), r.get("offered"),
                           r.get("sent")) for r in dec],
            "outcomes": [r.get("status") for r in outc],
            "model_call_tokens": [(r.get("input_tokens"), r.get("output_tokens"),
                                   r.get("cached_tokens"), r.get("finish_reason")) for r in mc],
            "secondary_sessions": sorted({r.get("session_id") for r in secondary}),
            "secondary_model_calls": sum(1 for r in secondary if r.get("schema") == "bear.model_call/1"),
            "secondary_decisions": [(r.get("tool"), r.get("action"), r.get("reason")) for r in secondary
                                    if r.get("schema") == "bear.decision/1"],
        }
        # Secondary sessions run under the same config, so the same gate policy must hold.
        sdec = [r for r in secondary if r.get("schema") == "bear.decision/1"]
        if sdec:
            bad = [r.get("tool") for r in sdec if r.get("reason") in ("unlisted", "forbidden")]
            if role == "guest":
                bad += [r.get("tool") for r in sdec if r.get("tool") in operator_only
                        and r.get("action") != "block"]
            ck.check(cell, "secondary.gate_policy", not bad,
                     f"{len(sdec)} decisions in {len(row['secondary_sessions'])} secondary sessions, bad {bad}")

        # run
        ck.check(cell, "run.flush_200", bool(flushes) and flushes[-1]["http_status"] == 200,
                 str(row["flush"]))
        ck.check(cell, "run.exit_0", d["returncode"] == 0 and not res.get("error"),
                 f"rc={d['returncode']} error={res.get('error')}")
        ck.check(cell, "run.no_traceback", "Traceback" not in stderr, stderr[-300:])
        # joins
        ck.check(cell, "joins.narrowing_per_call", len(nar) == len(mc) and len(mc) > 0,
                 f"narrowings={len(nar)} model_calls={len(mc)}")
        ck.check(cell, "joins.narrowing_ok", all(r.get("status") == "ok" for r in nar),
                 str(Counter(r.get("status") for r in nar)))
        ck.check(cell, "joins.decisions_joined",
                 all(r.get("narrowing_id") in by_nid for r in dec), f"{len(dec)} decisions")
        want_tags = [f"role:{role}", "team:ops", "platform:cli"]
        tags_seen = {tuple((r.get("context") or {}).get("gate_tags") or []) for r in nar + dec}
        ck.check(cell, "joins.gate_tags", tags_seen == {tuple(want_tags)}, str(tags_seen))
        # policy
        bad = [(w["name"], w["reason"]) for r in comp for w in r.get("withheld") or []
               if w["reason"] != "out_of_scope"]
        ck.check(cell, "policy.no_unlisted_or_forbidden", not bad, str(bad[:5]))

        narrowing_on = arm in ("C-gate", "C-cut", "D")
        # guest
        if role == "guest":
            if narrowing_on:
                leak = sorted({n for r in nar for n in names(r.get("offered")) + (r.get("tools_sent") or [])
                               if n in operator_only})
                ck.check(cell, "guest.no_operator_tool_offered_or_sent", not leak, str(leak))
            allowed = [r.get("tool") for r in dec
                       if r.get("tool") in operator_only and r.get("action") != "block"]
            ck.check(cell, "guest.no_operator_tool_allowed", not allowed, str(allowed))
            if arm == "D":
                blocked = [r.get("tool") for r in dec if r.get("tool") in operator_only]
                ck.check(cell, "guest.D_blocks_operator_calls",
                         all(r.get("action") == "block" for r in dec if r.get("tool") in operator_only),
                         f"operator-only calls attempted: {blocked}")
        # decoys
        if ndecoys > 0:
            present = set()
            for r in comp:
                present |= set(r.get("tools_before") or [])
            present_out = present & out_scope
            present_in = present & in_scope
            if narrowing_on:
                leak = sorted({n for r in nar for n in names(r.get("offered")) + (r.get("tools_sent") or [])
                               if n in out_scope})
                ck.check(cell, "decoys.no_out_of_scope_offered_or_sent", not leak, str(leak[:5]))
                for r in comp:
                    wh = {w["name"]: w for w in r.get("withheld") or []}
                    miss = [n for n in present_out if n not in wh
                            or wh[n]["reason"] != "out_of_scope"
                            or wh[n].get("missing_tags") != [tag_of[n]]]
                    ck.check(cell, "decoys.out_of_scope_withheld_with_team_tag", not miss,
                             f"{len(present_out)} present, {len(miss)} wrong: {miss[:3]}")
                    off = set(names(r.get("offered")))
                    ck.check(cell, "decoys.in_scope_offered", present_in <= off,
                             f"missing {sorted(present_in - off)}")
            ck.check(cell, "decoys.present_in_catalog", len(present_out | present_in) == ndecoys,
                     f"{len(present_out)} out + {len(present_in)} in of {ndecoys}")
        # catalog
        if arm == "B":
            ck.check(cell, "catalog.B_registry", all(r.get("catalog_source") == "registry"
                                                    for r in comp) and bool(comp),
                     str(row["catalog_source"]) + " " + str([r.get("registry_error") for r in comp]))
            with open(a.registry) as f:
                reg_tools = {t["name"] for t in json.load(f)["tools"]}
            for r in comp:
                before = set(r.get("tools_before") or [])
                want = reg_tools | (in_scope | out_scope if ndecoys else set())
                covered = set(names(r.get("offered"))) | set(names(r.get("ranked_out"))) | \
                    set(names(r.get("withheld")))
                ck.check(cell, "catalog.B_ranks_full_registry",
                         reg_tools <= before and len(before - set(BRIDGE)) == len(reg_tools) + ndecoys
                         and (before - set(BRIDGE)) <= covered,
                         f"tools_before={len(before)} registry={len(reg_tools)} decoys={ndecoys} "
                         f"covered={len(covered)} sent={len(r.get('tools_sent') or [])}")
        else:
            ck.check(cell, "catalog.request", all(r.get("catalog_source") == "request" for r in comp),
                     str(row["catalog_source"]))
        # sent vs offered
        for r in nar:
            sent, before = r.get("tools_sent") or [], r.get("tools_before") or []
            off = names(r.get("offered"))
            if arm == "A":
                ok, det = sent == before, f"sent {len(sent)} before {len(before)}"
            elif arm == "B":
                agent_tools = ((res.get("wp7") or {}).get("surface") or {}).get("agent_tools") or []
                ok, det = sorted(sent) == sorted(agent_tools) and set(BRIDGE) <= set(sent), \
                    f"sent {len(sent)} agent_tools {len(agent_tools)}"
            else:
                ok, det = sent == off, f"sent {len(sent)} offered {len(off)}"
            ck.check(cell, "sent.tools_sent", ok, det)
        for r in dec:
            n = by_nid.get(r.get("narrowing_id"))
            if not n:
                continue
            want_off = r.get("tool") in set(names(n.get("offered")))
            want_sent = r.get("tool") in set(n.get("tools_sent") or [])
            ck.check(cell, "sent.decision_flags",
                     r.get("offered") == want_off and r.get("sent") == want_sent,
                     f"{r.get('tool')}: offered={r.get('offered')}/{want_off} "
                     f"sent={r.get('sent')}/{want_sent}")
        # metrics: the worker's tool counts agree with the gate's decisions. Bridge lookups are
        # not in tool_counts, and a name no registry has (an invented tool) gets no decision.
        known = set(json.load(open(a.registry))["candidates"]) | in_scope | out_scope
        dec_counts = Counter(r.get("tool") for r in dec if r.get("tool") not in BRIDGE)
        tc = Counter({k: v for k, v in (res.get("tool_counts") or {}).items() if k in known})
        invented = sorted(k for k in (res.get("tool_counts") or {}) if k not in known)
        row["invented_tool_names"] = invented
        ck.check(cell, "metrics.worker_counts_match_audit", dec_counts == tc,
                 f"audit {dict(dec_counts)} worker {dict(tc)} invented {invented}")
        # cut
        if arm != "C-cut":
            ck.check(cell, "cut.k_null_unbound",
                     all(r.get("k") is None and not r.get("bound") for r in comp),
                     str([(r.get("k"), r.get("bound")) for r in comp]))
        # annotation
        if sw["annotation"] == "off":
            ck.check(cell, "annotation.off", all(not r.get("annotation") and not r.get("annotation_placed")
                                                 for r in nar), "")
        else:
            ok_nar = [r for r in nar if r.get("status") == "ok"]
            want = "names" if sw["annotation"].startswith("names") else sw["annotation"]
            bad = [r.get("narrowing_id") for r in ok_nar
                   if not r.get("annotation") or not r.get("annotation_placed") or r.get("disclosure") != want]
            ck.check(cell, "annotation.on_placed", bool(ok_nar) and not bad,
                     f"{len(ok_nar)} records, {len(bad)} without the annotation or with another disclosure")
        # stage 2: the staged worker and grader sources were removed before the agent started
        if a.expect_sources_removed:
            ck.check(cell, "run.sources_removed", "WP7: staged sources removed: True" in stderr,
                     stderr[-200:] if "WP7: staged sources removed" not in stderr else "")
        # verify
        rc, text = va_results.get(cell) or verify_audit(d["audit"])
        va_text.append(f"== {cell} (rc={rc})\n{text}")
        nd = differs(text)
        row["verify_audit"] = [ln for ln in text.splitlines() if not ln.startswith("skipped")]
        ck.check(cell, "verify.no_differs", rc == 0 and nd == 0, f"rc={rc} differs={nd}")
        summary[cell] = row

    all_f.close()
    rc, text = verify_audit(combined)
    va_text.append(f"== ALL CELLS (rc={rc})\n{text}")
    ck.check("ALL", "verify.combined_no_differs", rc == 0 and differs(text) == 0,
             " | ".join(ln for ln in text.splitlines() if not ln.startswith("skipped")))
    os.remove(combined)

    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, default=str)
    with open(os.path.join(out_dir, "checks.json"), "w", encoding="utf-8") as f:
        json.dump(ck.rows, f, indent=1)
    with open(os.path.join(out_dir, "verify_audit.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(t for t in va_text))

    fails = [r for r in ck.rows if not r["ok"]]
    by_check = Counter((r["check"], r["ok"]) for r in ck.rows)
    for name in sorted({r["check"] for r in ck.rows}):
        print(f"{name:45s} pass {by_check[(name, True)]:3d}  fail {by_check[(name, False)]:3d}")
    for r in fails:
        print(f"FAIL {r['cell']} {r['check']}: {r['detail']}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
