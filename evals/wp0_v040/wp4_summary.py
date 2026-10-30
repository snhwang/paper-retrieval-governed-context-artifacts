"""Markdown summary of wp4_token_efficiency.json for the report."""
import json
import sys

d = json.load(open(sys.argv[1]))
NA = "not reached by k=50"


def kfmt(k, ci):
    if k is None or k > 50:
        return NA
    lo, hi = ci or (None, None)
    hi_s = ">50" if hi is not None and hi > 50 else hi
    return f"{k} [{lo}, {hi_s}]"


def tfmt(x, ci):
    if x is None:
        return "n/a"
    return f"{x:,.0f} [{ci[0]:,.0f}, {ci[1]:,.0f}]" if ci else f"{x:,.0f}"


for bench, B in d["benchmarks"].items():
    print(f"\n#### {bench} ({B['n_queries']} queries, {B['n_items']} items)\n")
    print("| Backend | Recall@5 gov / ungated | Δ@5 [95% CI], d | k for 0.80 gov / ungated | k for 0.90 | k for 0.95 "
          "| e2e prompt tokens at k for 0.80, gov / ungated | k=5 e2e prompt tokens gov / ungated |")
    print("|---|---|---|---|---|---|---|---|")
    for b, v in B["backends"].items():
        if not isinstance(v, dict) or "conditions" not in v:
            continue
        cs = list(v["conditions"].values())
        rg, ru = cs[0]["recall_at_k"]["mean"][4], cs[1]["recall_at_k"]["mean"][4]
        p = v["paired_gov_minus_ungated"]
        dlt = f"{p['delta'][4]:+.3f} [{p['ci_lower'][4]:+.3f}, {p['ci_upper'][4]:+.3f}], {p['cohens_d_paired'][4]:.2f}"
        t = v["targets"]
        cols = []
        for tg in ("0.80", "0.90", "0.95"):
            x = t[tg]
            cols.append(f"{kfmt(x['k_gov'], x.get('k_gov_ci'))} / {kfmt(x['k_ungated'], x.get('k_ungated_ci'))}")
        te = t["0.80"].get("tokens_e2e_prompt") or t["0.80"].get("tokens_bear_content") or {}
        kind = "e2e" if t["0.80"].get("tokens_e2e_prompt") else "content"
        tok80 = f"{tfmt(te.get('gov'), te.get('gov_ci'))} / {tfmt(te.get('ungated'), te.get('ungated_ci'))} ({kind})"
        k5 = v.get("tokens_k5_e2e_prompt") or v.get("tokens_k5_bear_content") or {}
        tok5 = (f"{k5.get('gov_mean', 0):.0f} / {k5.get('ungated_mean', 0):.0f}" if k5 else "n/a")
        print(f"| {b} | {rg:.3f} / {ru:.3f} | {dlt} | {cols[0]} | {cols[1]} | {cols[2]} | {tok80} | {tok5} |")
    for b, v in B["backends"].items():
        if isinstance(v, dict) and "consistency_with_k5_run" in v:
            print(f"- {b}: consistency with the k=5 runs {v['consistency_with_k5_run']}; "
                  f"nesting {{{', '.join(f'{c}: ' + str(sum(x['mismatches'].values())) for c, x in (v.get('nesting_check') or {}).items() if x)}}}; "
                  f"lists shorter than 50: {v.get('n_returned_lt_50')}")
m = d.get("toolbench_monolithic")
if m:
    print(f"\nMonolithic ToolBench prompt: {m['n_tools']} tools, cl100k system tokens {m['cl100k_system_tokens']:,}, "
          f"Mistral-Nemo chat tokens (first 50 queries) mean {m.get('mistral_nemo_chat_tokens_first50_mean', 0):,.0f}.")
print("\nk=5 Mistral-Nemo chat tokens per condition:", json.dumps(d.get("toolbench_k5_mistral_nemo_chat_tokens")))
print("additivity:", d.get("e2e_additivity_check"))
