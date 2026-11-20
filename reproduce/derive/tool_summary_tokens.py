#!/usr/bin/env python3
"""Section 3.3: the textual tool summary "adds roughly 13 to 17 tokens (cl100k) per admitted tool".

    python reproduce/derive/tool_summary_tokens.py --out DIR/tool_summary_tokens.json

Composes the 50 tool definitions of the tool-scaling corpus
(evals/eval_tool_scaling.py, TOOL_DEFS) with BEAR's Composer twice, with
emit_tool_summary off and on, and counts the guidance tokens with tiktoken's
cl100k_base, the counter of the paper's token tables. Reports the extra tokens
per admitted tool, for all 50 tools and for each scenario-sized subset of the
first n tools. Instructions are built as build_corpus() builds them. No model,
no retrieval, no server.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from _common import EVALS, provenance, use_evals, write


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    use_evals()
    import tiktoken
    from bear.composer import Composer
    from bear.models import Instruction, InstructionType, ScopeCondition, ScoredInstruction
    from eval_tool_scaling import TOOL_DEFS

    enc = tiktoken.get_encoding("cl100k_base")
    insts = [Instruction(id=td["id"], type=InstructionType.TOOL, priority=td.get("priority", 65),
                         content=td["content"],
                         scope=ScopeCondition(**td["scope"]) if td.get("scope") else ScopeCondition(),
                         tags=td.get("tags", []), actions=td["actions"]) for td in TOOL_DEFS]
    scored = [ScoredInstruction(instruction=i, similarity=1.0, scope_match=True, final_score=1.0) for i in insts]

    def extra(items):
        off = Composer(emit_tool_summary=False).compose(items)
        on = Composer(emit_tool_summary=True).compose(items)
        n_tools = len(on.tools)
        d = len(enc.encode(on.guidance)) - len(enc.encode(off.guidance))
        return {"tools": n_tools, "extra_tokens": d, "per_tool": d / n_tools if n_tools else None,
                "same_tools_array": on.tools == off.tools}

    sizes = sorted({3, 4, 5, 6, 7, 10, 25, len(scored)})
    write(a.out, {
        "tokenizer": "cl100k_base",
        "all_tools": extra(scored),
        "first_n_tools": {str(n): extra(scored[:n]) for n in sizes if n <= len(scored)},
        "_provenance": provenance("reproduce/derive/tool_summary_tokens.py", [EVALS / "eval_tool_scaling.py"]),
    })


if __name__ == "__main__":
    main()
