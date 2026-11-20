"""Size of the monolithic prompts of the end-to-end reruns (evals/e2e_rerun/PLAN.md).

Builds each monolithic prompt exactly as the evaluation scripts do, with no model and no server, and
prints its characters and its cl100k tokens. The model's own count comes from the server at run time
(usage.prompt_tokens). This script gives the size to plan the context window with.

Two prompts differ:
  - eval_toolbench_react.py (the ReAct scaffold and the Gemma runs) lists each of the 3,225 tools as its
    name and the first 400 characters of its description.
  - eval_toolbench_e2e.py (Table 10's monolithic row) sends every tool as a full function schema. Its
    size is measured by evals/wp0_v040/e2e_prompt_tokens.py (82,298 cl100k tokens, 88.3k for Mistral-Nemo).

Usage (from the repo root, CPU only):
    python evals/e2e_rerun/count_prompts.py [--out FILE.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import eval_toolbench_react as react  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")

    corpus, queries = react.load_toolbench_data()
    name_map: dict = {}
    react.build_id_to_function(corpus, name_map)
    schemas = react.build_monolithic_schemas(corpus, 0, name_map)
    # The tool list of call_llm_react, character for character.
    tool_list = "\n".join(f"- {s['name']}: {(s.get('description') or '').strip()[:400]}"
                          for s in schemas if s.get("name"))
    qtexts = [q[0] for q in queries]
    longest = max(qtexts, key=len)
    out = {"n_tools": len([s for s in schemas if s.get("name")]), "n_queries": len(queries),
           "tool_list_chars": len(tool_list), "tool_list_cl100k": len(enc.encode(tool_list)),
           "longest_query_chars": len(longest), "longest_query_cl100k": len(enc.encode(longest)),
           "prompts": {}}
    for label, system in (("scaffold (constrained thought and action)", react.REACT_SYSTEM_PROMPT),
                          ("native reasoning", react.REACT_REASONING_SYSTEM_PROMPT)):
        text = system + "\nAvailable tools:\n" + tool_list
        out["prompts"][label] = {"system_chars": len(text), "system_cl100k": len(enc.encode(text)),
                                 "with_longest_query_cl100k": len(enc.encode(text)) + len(enc.encode(longest))}
    # The enum of tool names in the constrained schema is a grammar, not prompt text, on a server that
    # compiles response_format. Its size is given in case a server puts it into the prompt.
    names = json.dumps([s["name"] for s in schemas if s.get("name")])
    out["tool_name_enum_cl100k"] = len(enc.encode(names))
    print(json.dumps(out, indent=1))
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
