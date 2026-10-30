"""WP4: token efficiency attributable to governance (BEAR 0.4.0).

Reads the k=50 ranked lists written by dump_toolbench_lists.py (ToolBench as
in Table 3, MetaTool+Tags as in Table 6), for every backend, governed and
ungated, and reports:

1. Recall@k for k = 1..50, governed and ungated, with 95% bootstrap CIs, and
   the paired governed-minus-ungated difference at every k (bootstrap CI and
   p-value, paired t-test, paired Cohen's d = mean(diff)/sd(diff), the same d
   eval_toolbench.py reports).
2. For recall targets 0.80, 0.90 and 0.95: the smallest k at which mean
   Recall@k reaches the target, and the mean prompt tokens at that k, each
   with a bootstrap CI (queries resampled jointly for both conditions, so the
   token difference is paired). Per query, the k at which every gold item is
   in the list (k_full; 51 if not by k=50), compared with a Wilcoxon
   signed-rank test.
3. ToolBench prompt tokens per condition at k=5: the monolithic prompt with
   all 3,225 tools, and the governed and ungated top-5 prompts per backend.

Token counting
  Primary: tiktoken cl100k_base, the counter eval_governance_ablation.py and
  eval_retrieval_backends.py use for the Pet Sim token table. Two prompt
  definitions are counted:
    * e2e prompt (ToolBench only). The exact prompt eval_toolbench_e2e.py
      sends for Tables 7 to 9: its system preamble, one "- name: description"
      line per tool (the tool's action schema, description cut at 400 chars),
      and the query as the user message. Chat-template tokens are excluded.
    * BEAR content. The instruction content of the retrieved tools as BEAR
      stores it (eval_toolbench.py's corpus text), summed per tool.
  A prompt's token count is the sum of per-line counts. cl100k's
  pre-tokenizer never merges across a newline followed by "- ", so the sum is
  exact. The script checks that on a seeded sample against tokenizing the
  whole prompt.
  Secondary (ToolBench k=5 and monolithic only): the Mistral-Nemo-Instruct-2407
  tekken tokenizer in its v3 instruct format, the executor of Tables 7 and 8, to check
  the manuscript's "about 82k" monolithic figure.

Bootstrap: percentile, 10,000 resamples of queries, seed 42, as stat_utils.

Before using a list prefix as the top-k, the script checks it against the
k=5 runs (per-query recall and NDCG must equal those of the main
eval_toolbench run) and reports the dumper's nesting check.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

KMAX = 50
TARGETS = (0.80, 0.90, 0.95)
B = 10_000
SEED = 42
BACKENDS = [("bge", "BGE"), ("bge-m3", "BGE-M3"), ("qwen3-0.6b", "Qwen3-0.6B"),
            ("qwen3-4b", "Qwen3-4B"), ("bm25", "BM25"), ("hash", "Hash"),
            ("nemotron", "Nemotron")]

E2E_PREAMBLE = (
    "You are a tool-selection assistant. Given the user's query and the "
    "list of available tools, choose the single most appropriate tool. "
    "Respond with a JSON object {\"tool\": \"<exact tool name>\"} and nothing else."
    "\n\nAvailable tools:\n"
)


def slug(name: str) -> str:
    import re
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def boot_counts(n: int, b: int = B, seed: int = SEED, chunk: int = 250):
    """Yield (chunk, n) resample count matrices, float32."""
    rng = np.random.default_rng(seed)
    done = 0
    while done < b:
        m = min(chunk, b - done)
        idx = rng.integers(0, n, size=(m, n))
        counts = np.zeros((m, n), dtype=np.float32)
        for r in range(m):
            counts[r] = np.bincount(idx[r], minlength=n)
        done += m
        yield counts


def boot_means(mats: list[np.ndarray], n: int) -> list[np.ndarray]:
    """Bootstrap means of the columns of each (n, c) matrix, resampling rows
    jointly across matrices. Returns a (B, c) array per matrix."""
    outs = [[] for _ in mats]
    mats32 = [m.astype(np.float32) for m in mats]
    for counts in boot_counts(n):
        for j, m in enumerate(mats32):
            outs[j].append(counts @ m / n)
    return [np.concatenate(o, axis=0) for o in outs]


def ci(x: np.ndarray, axis=0):
    lo, hi = np.percentile(x, [2.5, 97.5], axis=axis)
    return lo, hi


def first_reach(curves: np.ndarray, target: float) -> np.ndarray:
    """First k (1-based) where curve >= target along the last axis; KMAX+1 if never."""
    ok = curves >= target - 1e-12
    k = np.where(ok.any(axis=-1), ok.argmax(axis=-1) + 1, KMAX + 1)
    return k


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def cl100k():
    import tiktoken
    return tiktoken.get_encoding("cl100k_base")


def e2e_lines(corpus_ids: list[str]) -> tuple[dict, list[str]]:
    """Map instruction id -> e2e prompt line; also every line, corpus order."""
    import eval_toolbench_e2e as e2e
    corpus, _ = e2e.load_toolbench_data()
    lines = {}
    order = []
    for inst in corpus:
        s = e2e.make_tool_schema(inst)
        if s and s.get("name"):
            line = f"- {s['name']}: {(s.get('description') or '').strip()[:400]}"
            lines[inst.id] = line
            order.append(line)
    missing = [i for i in corpus_ids if i not in lines]
    if missing:
        raise RuntimeError(f"{len(missing)} ids have no e2e schema, e.g. {missing[:3]}")
    return lines, order


def mistral_tokenizer():
    """Mistral-Nemo-Instruct-2407's tekken tokenizer, built from the cached
    tekken.json with tiktoken (the way mistral_common's Tekkenizer builds it:
    the first default_vocab_size - default_num_special_tokens ranks, the
    config's split pattern). Only token counts are needed, so the special-token
    id offset is irrelevant."""
    import base64
    import glob
    import os

    import tiktoken
    hub = os.path.expanduser("~/.cache/huggingface/hub")
    path = glob.glob(f"{hub}/models--mistralai--Mistral-Nemo-Instruct-2407/snapshots/*/tekken.json")[0]
    d = json.loads(Path(path).read_text())
    cfg = d["config"]
    n_inner = cfg["default_vocab_size"] - cfg["default_num_special_tokens"]
    ranks = {base64.b64decode(t["token_bytes"]): t["rank"] for t in d["vocab"][:n_inner]}
    return tiktoken.Encoding(name="tekken-mistral-nemo", pat_str=cfg["pattern"],
                             mergeable_ranks=ranks, special_tokens={})


def mistral_count(tok, system: str, user: str) -> int:
    """Tokens of one chat turn under Mistral's v3 tekken instruct format:
    [BOS][INST] system + "\\n\\n" + user [/INST], 3 control tokens."""
    return 3 + len(tok.encode(system + "\n\n" + user, disallowed_special=()))


# ---------------------------------------------------------------------------
# Per benchmark
# ---------------------------------------------------------------------------

def load_lists(d: Path, cond: str):
    p = d / f"{slug(cond)}.npz"
    if not p.exists():
        return None, None
    z = np.load(p)
    side = json.loads(p.with_suffix(".json").read_text())
    return z, side


def recall_matrix(idx: np.ndarray, expected: list[list[int]], n_exp: list[int]) -> np.ndarray:
    n = idx.shape[0]
    hits = np.zeros((n, KMAX), dtype=np.float32)
    for i in range(n):
        e = set(expected[i])
        h = np.array([1.0 if (v >= 0 and int(v) in e) else 0.0 for v in idx[i, :KMAX]])
        hits[i] = np.cumsum(h)
    denom = np.maximum(np.asarray(n_exp, dtype=np.float32), 1)[:, None]
    return hits / denom


def ndcg5(idx_row, e: set, n_exp: int) -> float:
    dcg = sum(1.0 / np.log2(r + 2) for r, v in enumerate(idx_row[:5]) if v >= 0 and int(v) in e)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(n_exp, 5)))
    return dcg / idcg if idcg else 0.0


def token_matrix(idx: np.ndarray, per_item: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Cumulative tokens of the top-k items plus a per-query base."""
    tok = np.where(idx[:, :KMAX] >= 0, per_item[np.maximum(idx[:, :KMAX], 0)], 0)
    return base[:, None] + np.cumsum(tok, axis=1)


def analyse(bench: str, d: Path, main_runs: dict, enc, args, e2e: dict | None) -> dict:
    meta = json.loads((d / "meta.json").read_text())
    ids = meta["corpus_ids"]
    queries = meta["queries"]
    n = len(queries)
    expected = [q["expected"] for q in queries]
    n_exp = [q["n_expected"] for q in queries]
    print(f"\n=== {bench}: {len(ids)} items, {n} queries ===", flush=True)

    # BEAR content tokens per item (eval_toolbench corpus text).
    import eval_toolbench as et
    if bench == "toolbench":
        corpus, _, _ = et.load_toolbench_corpus_and_queries()
    else:
        corpus, _ = et.load_metatool_corpus_tagged(et.METATOOL_DIR / "plugin_tags.json")
    content = {inst.id: inst.content for inst in corpus}
    content_tok = np.array([len(enc.encode(content[i])) for i in ids], dtype=np.float32)
    zero_base = np.zeros(n, dtype=np.float32)
    measures = {"bear_content": (content_tok, zero_base)}
    if e2e is not None:
        line_tok = np.array([len(enc.encode(e2e["lines"][i] + "\n")) for i in ids], dtype=np.float32)
        base = np.array([len(enc.encode(E2E_PREAMBLE)) + len(enc.encode(q["text"]))
                         for q in queries], dtype=np.float32)
        measures["e2e_prompt"] = (line_tok, base)

    out = {"n_queries": n, "n_items": len(ids), "backends": {}}
    for key, lab in BACKENDS:
        g_name, u_name = f"BEAR+{lab} (gov)", f"{lab} (no gov)"
        zg, sg = load_lists(d, g_name)
        zu, su = load_lists(d, u_name)
        if zg is None or zu is None:
            print(f"  {lab}: lists missing, skipped")
            continue
        t0 = time.time()
        Rg = recall_matrix(zg["idx"], expected, n_exp)
        Ru = recall_matrix(zu["idx"], expected, n_exp)
        rec = {"conditions": {g_name: {}, u_name: {}}}

        # Consistency with the k=5 main run.
        cons = {}
        for name, z, R in ((g_name, zg, Rg), (u_name, zu, Ru)):
            ref = main_runs.get(name)
            if ref is None:
                cons[name] = "no main-run arrays"
                continue
            r5 = R[:, 4]
            n5 = np.array([ndcg5(z["idx"][i], set(expected[i]), n_exp[i]) for i in range(n)])
            cons[name] = {
                "recall5_equal": bool(np.allclose(r5, np.asarray(ref["recall"]), atol=1e-9)),
                "ndcg5_equal": bool(np.allclose(n5, np.asarray(ref["ndcg"]), atol=1e-9)),
                "n_recall5_diff": int(np.sum(np.abs(r5 - np.asarray(ref["recall"])) > 1e-9)),
                "n_ndcg5_diff": int(np.sum(np.abs(n5 - np.asarray(ref["ndcg"])) > 1e-9)),
            }
        rec["consistency_with_k5_run"] = cons
        rec["nesting_check"] = {g_name: sg.get("nesting_check"), u_name: su.get("nesting_check")}
        rec["n_returned_lt_50"] = {g_name: int(np.sum(zg["n_returned"] < KMAX)),
                                   u_name: int(np.sum(zu["n_returned"] < KMAX))}

        # Curves with CIs, paired differences.
        D = Rg - Ru
        bg, bu, bd = boot_means([Rg, Ru, D], n)
        for name, R, bm in ((g_name, Rg, bg), (u_name, Ru, bu)):
            lo, hi = ci(bm)
            rec["conditions"][name]["recall_at_k"] = {
                "mean": R.mean(0).tolist(), "ci_lower": lo.tolist(), "ci_upper": hi.tolist()}
        dlo, dhi = ci(bd)
        sd = D.std(0, ddof=1)
        tt = [stats.ttest_rel(Rg[:, k], Ru[:, k]) if sd[k] > 0 else None for k in range(KMAX)]
        pboot = [float(min(1.0, max(2 * min((bd[:, k] <= 0).mean(), (bd[:, k] >= 0).mean()), 1 / B)))
                 for k in range(KMAX)]
        rec["paired_gov_minus_ungated"] = {
            "delta": D.mean(0).tolist(), "ci_lower": dlo.tolist(), "ci_upper": dhi.tolist(),
            "p_bootstrap": pboot,
            "t": [float(x.statistic) if x is not None else 0.0 for x in tt],
            "p_ttest": [float(x.pvalue) if x is not None else 1.0 for x in tt],
            "cohens_d_paired": [float(D[:, k].mean() / sd[k]) if sd[k] > 0 else 0.0 for k in range(KMAX)],
        }

        # k and tokens to reach recall targets.
        tgt = {}
        for mname, (per_item, base) in measures.items():
            Tg = token_matrix(zg["idx"], per_item, base)
            Tu = token_matrix(zu["idx"], per_item, base)
            btg, btu = boot_means([Tg, Tu], n)
            rec["conditions"][g_name][f"tokens_at_k_{mname}"] = Tg.mean(0).tolist()
            rec["conditions"][u_name][f"tokens_at_k_{mname}"] = Tu.mean(0).tolist()
            for t in TARGETS:
                kg, ku = int(first_reach(Rg.mean(0), t)), int(first_reach(Ru.mean(0), t))
                kgb, kub = first_reach(bg, t), first_reach(bu, t)
                entry = tgt.setdefault(f"{t:.2f}", {})
                entry["k_gov"] = kg
                entry["k_ungated"] = ku
                entry["k_gov_ci"] = [int(x) for x in np.percentile(kgb, [2.5, 97.5])]
                entry["k_ungated_ci"] = [int(x) for x in np.percentile(kub, [2.5, 97.5])]
                entry["k_reached_frac_boot"] = {"gov": float((kgb <= KMAX).mean()),
                                                "ungated": float((kub <= KMAX).mean())}

                def tok_at(meanT, k):
                    return float(meanT[k - 1]) if k <= KMAX else None
                tg_pt, tu_pt = tok_at(Tg.mean(0), kg), tok_at(Tu.mean(0), ku)
                # Bootstrap: each replicate's own k*, its own mean tokens.
                rows = np.arange(len(kgb))
                tgb = np.where(kgb <= KMAX, btg[rows, np.minimum(kgb, KMAX) - 1], np.nan)
                tub = np.where(kub <= KMAX, btu[rows, np.minimum(kub, KMAX) - 1], np.nan)
                diff = tub - tgb
                entry[f"tokens_{mname}"] = {
                    "gov": tg_pt, "ungated": tu_pt,
                    "gov_ci": np.nanpercentile(tgb, [2.5, 97.5]).tolist() if np.isfinite(tgb).any() else None,
                    "ungated_ci": np.nanpercentile(tub, [2.5, 97.5]).tolist() if np.isfinite(tub).any() else None,
                    "ungated_minus_gov": (tu_pt - tg_pt) if (tg_pt is not None and tu_pt is not None) else None,
                    "ungated_minus_gov_ci": (np.nanpercentile(diff, [2.5, 97.5]).tolist()
                                             if np.isfinite(diff).sum() > 0.95 * len(diff) else None),
                    "ratio_ungated_over_gov": (tu_pt / tg_pt) if (tg_pt and tu_pt) else None,
                }
            # Tokens at fixed k=5, paired.
            dk5 = Tu[:, 4] - Tg[:, 4]
            rec[f"tokens_k5_{mname}"] = {
                "gov_mean": float(Tg[:, 4].mean()), "ungated_mean": float(Tu[:, 4].mean()),
                "gov_ci": ci(btg[:, 4]), "ungated_ci": ci(btu[:, 4]),
                "ungated_minus_gov": float(dk5.mean()),
                "wilcoxon_p": (float(stats.wilcoxon(dk5[dk5 != 0]).pvalue)
                               if np.sum(dk5 != 0) >= 5 else None),
            }
            rec[f"tokens_k5_{mname}"]["gov_ci"] = [float(x) for x in rec[f"tokens_k5_{mname}"]["gov_ci"]]
            rec[f"tokens_k5_{mname}"]["ungated_ci"] = [float(x) for x in rec[f"tokens_k5_{mname}"]["ungated_ci"]]
            np.savez_compressed(args.outdir / f"{bench}_{key}_tokens_{mname}.npz",
                                gov=Tg.astype(np.float32), ungated=Tu.astype(np.float32))
        rec["targets"] = tgt

        # Per-query k at which every gold item is present.
        def kfull(R):
            ok = R >= 1 - 1e-9
            return np.where(ok.any(1), ok.argmax(1) + 1, KMAX + 1)
        kg_q, ku_q = kfull(Rg), kfull(Ru)
        dq = ku_q - kg_q
        rec["k_full_recall"] = {
            "gov_median": float(np.median(kg_q)), "ungated_median": float(np.median(ku_q)),
            "gov_mean_capped51": float(kg_q.mean()), "ungated_mean_capped51": float(ku_q.mean()),
            "gov_reached_frac": float((kg_q <= KMAX).mean()),
            "ungated_reached_frac": float((ku_q <= KMAX).mean()),
            "wilcoxon_p": (float(stats.wilcoxon(dq[dq != 0]).pvalue) if np.sum(dq != 0) >= 5 else None),
            "n_gov_fewer": int(np.sum(dq > 0)), "n_ungated_fewer": int(np.sum(dq < 0)),
        }
        np.savez_compressed(args.outdir / f"{bench}_{key}_recall_at_k.npz",
                            gov=Rg, ungated=Ru, k_full_gov=kg_q, k_full_ungated=ku_q)
        out["backends"][lab] = rec
        t5 = rec["targets"]
        print(f"  {lab:10s} R@5 gov={Rg[:,4].mean():.3f} ung={Ru[:,4].mean():.3f}  "
              + "  ".join(f"t={t}: k {v['k_gov']}/{v['k_ungated']}" for t, v in t5.items())
              + f"  cons={ {k: (v if isinstance(v, str) else (v['recall5_equal'] and v['ndcg5_equal'])) for k, v in cons.items()} }"
              + f" ({time.time() - t0:.0f}s)", flush=True)
    return out


def additivity_check(enc, lines: dict, d: Path, n_check: int = 300) -> dict:
    """Compare summed per-line counts with tokenizing the whole e2e prompt."""
    meta = json.loads((d / "meta.json").read_text())
    ids = meta["corpus_ids"]
    rng = np.random.default_rng(7)
    conds = [p for p in sorted(d.glob("*.npz"))]
    bad = 0
    maxdiff = 0
    for _ in range(n_check):
        z = np.load(conds[rng.integers(len(conds))])
        i = int(rng.integers(z["idx"].shape[0]))
        k = int(rng.integers(1, KMAX + 1))
        row = [int(v) for v in z["idx"][i, :k] if v >= 0]
        body = "".join(lines[ids[j]] + "\n" for j in row)
        full = len(enc.encode(E2E_PREAMBLE + body)) + len(enc.encode(meta["queries"][i]["text"]))
        summed = (len(enc.encode(E2E_PREAMBLE)) + sum(len(enc.encode(lines[ids[j]] + "\n")) for j in row)
                  + len(enc.encode(meta["queries"][i]["text"])))
        if full != summed:
            bad += 1
            maxdiff = max(maxdiff, abs(full - summed))
    return {"n_checked": n_check, "n_mismatch": bad, "max_abs_diff": maxdiff,
            "note": "prompt body counted with a trailing newline after the last tool line"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lists", required=True, help="dir with toolbench/ and metatool-tags/")
    ap.add_argument("--main-runs", nargs="*", default=[],
                    help="toolbench_eval JSONs of the k=5 runs, for the consistency check")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--benchmarks", nargs="+", default=["toolbench", "metatool-tags"])
    ap.add_argument("--no-mistral", action="store_true")
    args = ap.parse_args()
    args.outdir = Path(args.outdir)
    args.outdir.mkdir(parents=True, exist_ok=True)
    enc = cl100k()

    main_runs = {"toolbench": {}, "metatool-tags": {}}
    for p in args.main_runs:
        dd = json.loads(Path(p).read_text())
        for bench_key, mine in (("ToolBench", "toolbench"), ("MetaTool+Tags", "metatool-tags")):
            for name, e in (dd.get(bench_key) or {}).items():
                if isinstance(e, dict) and "metrics" in e:
                    main_runs[mine][name] = e["metrics"]

    result = {"kmax": KMAX, "targets": TARGETS, "bootstrap": {"B": B, "seed": SEED},
              "token_counter": "tiktoken cl100k_base", "benchmarks": {}}
    lists = Path(args.lists)
    e2e = None
    if "toolbench" in args.benchmarks:
        meta = json.loads((lists / "toolbench" / "meta.json").read_text())
        lines, all_lines = e2e_lines(meta["corpus_ids"])
        e2e = {"lines": lines}
        result["e2e_additivity_check"] = additivity_check(enc, lines, lists / "toolbench")
        print("additivity:", result["e2e_additivity_check"], flush=True)
        # Monolithic and k=5 prompt tokens (cl100k).
        mono_body = "\n".join(all_lines)
        mono_sys = E2E_PREAMBLE + mono_body
        mono_sys_tok = len(enc.encode(mono_sys))
        qtok = np.array([len(enc.encode(q["text"])) for q in meta["queries"]], dtype=float)
        result["toolbench_monolithic"] = {
            "n_tools": len(all_lines),
            "cl100k_system_tokens": mono_sys_tok,
            "cl100k_mean_prompt_tokens": float(mono_sys_tok + qtok.mean()),
            "chars": len(mono_sys),
            "e2e_preflight_estimate_tokens": len(mono_body) / 3.0 + 1024,
        }
        if not args.no_mistral:
            try:
                tok = mistral_tokenizer()
                sample = [q["text"] for q in meta["queries"][:50]]
                exact = [mistral_count(tok, mono_sys, s) for s in sample]
                result["toolbench_monolithic"]["mistral_nemo_chat_tokens_first50_mean"] = float(np.mean(exact))
                result["toolbench_monolithic"]["mistral_nemo_chat_tokens_first50_range"] = [int(min(exact)), int(max(exact))]
                result["mistral_tokenizer"] = ("mistralai/Mistral-Nemo-Instruct-2407 tekken.json via tiktoken; "
                                               "[BOS][INST] system + blank line + user [/INST]")
                e2e["mistral"] = tok
            except Exception as exc:  # noqa: BLE001
                result["mistral_tokenizer_error"] = repr(exc)
                print("Mistral tokenizer unavailable:", exc)

    for bench in args.benchmarks:
        result["benchmarks"][bench] = analyse(bench, lists / bench, main_runs.get(bench, {}),
                                              enc, args, e2e if bench == "toolbench" else None)

    # Mistral-Nemo counts at k=5, exact per query (ToolBench).
    if e2e is not None and "mistral" in e2e:
        tok = e2e["mistral"]
        meta = json.loads((lists / "toolbench" / "meta.json").read_text())
        ids = meta["corpus_ids"]
        mk5 = {}
        for key, lab in BACKENDS:
            for cond in (f"BEAR+{lab} (gov)", f"{lab} (no gov)"):
                z, _ = load_lists(lists / "toolbench", cond)
                if z is None:
                    continue
                counts = []
                for i, q in enumerate(meta["queries"]):
                    row = [int(v) for v in z["idx"][i, :5] if v >= 0]
                    system = E2E_PREAMBLE + "\n".join(e2e["lines"][ids[j]] for j in row)
                    counts.append(mistral_count(tok, system, q["text"]))
                c = np.asarray(counts, dtype=float)
                mk5[cond] = {"mean": float(c.mean()), "min": int(c.min()), "max": int(c.max())}
        result["toolbench_k5_mistral_nemo_chat_tokens"] = mk5

    try:
        import wp0_common
        result["_provenance"] = wp0_common.provenance({"script": "evals/wp0_v040/wp4_token_efficiency.py"})
    except Exception:  # noqa: BLE001
        pass
    out = args.outdir / "wp4_token_efficiency.json"
    out.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
