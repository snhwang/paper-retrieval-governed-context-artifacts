#!/usr/bin/env python3
"""Minimal reproduction: BM25 never admits an admissible instruction with no term in common.

Claims at stake (formal section, BEAR 0.4.x):
  * Admission rule. An instruction is admitted when its gate passes and its
    soft scope matches or its similarity reaches the threshold:
        gate(d) and (soft(d) or sim(q, d) >= theta)
    An empty soft scope matches every context.
  * Gated ranking. "For a gated query, every gate-passing instruction is
    ranked" (a gated query searches the whole corpus, and the required-tags
    backfill catches any gated instruction the search left out).

The corpus has three instructions and the context one tag, so the query is
gated:

  billing-refund   required_tags [billing]; shares terms with the query
  greeting         no required tags, empty soft scope; no term in common
  billing-tone     required_tags [billing]; no term in common

Expected under the admission rule: all three admitted (each passes its gate,
and each soft scope matches: greeting's is empty, the billing ones are empty
apart from the gate).

Actual under BM25: billing-refund is admitted by search and billing-tone by
the backfill (similarity 0, score alpha * p / 100 in 0.4.1). greeting is
never ranked or admitted, and appears nowhere in the trace. BM25 returns no
row that shares no term with the query, and the backfill covers only
instructions with required tags. The same corpus on a dense backend (BEAR's
hash embedder) admits all three.

So under BM25 both claims fail for gate-passing instructions without
required tags that share no term with the query. The failure predates 0.4.1.

Usage:
    python evals/repro_bm25_admission_gap.py
"""

from __future__ import annotations

import logging

import bear
from bear import Config, Context, Corpus, EmbeddingBackend, Retriever
from bear.models import Instruction, InstructionType, ScopeCondition

logging.getLogger("bear").setLevel(logging.ERROR)

QUERY = "refund an invoice"
CONTEXT = Context(tags=["billing"])


def corpus() -> Corpus:
    c = Corpus()
    c.add(Instruction(id="billing-refund", type=InstructionType.DIRECTIVE, priority=50,
                      content="Refund requests need the invoice number.",
                      scope=ScopeCondition(required_tags=["billing"])))
    c.add(Instruction(id="greeting", type=InstructionType.DIRECTIVE, priority=50,
                      content="Open every conversation politely.",
                      scope=ScopeCondition()))
    c.add(Instruction(id="billing-tone", type=InstructionType.DIRECTIVE, priority=50,
                      content="Stay calm and courteous.",
                      scope=ScopeCondition(required_tags=["billing"])))
    return c


def run(backend: str) -> dict:
    common = dict(default_top_k=5, default_threshold=0.3, priority_weight=0.3,
                  mandatory_tags=[], embedding_query_prefix="", embedding_passage_prefix="")
    if backend == "bm25":
        cfg = Config(embedding_model="bm25", embedding_backend=EmbeddingBackend.BM25,
                     embedding_dim=0, **common)
    else:
        cfg = Config(embedding_model="hash", embedding_dim=768, **common)
    r = Retriever(corpus(), config=cfg)
    r.build_index()
    out, tr = r.retrieve_with_trace(QUERY, CONTEXT, top_k=Retriever.ALL)
    return {"output": [(s.id, round(float(s.similarity), 4), round(float(s.final_score), 4))
                       for s in out],
            "admitted": dict(tr.admitted), "excluded": dict(tr.excluded),
            "pool": tr.pool, "gated": tr.gated}


def main() -> None:
    print(f"BEAR {bear.__version__}. Query {QUERY!r}, context tags {CONTEXT.tags}, "
          f"threshold 0.3, top_k=ALL.")
    print("Expected (admission rule): billing-refund, greeting and billing-tone all admitted.\n")
    for b in ("bm25", "hash"):
        res = run(b)
        missing = sorted({"billing-refund", "greeting", "billing-tone"} - set(res["admitted"]))
        print(f"{b}: gated={res['gated']} pool={res['pool']}")
        print(f"  output (id, similarity, score): {res['output']}")
        print(f"  admitted: {res['admitted']}")
        print(f"  excluded: {res['excluded']}")
        print(f"  admissible but never admitted: {missing or 'none'}\n")


if __name__ == "__main__":
    main()
