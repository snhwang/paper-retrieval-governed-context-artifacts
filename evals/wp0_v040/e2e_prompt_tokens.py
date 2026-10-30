"""Did any published end-to-end prompt exceed the context window it ran with?

Ollama cuts a prompt longer than num_ctx without an error. The July runs did
not record prompt_eval_count, so this counts the tokens of the prompts
instead, with Mistral-Nemo's own tekken tokenizer (tiktoken over the cached
tekken.json, as in wp4_token_efficiency.py), in the chat format the Ollama
template renders: [BOS][INST] system, blank line, user [/INST].

Prompts counted:
  retrieval  each top-5 list file given (0.1.10 regenerated and 0.4.2, every
             backend available), built exactly as call_llm_with_tools builds
             them; plus a bound over any 5 tools of the corpus (the 5 longest
             tool lines and the longest query), which covers every list,
             including the published tie orders that cannot be rebuilt
  monolithic all 3,225 tool lines, single-turn (Table 7) and ReAct (Tables 8
             and 9, both system prompts), with each query; the maximum is kept

Windows the July runs used, from their logs: the monolithic single-turn and
ReAct runs print "server window 131,072" (Mistral-Nemo) and "262,144"
(Gemma 4). The Table 7 retrieval rows (Jul 9) printed no window; the smallest
default Ollama has ever used is 2,048, so the retrieval prompts are compared
with 2,048 as well. With --gemma-tokenizer, the monolithic ReAct prompts are
also counted with Gemma 4's tokenizer and chat template (tokenizer only).

    python e2e_prompt_tokens.py --lists DIR [DIR ...] --out tokens.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import eval_toolbench_e2e as e2e  # noqa: E402
import eval_toolbench_react as react  # noqa: E402
from wp4_token_efficiency import mistral_count, mistral_tokenizer  # noqa: E402

PREAMBLE = ("You are a tool-selection assistant. Given the user's query and the "
            "list of available tools, choose the single most appropriate tool. "
            "Respond with a JSON object {\"tool\": \"<exact tool name>\"} and nothing else."
            "\n\nAvailable tools:\n")
WINDOWS = [2048, 4096, 8192, 32768, 131072, 262144]


def line(schema: dict) -> str:
    return f"- {schema['name']}: {(schema.get('description') or '').strip()[:400]}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lists", nargs="*", default=[], help="folders with e2e list files (*.json)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gemma-tokenizer", default="",
                    help="HF id of a cached Gemma 4 tokenizer, e.g. google/gemma-4-12B-it (tokenizer only)")
    a = ap.parse_args()
    tok = mistral_tokenizer()
    corpus, queries = e2e.load_toolbench_data()
    lines, order = {}, []
    for inst in corpus:
        s = e2e.make_tool_schema(inst)
        if s and s.get("name"):
            lines[inst.id] = line(s)
            order.append(lines[inst.id])
    qtexts = [q[0] for q in queries]
    out = {"tokenizer": "Mistral-Nemo-Instruct-2407 tekken.json via tiktoken, + 3 control tokens",
           "windows_checked": WINDOWS, "retrieval": {}, "notes": []}

    def summary(counts):
        c = np.asarray(counts)
        return {"n": int(c.size), "max": int(c.max()), "p99": float(np.percentile(c, 99)),
                "median": float(np.median(c)), "argmax_query": int(c.argmax()),
                "over_window": {w: int(np.sum(c > w)) for w in WINDOWS}}

    for d in a.lists:
        for f in sorted(Path(d).glob("*.json")):
            if f.name.endswith(".provenance.json"):
                continue
            L = json.loads(f.read_text())
            if "ids" not in L:
                continue
            counts = [mistral_count(tok, PREAMBLE + "\n".join(lines[i] for i in ids if i in lines), qtexts[k])
                      for k, ids in enumerate(L["ids"])]
            out["retrieval"][str(f)] = {"condition": L.get("condition"), **summary(counts)}
            print(f"{str(f)[-70:]:70s} max {max(counts):5d}  median {np.median(counts):6.0f}", flush=True)

    # Bound over any 5 tools: the 5 longest lines, the longest query.
    per_line = sorted((len(tok.encode(x, disallowed_special=())) + 1 for x in order), reverse=True)
    qmax = max(len(tok.encode(q, disallowed_special=())) for q in qtexts)
    bound = 3 + len(tok.encode(PREAMBLE, disallowed_special=())) + sum(per_line[:5]) + 2 + qmax + 10
    out["retrieval_bound_any_5_tools"] = {
        "tokens": int(bound), "longest_tool_lines": per_line[:5], "longest_query": int(qmax),
        "note": "preamble + the 5 longest tool lines (+1 newline each) + blank line + longest query, "
                "+3 control tokens, +10 for merges across joins"}
    print("bound over any 5 tools:", bound, flush=True)

    # Monolithic: single-turn (Table 7) and ReAct (Tables 8, 9).
    body = "\n".join(order)
    sys_tokens = {
        "single-turn (Table 7)": PREAMBLE + body,
        "ReAct scaffold (Tables 8, 9)": react.REACT_SYSTEM_PROMPT + "\nAvailable tools:\n" + body,
        "ReAct reasoning prompt (Table 9)": react.REACT_REASONING_SYSTEM_PROMPT + "\nAvailable tools:\n" + body,
    }
    out["monolithic"] = {}
    for name, system in sys_tokens.items():
        base = mistral_count(tok, system, "")
        qmono = [base + len(tok.encode(q, disallowed_special=())) for q in qtexts]
        out["monolithic"][name] = {"n_tools": len(order), "system_tokens": int(base), "max": int(max(qmono)),
                                   "median": float(np.median(qmono)),
                                   "over_window": {w: int(np.sum(np.asarray(qmono) > w)) for w in WINDOWS}}
        print(f"monolithic {name}: max {max(qmono)}", flush=True)
    out["notes"].append("ReAct tool names come from _derive_function_name and may differ slightly from the "
                        "e2e names; the difference is a few tokens per tool at most.")

    # Gemma 4 (Table 9), with its own tokenizer and chat template, for the
    # monolithic ReAct prompts: exact for the 5 longest queries.
    if a.gemma_tokenizer:
        # tokenizers + the snapshot's own chat_template.jinja: the installed
        # transformers cannot load the Gemma 4 tokenizer config.
        import glob
        import os
        import jinja2
        from tokenizers import Tokenizer
        snap = sorted(glob.glob(os.path.expanduser(
            f"~/.cache/huggingface/hub/models--{a.gemma_tokenizer.replace('/', '--')}/snapshots/*/")))[-1]
        gt = Tokenizer.from_file(snap + "tokenizer.json")
        env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True)
        env.globals["raise_exception"] = lambda m: (_ for _ in ()).throw(ValueError(m))
        env.globals["strftime_now"] = lambda f: "2026-07-19"
        tmpl = env.from_string(Path(snap + "chat_template.jinja").read_text())
        cfg = json.loads(Path(snap + "tokenizer_config.json").read_text())

        def gcount(system, user):
            text = tmpl.render(messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                               add_generation_prompt=True, bos_token=cfg.get("bos_token", "<bos>"),
                               eos_token=cfg.get("eos_token", "<eos>"))
            return len(gt.encode(text, add_special_tokens=False).ids)
        longest = sorted(range(len(qtexts)), key=lambda i: -len(qtexts[i]))[:5]
        out["gemma_monolithic"] = {"tokenizer": a.gemma_tokenizer, "snapshot": snap}
        for name in ("ReAct scaffold (Tables 8, 9)", "ReAct reasoning prompt (Table 9)"):
            counts = [gcount(sys_tokens[name], qtexts[i]) for i in longest]
            out["gemma_monolithic"][name] = {"max_over_5_longest_queries": int(max(counts))}
            print(f"gemma monolithic {name}: {max(counts)}", flush=True)
    Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
