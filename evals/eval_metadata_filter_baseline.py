#!/usr/bin/env python3
"""Metadata filter plus rules, on a released stack, against BEAR (WP5).

AE-3, R1-W3 and R2-3 ask for a state-of-the-art baseline. The closest
practice to BEAR's gate is a vector store with a query-side metadata filter
and a fixed rule for always-on items. This script builds that baseline on
LlamaIndex (llama-index-core VectorStoreIndex retriever with
``MetadataFilters``) and compares it with BEAR governed on the same encoder.

ToolBench (1,100 queries, k = 5). Each API node carries its RapidAPI
category as metadata. The filter is an equality on that field, OR-ed over
the query's categories (a query can span several). There are no always-on
items, so no rule applies. With one category per API this filter and BEAR's
gate admit exactly the same set, so a tie is the expected outcome.

Pet Sim (60 standard queries, k = 10). Each instruction node carries its
declared tags (tags, scope tags and required tags together) and, separately,
its required tags. Two filters:

  overlap   admits a node that shares at least one declared tag with the
            query context (FilterOperator.ANY). This is the natural
            practitioner filter and what the revision plan names.
  contain   admits a node whose required tags are all in the query context,
            written as NOT (required ANY of the tags the context lacks). It
            is BEAR's conjunctive gate expressed in LlamaIndex filters, the
            strongest filter this stack can state.

The fixed rule puts the three safety instructions first and fills the
remaining k - 3 slots from the filtered ranking. The manuscript describes
Pet Sim's ground truth as tag overlap. It was built by hand and tracks the
subset condition closely, so the containment filter is the one that could
beat BEAR. Either outcome is reported.

Arms:
    bear_gov         BEAR governed, as published (tags in Context.tags)
    bear_nogov       BEAR without governance, as published
    li_plain         LlamaIndex, no filter
    li_filter        LlamaIndex, metadata filter (ToolBench category; Pet Sim overlap)
    li_filter_rule   LlamaIndex, overlap filter + safety rule (Pet Sim)
    li_contain       LlamaIndex, containment filter (Pet Sim)
    li_contain_rule  LlamaIndex, containment filter + safety rule (Pet Sim)
    li_plain_rule    LlamaIndex, no filter + safety rule (Pet Sim)

LlamaIndex runs with its defaults apart from the encoder, so node metadata
is part of the embedded text ("category: data" before the content), which
is what a practitioner gets. Encoders: BAAI/bge-base-en-v1.5 (both stacks,
BGE query instruction, on the CPU) and Nemotron embed 1B v2 through the
model-server on port 8360 (a LlamaIndex BaseEmbedding over BEAR's
RemoteEmbedder, and RemoteEmbedder for BEAR).

Also reported, per arm: how many returned items fail BEAR's conjunctive gate
for the query (an item whose required tags are not all in the context). A
filter that admits on any overlap has no notion of a conjunctive gate.

Metrics: ToolBench Recall@5 and NDCG@5; Pet Sim strict and relaxed F1@10.
Paired bootstrap 95% CIs, paired Cohen's d, Wilcoxon and paired t, with
per-query arrays saved.

The Nemotron arms call port 8360, so run under the GPU lock:
    flock ~/tist-gpu.lock env CUDA_VISIBLE_DEVICES= \
        python evals/eval_metadata_filter_baseline.py --corpus toolbench
    flock ~/tist-gpu.lock env CUDA_VISIBLE_DEVICES= \
        python evals/eval_metadata_filter_baseline.py --corpus petsim
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tistr2_common import (  # noqa: E402
    NEMOTRON_URL, REPO_ROOT, Tee, bear_provenance, ci_summary, fmt, fmt_delta,
    json_default, ndcg, paired_summary, prf, refuse_overwrite, require_bear_040,
)
import bear  # noqa: E402
from bear import Config, Context, Corpus, EmbeddingBackend, Retriever  # noqa: E402
from bear.remote_embedder import RemoteEmbedder  # noqa: E402
from bear.retriever import Embedder  # noqa: E402
from bear.scope import passes_gate  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

BGE = "BAAI/bge-base-en-v1.5"
BGE_PREFIX = "Represent this sentence for retrieving relevant documents: "
SETTINGS = {
    "toolbench": {"k": 5, "pw": 0.3, "theta": 0.15, "mandatory": []},
    "petsim": {"k": 10, "pw": 0.3, "theta": 0.3, "mandatory": ["safety"]},
}


# ---------------------------------------------------------------------------
# Encoders
# ---------------------------------------------------------------------------

def li_embed_model(encoder: str):
    if encoder == "bge":
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        return HuggingFaceEmbedding(model_name=BGE, query_instruction=BGE_PREFIX,
                                    text_instruction="", device="cpu")
    from llama_index.core.base.embeddings.base import BaseEmbedding
    from pydantic import PrivateAttr

    class NemotronEmbedding(BaseEmbedding):
        """LlamaIndex embedding over the model-server Nemotron service."""

        _remote: Any = PrivateAttr()

        def __init__(self, **kw):
            super().__init__(model_name="nemotron-embed-vl-1b-v2", embed_batch_size=64, **kw)
            self._remote = RemoteEmbedder(NEMOTRON_URL, batch_size=64)

        def _get_query_embedding(self, query: str):
            return self._remote.embed([query], is_query=True)[0].tolist()

        async def _aget_query_embedding(self, query: str):
            return self._get_query_embedding(query)

        def _get_text_embedding(self, text: str):
            return self._remote.embed([text], is_query=False)[0].tolist()

        def _get_text_embeddings(self, texts):
            return self._remote.embed(list(texts), is_query=False).tolist()

    return NemotronEmbedding()


def bear_config(corpus_name: str, encoder: str, governed: bool) -> Config:
    s = SETTINGS[corpus_name]
    model = BGE if encoder == "bge" else f"remote:{NEMOTRON_URL}"
    return Config(embedding_model=model, embedding_backend=EmbeddingBackend.NUMPY,
                  embedding_dim=768 if encoder == "bge" else 2048,
                  embedding_query_prefix=BGE_PREFIX if encoder == "bge" else "",
                  embedding_passage_prefix="", embedding_device="cpu",
                  priority_weight=s["pw"] if governed else 0.0,
                  default_threshold=s["theta"], default_top_k=s["k"],
                  mandatory_tags=s["mandatory"] if governed else [])


def bear_embedder(cfg: Config, encoder: str):
    return Embedder.from_config(cfg) if encoder == "bge" else RemoteEmbedder(NEMOTRON_URL, batch_size=64)


# ---------------------------------------------------------------------------
# Corpora
# ---------------------------------------------------------------------------

def load(corpus_name: str):
    if corpus_name == "toolbench":
        from eval_toolbench import load_toolbench_corpus_and_queries
        corpus, queries, _ = load_toolbench_corpus_and_queries()
        qs = [(q[0], list(q[1]), set(q[2]), None, q[3]) for q in queries]
        return corpus, qs
    from eval_governance_decomposed import load_pet_sim_corpus
    from eval_retrieval import RELAXED_EXTRAS, TEST_QUERIES
    corpus = load_pet_sim_corpus()
    qs = [(q, list(t), set(e), set(e) | RELAXED_EXTRAS.get(q, set()), "standard")
          for q, t, e in TEST_QUERIES]
    return corpus, qs


def li_nodes(corpus: Corpus, corpus_name: str):
    from llama_index.core.schema import TextNode
    nodes = []
    for inst in corpus:
        if corpus_name == "toolbench":
            md = {"category": inst.scope.required_tags[0]}
        else:
            md = {"tags": sorted(set(inst.tags) | set(inst.scope.tags)
                                 | set(inst.scope.required_tags)),
                  "required": sorted(inst.scope.required_tags)}
        # "required" exists only for the containment filter. It is kept out
        # of the embedded and LLM text, so every arm embeds the same node text
        # (LlamaIndex's default: the "tags" or "category" line, then content).
        nodes.append(TextNode(text=inst.content, id_=inst.id, metadata=md,
                              excluded_embed_metadata_keys=["required"],
                              excluded_llm_metadata_keys=["required"]))
    return nodes


def li_filters(corpus_name: str, tags: list[str], mode: str = "overlap",
               required_vocab: list[str] | None = None):
    from llama_index.core.vector_stores import (FilterCondition, FilterOperator,
                                                MetadataFilter, MetadataFilters)
    if mode == "contain":
        lacking = [t for t in (required_vocab or []) if t not in tags]
        if not lacking:
            return None
        return MetadataFilters(filters=[MetadataFilter(key="required", value=lacking,
                                                       operator=FilterOperator.ANY)],
                               condition=FilterCondition.NOT)
    if corpus_name == "toolbench":
        return MetadataFilters(filters=[MetadataFilter(key="category", value=t,
                                                       operator=FilterOperator.EQ) for t in tags],
                               condition=FilterCondition.OR)
    return MetadataFilters(filters=[MetadataFilter(key="tags", value=list(tags),
                                                   operator=FilterOperator.ANY)])


def strip_for_nogov(corpus: Corpus, corpus_name: str) -> Corpus:
    if corpus_name == "toolbench":
        from eval_toolbench import strip_governance
        return strip_governance(corpus)
    from eval_reranker_composition import strip_all_governance
    return strip_all_governance(corpus, drop_conflicts=False)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_encoder(corpus_name: str, encoder: str, corpus: Corpus, queries) -> dict:
    from llama_index.core import VectorStoreIndex
    from llama_index.core.schema import QueryBundle
    s = SETTINGS[corpus_name]
    k = s["k"]
    inst_by_id = {i.id: i for i in corpus}
    safety = sorted((i for i in corpus if "safety" in i.tags),
                    key=lambda i: (-i.priority, i.id)) if corpus_name == "petsim" else []
    safety_ids = [i.id for i in safety]

    t0 = time.time()
    em = li_embed_model(encoder)
    index = VectorStoreIndex(nodes=li_nodes(corpus, corpus_name), embed_model=em)
    t_li = time.time() - t0
    cfg_g = bear_config(corpus_name, encoder, True)
    cfg_n = bear_config(corpus_name, encoder, False)
    shared = bear_embedder(cfg_g, encoder)
    r_gov = Retriever(corpus, config=cfg_g, embedder=shared)
    r_gov.build_index()
    r_nogov = Retriever(strip_for_nogov(corpus, corpus_name), config=cfg_n, embedder=shared)
    r_nogov.build_index()
    print(f"  [{encoder}] indexes built (LlamaIndex {t_li:.0f}s, total {time.time() - t0:.0f}s)",
          flush=True)

    arms = ["bear_gov", "bear_nogov", "li_plain", "li_filter"]
    if corpus_name == "petsim":
        arms += ["li_filter_rule", "li_contain", "li_contain_rule", "li_plain_rule"]
    required_vocab = sorted({t for i in corpus for t in i.scope.required_tags})
    lists: dict[str, list[list[str]]] = {a: [] for a in arms}
    plain_ret = index.as_retriever(similarity_top_k=k + len(safety_ids))
    for qi, (q, tags, _e, _r, _s) in enumerate(queries):
        lists["bear_gov"].append([x.id for x in r_gov.retrieve(q, Context(tags=tags), top_k=k)])
        nogov_ctx = Context(tags=tags) if corpus_name == "petsim" else Context()
        lists["bear_nogov"].append([x.id for x in r_nogov.retrieve(q, nogov_ctx, top_k=k)])
        qvec = em.get_query_embedding(q)
        bundle = QueryBundle(query_str=q, embedding=qvec)
        plain = [n.node.node_id for n in plain_ret.retrieve(bundle)]
        filt_ret = index.as_retriever(similarity_top_k=k, filters=li_filters(corpus_name, tags))
        filt = [n.node.node_id for n in filt_ret.retrieve(bundle)]
        lists["li_plain"].append(plain[:k])
        lists["li_filter"].append(filt[:k])
        if corpus_name == "petsim":
            room = k - len(safety_ids)
            cf = li_filters(corpus_name, tags, "contain", required_vocab)
            cont_ret = index.as_retriever(similarity_top_k=k + len(safety_ids), filters=cf)
            cont = [n.node.node_id for n in cont_ret.retrieve(bundle)]
            lists["li_contain"].append(cont[:k])
            lists["li_contain_rule"].append(safety_ids + [x for x in cont if x not in safety_ids][:room])
            lists["li_filter_rule"].append(safety_ids + [x for x in filt if x not in safety_ids][:room])
            lists["li_plain_rule"].append(safety_ids + [x for x in plain if x not in safety_ids][:room])
        if qi and qi % 200 == 0:
            print(f"    {qi}/{len(queries)} queries", flush=True)

    per: dict[str, dict[str, np.ndarray]] = {}
    for a in arms:
        m: dict[str, list] = {"recall": [], "precision": [], "f1": [], "ndcg": [],
                              "gate_violations": [], "n_out": []}
        if corpus_name == "petsim":
            m.update(recall_relaxed=[], f1_relaxed=[])
        for (q, tags, exp, rel, _s), ids in zip(queries, lists[a]):
            got = set(ids)
            p_, r_, f_ = prf(got, exp)
            m["recall"].append(r_)
            m["precision"].append(p_)
            m["f1"].append(f_)
            m["ndcg"].append(ndcg(ids, exp, k))
            m["n_out"].append(len(ids))
            ctx = Context(tags=tags)
            m["gate_violations"].append(sum(1 for x in ids if not passes_gate(inst_by_id[x], ctx)))
            if rel is not None:
                _, rr, fr = prf(got, rel)
                m["recall_relaxed"].append(rr)
                m["f1_relaxed"].append(fr)
        per[a] = {key: np.asarray(v, dtype=float) for key, v in m.items()}

    metrics = (["recall", "ndcg"] if corpus_name == "toolbench"
               else ["f1", "f1_relaxed", "recall", "recall_relaxed"])
    contrasts = ([("li_filter", "bear_gov"), ("li_filter", "li_plain"),
                  ("bear_gov", "bear_nogov"), ("li_plain", "bear_nogov")]
                 if corpus_name == "toolbench" else
                 [("li_filter_rule", "bear_gov"), ("li_contain_rule", "bear_gov"),
                  ("li_filter", "bear_gov"), ("li_contain", "bear_gov"),
                  ("li_filter_rule", "li_filter"), ("li_contain_rule", "li_contain"),
                  ("li_filter_rule", "li_plain_rule"), ("li_contain_rule", "li_filter_rule"),
                  ("bear_gov", "bear_nogov"), ("li_plain", "bear_nogov")])
    out = {"arms": {}, "contrasts": {}, "per_query": {}, "lists": lists}
    for a in arms:
        out["arms"][a] = {mm: ci_summary(per[a][mm]) for mm in per[a]}
        out["arms"][a]["items_failing_gate"] = int(per[a]["gate_violations"].sum())
        out["arms"][a]["items_returned"] = int(per[a]["n_out"].sum())
        out["per_query"][a] = per[a]
    for a, b in contrasts:
        for mm in metrics:
            out["contrasts"][f"{a}_vs_{b}__{mm}"] = paired_summary(per[a][mm], per[b][mm])
    if corpus_name == "toolbench":
        splits = sorted({q[4] for q in queries})
        out["by_split"] = {sp: {a: float(np.mean([v for v, q in zip(per[a]["recall"], queries)
                                                  if q[4] == sp])) for a in arms} for sp in splits}
        out["identical_top5_li_filter_vs_bear_gov"] = int(sum(
            set(x) == set(y) for x, y in zip(lists["li_filter"], lists["bear_gov"])))
    out["embedding"] = {
        "encoder": encoder,
        "llama_index_embed_batch_size": getattr(em, "embed_batch_size", None),
        "bear_embedder_batching": ("bear.retriever.Embedder.embed: one batch for 64 or fewer "
                                   "texts, else batches of 32 (identical in BEAR 0.4.0 and 0.4.2)"
                                   if encoder == "bge" else "RemoteEmbedder, batch_size 64"),
        "device": "cpu" if encoder == "bge" else "service"}
    out["elapsed_s"] = round(time.time() - t0, 1)
    return out


def print_encoder(corpus_name: str, encoder: str, res: dict) -> None:
    metrics = (["recall", "ndcg"] if corpus_name == "toolbench"
               else ["f1", "f1_relaxed"])
    print(f"\n  {encoder}: arms (95% bootstrap CI)")
    for a, e in res["arms"].items():
        cells = "   ".join(f"{m} {fmt(e[m])}" for m in metrics)
        print(f"    {a:<15} {cells}   gate-failing items {e['items_failing_gate']}/{e['items_returned']}")
    print(f"  {encoder}: paired contrasts (delta [95% CI] p d)")
    for key, c in res["contrasts"].items():
        print(f"    {key:<40} {fmt_delta(c)}")
    if "identical_top5_li_filter_vs_bear_gov" in res:
        print(f"    li_filter and bear_gov return the same top-5 set on "
              f"{res['identical_top5_li_filter_vs_bear_gov']} queries")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=["toolbench", "petsim"], required=True)
    ap.add_argument("--encoders", nargs="+", default=["bge", "nemotron"], choices=["bge", "nemotron"])
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--log-file", type=Path, default=None)
    args = ap.parse_args()
    require_bear_040()
    out_path = args.output or REPO_ROOT / "results" / f"metadata_filter_baseline_{args.corpus}.json"
    log_path = args.log_file or REPO_ROOT / "results" / f"metadata_filter_baseline_{args.corpus}_output.txt"
    refuse_overwrite(out_path, log_path)
    log = log_path.open("w", encoding="utf-8")
    orig = sys.stdout
    sys.stdout = Tee(orig, log)
    try:
        import llama_index.core as lic
        t0 = time.time()
        corpus, queries = load(args.corpus)
        s = SETTINGS[args.corpus]
        print(f"=== Metadata filter + rules (LlamaIndex {lic.__version__}) vs BEAR {bear.__version__}: "
              f"{args.corpus} ===")
        print(f"{len(corpus)} items, {len(queries)} queries, k={s['k']}, BEAR priority weight "
              f"{s['pw']}, theta {s['theta']}, mandatory {s['mandatory']}")
        results = {}
        for enc in args.encoders:
            results[enc] = run_encoder(args.corpus, enc, corpus, queries)
            print_encoder(args.corpus, enc, results[enc])
        out = {"corpus": args.corpus, "settings": s, "llama_index_core": lic.__version__,
               "n_items": len(corpus), "n_queries": len(queries),
               "queries": [{"query": q[0], "tags": q[1]} for q in queries],
               "provenance": bear_provenance(), "encoders": results}
        out_path.write_text(json.dumps(out, default=json_default), encoding="utf-8")
        print(f"\nWrote {out_path}\nElapsed {time.time() - t0:.0f}s")
        print_repro_footer(extra={"eval": "metadata_filter_baseline", "corpus": args.corpus,
                                  "encoders": args.encoders, **bear_provenance()})
    finally:
        sys.stdout = orig
        log.close()


if __name__ == "__main__":
    main()
