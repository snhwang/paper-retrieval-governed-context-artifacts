"""Invariants of BEAR's retrieval precedence order, as a reported experiment (WP1).

Addresses R2-4 (formal guarantees incomplete), R2-6 (no stress tests with
conflicting rules) and R2-7 (measure the mechanisms as guarantees, as violation
rates rather than F1). A seeded generator builds random corpora with hard
gates, soft scopes, mandatory tags, priorities, and conflicts_with /
supersedes / requires edges, including cycles, chains, self-requirements and
ids that name nothing. Random contexts and queries are drawn per corpus, and
every query is retrieved at every k from 1 to 30. Each output is checked
against the precedence order that the revised Section 3.1.1 states:

    I1   Gate soundness. No item with required_tags appears unless its gate
         passes (required_tags within context tags plus gate_tags).
    I2   Mandatory completeness. Every gate-admissible mandatory item is in
         the output, unless an admissible mandatory item supersedes it or
         beats it in a declared conflict.
    I2b  Budget bound. Output items that are neither mandatory nor required
         by another output item number at most max(0, k - #mandatory).
    I3   Conflict freeness. No declared conflict pair appears together.
    I3b  Supersede consistency. No item appears with an item it supersedes,
         except an optional item beside a mandatory one it cannot displace.
    I4   Dependency closure. A non-mandatory output item has all its
         prerequisites in the output. A mandatory one records exactly its
         missing prerequisites in the retrieval trace.
    I5   No orphan prerequisites. Every item admitted only as a prerequisite
         is reachable through requires edges from an output item admitted on
         its own (search, gate backfill or mandatory injection). Split by
         where the orphan arises: I5a, made by the top-k cut; I5b, already
         present after relationship resolution.
    I6   Determinism. The same call twice, the public call against the traced
         one, and a freshly built retriever all give identical output (ids,
         order, scores). A cross-process check under another PYTHONHASHSEED
         compares output digests.
    I7   Budget stability. For k1 < k2 <= the pool base, the k1 output is
         contained in the k2 output, in the same order.
    I8   No mandatory item is displaced by an optional one (trace: every
         admissible mandatory item that is absent was removed by a mandatory
         item, through superseded or conflict).
    I9   Threshold condition. Every item the threshold removes passes its
         gate, fails its soft scope, and has similarity below the threshold.

    I10  Resolution order-independence. The resolved set (top_k=ALL, so no
         cut, and the threshold off, so the admitted set is fixed) is
         unchanged when the similarity order of the candidates changes. With
         the stub the order is reversed exactly, by reassigning similarity
         markers, and also shuffled. With the hash embedder it is shuffled.
    I11  Pool admissibility. The ranked pool is the min(pool,
         #gate-passing) most similar gate-passing instructions, so no
         gate-failing instruction takes a place in it. Checked against the
         similarities: (a) every gate-passing instruction strictly above the
         boundary similarity was a candidate (it appears in the trace other
         than as a gate exclusion), and (b) none strictly below it was a
         search candidate (admitted by search, or set aside by the
         threshold). Non-vacuous for ungated queries on a corpus that gates
         anything. Similarities come from the stub's markers, or for the
         hash embedder from a public retrieve over the same texts.
    I12  No acting after removal. For every conflict or superseded exclusion
         at position n of RetrievalTrace.excluded (insertion order), its "by"
         is not among the first n excluded ids. The remover may still leave
         later (a supersede, the cut, closure, unrequired), since resolution
         is one pass, so it is not required to be in the output.
    I13  Ranked score rule (BEAR 0.4.1). Every output instruction that
         competes for a ranked slot, meaning one that is not mandatory and
         entered by search or by the required-tags backfill, has final score
         (1 - alpha) * sim + alpha * priority / 100. sim is the search
         similarity, or 0 for a row the search did not return, and such a
         backfilled row must record similarity 0. Rows exempt from the cut
         keep their own documented score: a mandatory instruction added by
         injection, and a prerequisite added by requires, both at
         priority / 100, which only orders the result.
    I14  Backfill admission (BEAR 0.4.1). Every instruction the required-tags
         backfill admits passes its gate and either matches its soft scope or
         meets a threshold of at most 0 (similarity 0 >= theta). This is the
         rule every searched row meets, at similarity 0.
    I15  Admission completeness. Every candidate that the admission rule
         admits (gate passes, and soft scope matches or similarity reaches
         the threshold) is admitted: it appears in RetrievalTrace.admitted,
         whatever resolution or the cut does to it afterwards. For a gated
         query every instruction is a candidate, since BEAR ranks the whole
         corpus. For an ungated query the candidates are the gate-passing
         instructions strictly above the pool's boundary similarity, as in
         I11. Instructions within SIM_TOL of the threshold or of the boundary
         are left alone. I1, I9 and I14 check that admission is sound, I2
         that mandatory items are complete, and I15 that the rule is complete.
    I16  Canonical tie order. Among ranked rows (not mandatory, admitted by
         search or by the backfill) with equal final score and equal
         priority, the output lists them by id, and the top-k cut keeps the
         smallest ids: no ranked row cut by top_k ties a kept ranked row with
         a larger id (kept rows that another output row requires are left
         out of that comparison, since closure, not the ranking, may have
         kept them). Scores of cut rows are recomputed with BEAR's own
         float64 expression from the similarity the trace records, so ties
         are exact. Without a canonical tie-break the order of tied rows is
         whatever the backend's argsort gives, which can differ between numpy
         versions, so this turns a cross-environment difference into a check
         within one environment.

I13 and I14 are only non-vacuous where the search drops rows, since a gated
query on a dense backend ranks the whole corpus and the backfill then adds
nothing. The main_bm25 configuration supplies that: BM25 returns no row that
shares no term with the query. Its texts write each similarity marker as
cluster words ("clu<C>" repeated by strength, and "var<C>x<V>"), so an
instruction in the query's cluster shares terms with it and others share
only header tags. A quarter of the queries (marker v = 0) carry no cluster
word at all.

BEAR writes the context's tags into the query text ("[tags:t1,t3]") and an
instruction's labels and scope tags into its own, so under main_bm25 every
tagged query shares the word "tags" with every instruction that has a soft
scope, and only scope-free instructions are ever dropped. main_bm25_gatectx
passes the same tags as gate_tags instead, so the query carries no header and
an instruction with a soft scope can be dropped and reach the backfill. That
is where I14 and restore_flat_backfill differ, so the flat-backfill column
runs on it. Soft scopes then see no context tags.

From 0.4.2, BM25 returns every row: a row that shares no term with the
query comes back at similarity 0, ordered by priority then id, and meets the
normal pool and admission rules. The backfill then has nothing to add under
BM25, so I13 and I14 are exercised only by the columns that restore the
earlier behavior (restore_dropped_rows, restore_flat_backfill and
restore_below_threshold imply it). A configuration whose switch this BEAR
does not define is skipped with a note, since Config would ignore it
silently and report a column that changed nothing.

Under a backend that drops rows two checks are restricted. I10 compares the
resolved set only across order variants that admit the same instructions by
the same paths, since moving the similarity markers changes which rows share
a term with the query at all, and so whether a row enters on its own merit or
only as a prerequisite. I11 requires only gate-passing rows of similarity above 0 to be
candidates. The rows it leaves out (gate-passing, soft scope matching, no
required tags, no term in common with the query) are admissible under the
admission rule but never reach a result, because the search drops them and
the backfill covers only rows with required tags. They are counted as
"lexical admission gap" in the summary.

Invariants can be reported apart as pending (--pending), for a sha that
predates the rule they state.

Similarities come from a controlled stub embedder that gives clustered,
deterministic similarities (instructions and queries carry a cluster marker;
equal markers give equal vectors, so exact ties occur). A second "main"
configuration uses BEAR's built-in hash embedder instead.

Configurations: BEAR main defaults (stub, hash and BM25); each legacy switch
on (restore_pool_by_k, restore_unchecked_requires, restore_below_threshold,
restore_ranked_resolution, restore_ungated_pool, restore_removed_acting; from
0.4.1 restore_flat_backfill, run under BM25 where the backfill acts; from
0.4.2 restore_dropped_rows under BM25, and restore_tie_order under the stub
and under BM25, where exact ties occur);
and each mechanism Config can disable (mandatory_tags=[], priority_weight=0,
threshold off). The gate and the relationship edges are corpus metadata, so
Config cannot disable them.

Pool growth is reported separately, as a sensitivity of the retriever: k
above the pool base (retrieval_pool=10, k to 30), and the pool varied at
fixed k against a whole-corpus pool.

Violation rates are reported per corpus (the independent unit) with
Clopper-Pearson 95% CIs, alongside output-level counts. For every
configuration and invariant with a violation, the first one found is shrunk
to a minimal counterexample and saved.

Only BEAR's public API is used. The trace comes from
Retriever.retrieve_with_trace (BEAR 0.4.0 and later), and I6 checks that it
returns what Retriever.retrieve returns. Since that version a prerequisite
the cut drops with its dependent is recorded as "unrequired" rather than
"top_k". The I5a/I5b split reads "unrequired" as a resolution removal, so it
is exact for orphans only on shas where the cut can still strand one.

Usage:
    python evals/eval_invariants.py                         # 2,000 corpora, all configs
    python evals/eval_invariants.py --n-corpora 100         # quick run
    python evals/eval_invariants.py --configs main legacy_pool_by_k
    BEAR_SOURCE_SHA=<sha> python evals/eval_invariants.py   # record the BEAR source commit
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from scipy import stats

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bear  # noqa: E402
from bear import Config, Context, Corpus, EmbeddingBackend, Retriever  # noqa: E402
from bear.models import Instruction, InstructionType, ScopeCondition  # noqa: E402
from repro_footer import print_repro_footer  # noqa: E402

logging.getLogger("bear").setLevel(logging.ERROR)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_SEED = 20261029
N_CORPORA = 2000
MIN_N, MAX_N = 20, 60
CASES_PER_CORPUS = 5
K_VALUES = list(range(1, 31))
DEFAULT_TOP_K = 10            # pool base = 3 x default_top_k = 30, so every k <= base
THRESHOLD = 0.3
PRIORITY_WEIGHT = 0.3
MANDATORY_TAGS = ("safety", "compliance")
TAG_VOCAB = [f"t{i}" for i in range(8)]
TYPES = ["persona", "constraint", "protocol", "directive", "tool"]
MAX_CLUSTERS = 6
EMBED_DIM = 24
STUB_SEED = 7

# Pool-growth sensitivity
SENS_POOL_BASE = 10                       # k above this is above the base
SENS_FIXED_K = (5, 10)
SENS_POOLS = (5, 10, 15, 20, 30, 45, 60)
WHOLE_POOL = 10_000

CROSS_PROCESS_CORPORA = 200
CROSS_PROCESS_HASHSEED = "12345"

CONFIGS: dict[str, dict] = {
    "main": {"label": "Main defaults (stub)", "embedder": "stub", "overrides": {}},
    "main_hash": {"label": "Main defaults (hash)", "embedder": "hash", "overrides": {}},
    "main_bm25": {"label": "Main defaults (BM25, drops rows)", "embedder": "bm25",
                  "overrides": {}},
    "main_bm25_gatectx": {"label": "Main defaults (BM25, context tags as gate_tags)",
                          "embedder": "bm25", "context": "gate", "overrides": {}},
    "legacy_pool_by_k": {"label": "restore_pool_by_k", "embedder": "stub",
                         "overrides": {"restore_pool_by_k": True}},
    "legacy_unchecked_requires": {"label": "restore_unchecked_requires", "embedder": "stub",
                                  "overrides": {"restore_unchecked_requires": True}},
    "legacy_below_threshold": {"label": "restore_below_threshold", "embedder": "stub",
                               "overrides": {"restore_below_threshold": True}},
    "legacy_ranked_resolution": {"label": "restore_ranked_resolution", "embedder": "stub",
                                 "overrides": {"restore_ranked_resolution": True}},
    "legacy_ungated_pool": {"label": "restore_ungated_pool", "embedder": "stub",
                            "overrides": {"restore_ungated_pool": True}},
    "legacy_removed_acting": {"label": "restore_removed_acting", "embedder": "stub",
                              "overrides": {"restore_removed_acting": True}},
    "legacy_flat_backfill": {"label": "restore_flat_backfill (BM25, gate_tags context)",
                             "embedder": "bm25", "context": "gate",
                             "overrides": {"restore_flat_backfill": True}},
    "legacy_dropped_rows": {"label": "restore_dropped_rows (BM25)", "embedder": "bm25",
                            "overrides": {"restore_dropped_rows": True}},
    "legacy_tie_order": {"label": "restore_tie_order (stub)", "embedder": "stub",
                         "overrides": {"restore_tie_order": True}},
    "legacy_tie_order_bm25": {"label": "restore_tie_order (BM25)", "embedder": "bm25",
                              "overrides": {"restore_tie_order": True}},
    "no_mandatory": {"label": "mandatory_tags=[]", "embedder": "stub",
                     "overrides": {"mandatory_tags": []}},
    "no_priority": {"label": "priority_weight=0", "embedder": "stub",
                    "overrides": {"priority_weight": 0.0}},
    "no_threshold": {"label": "threshold off", "embedder": "stub",
                     "overrides": {"default_threshold": -1.01}},
}

INVARIANTS = [
    ("I1", "Gate soundness"),
    ("I2", "Mandatory completeness"),
    ("I2b", "Budget bound"),
    ("I3", "Conflict freeness"),
    ("I3b", "Supersede consistency"),
    ("I4", "Dependency closure"),
    ("I5", "No orphan prerequisites"),
    ("I5a", "  I5 orphan made by the top-k cut"),
    ("I5b", "  I5 orphan left by resolution (cycle)"),
    ("I6", "Determinism"),
    ("I7", "Budget stability (k <= pool base)"),
    ("I8", "Mandatory not displaced by optional"),
    ("I9", "Threshold removes only soft-scope failures"),
    ("I10", "Resolution order-independence"),
    ("I11", "Pool admissibility"),
    ("I12", "No acting after removal"),
    ("I13", "Ranked score rule (sim 0 if not searched)"),
    ("I14", "Backfill admission (gate, soft or theta<=0)"),
    ("I15", "Admission completeness (gate, soft or sim>=theta)"),
    ("I16", "Canonical tie order (equal score, priority: by id)"),
]
INV_KEYS = [k for k, _ in INVARIANTS]
INV_LABEL = dict(INVARIANTS)
# Invariants to report apart as pending, for a sha that predates the rule they
# state (I10 to I12 need canonical resolution order, the gate-passing ungated
# pool and removed instructions that stop acting, all in 0.4.0 at 10730c8).
# Empty by default. Pass --pending I10 I11 I12 to run against an older sha.
PENDING_INVARIANTS: set[str] = set()
# Similarity shuffles behind I10, in addition to the exact reversal the stub
# allows, and the tolerance for comparing the stub's similarities with BEAR's
# float32 ones at a pool boundary (I11).
ORDER_SHUFFLES = 1
SIM_TOL = 1e-5
SCORE_TOL = 1e-9


# ---------------------------------------------------------------------------
# Controlled embedder
# ---------------------------------------------------------------------------

class ClusteredEmbedder:
    """Deterministic clustered similarities.

    Every instruction and query text carries a marker ``<<c=C v=V s=S>>``. The
    vector is the unit centre of cluster C plus Gaussian noise whose norm is
    NOISE[S], seeded by (C, V, S, query-or-passage), then normalised. Texts in
    one cluster have cosine about 0.2 to 0.9 depending on S, texts in different
    clusters about -0.3 to 0.3, so a threshold of 0.3 cuts through clusters.
    Equal markers give equal vectors and therefore exact similarity ties.
    """

    MARK = re.compile(r"<<c=(\d+) v=(\d+) s=(\d+)>>")
    NOISE = (0.5, 1.0, 2.0)

    def __init__(self, dim: int = EMBED_DIM, n_clusters: int = MAX_CLUSTERS,
                 seed: int = STUB_SEED) -> None:
        rng = np.random.default_rng(seed)
        centres = rng.standard_normal((n_clusters, dim))
        self._centres = centres / np.linalg.norm(centres, axis=1, keepdims=True)
        self.dim = dim
        self._seed = seed
        self._cache: dict[tuple, np.ndarray] = {}

    def _vec(self, text: str, is_query: bool) -> np.ndarray:
        m = self.MARK.search(text)
        c, v, s = (int(g) for g in m.groups()) if m else (0, 0, 2)
        key = (c, v, s, int(is_query))
        vec = self._cache.get(key)
        if vec is None:
            rng = np.random.default_rng([self._seed, c, v, s, int(is_query)])
            noise = rng.standard_normal(self.dim) * (self.NOISE[s] / math.sqrt(self.dim))
            raw = self._centres[c % len(self._centres)] + noise
            vec = (raw / np.linalg.norm(raw)).astype(np.float32)
            self._cache[key] = vec
        return vec

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        return np.vstack([self._vec(t, is_query) for t in texts])

    def embed_single(self, text: str, is_query: bool = False) -> np.ndarray:
        return self._vec(text, is_query)


STUB = ClusteredEmbedder()


def drops_rows(config_name: str) -> bool:
    """True for a backend whose search leaves rows out (BM25: zero term overlap)."""
    return CONFIGS[config_name]["embedder"] == "bm25"


def lexical_text(text: str, is_query: bool) -> str:
    """The stub's similarity marker written as words, for the BM25 configurations.

    An instruction becomes "Instruction iNN clu<C> ... var<C>x<V>", with the
    cluster word repeated 3 - S times so the stub's noise level S still moves
    the score. A query becomes "query clu<C> var<C>x<V>", or just "query" when
    its marker has V = 0, so a quarter of the queries share no term with any
    instruction body and reach instructions only through header tags. The
    case index is dropped from queries, so no number in an instruction header
    ("priority:50") can match one.
    """
    m = ClusteredEmbedder.MARK.search(text)
    c, v, s = (int(g) for g in m.groups()) if m else (0, 0, 2)
    if is_query:
        return "query" if v == 0 else f"query clu{c} var{c}x{v}"
    words = " ".join([f"clu{c}"] * (3 - s) + [f"var{c}x{v}"])
    return ClusteredEmbedder.MARK.sub(words, text)


def query_of(r: Retriever, case: dict) -> str:
    """The query text a retriever is asked, rendered for its configuration."""
    if getattr(r, "_wp1_lexical", False):
        return lexical_text(case["query"], True)
    return case["query"]


# ---------------------------------------------------------------------------
# Corpus and case generator
# ---------------------------------------------------------------------------

def _add(lst: list, x: str) -> None:
    if x not in lst:
        lst.append(x)


def generate_corpus(index: int) -> dict:
    """One random corpus, as JSON-serialisable instruction dicts."""
    rng = random.Random(f"wp1-corpus-{BASE_SEED}-{index}")
    n = rng.randint(MIN_N, MAX_N)
    knobs = {
        "p_gate": 0.0 if rng.random() < 0.15 else rng.uniform(0.1, 0.7),
        "p_soft": rng.uniform(0.2, 0.8),
        "p_mand": rng.uniform(0.03, 0.2),
        "p_conf": rng.uniform(0.0, 0.25),
        "p_sup": rng.uniform(0.0, 0.15),
        "p_req": rng.uniform(0.0, 0.35),
        "p_missing": rng.uniform(0.0, 0.15),
        "n_clusters": rng.randint(2, MAX_CLUSTERS),
    }
    ids = [f"i{j:02d}" for j in range(n)]
    insts: list[dict] = []
    for iid in ids:
        required = (sorted(rng.sample(TAG_VOCAB, rng.randint(1, 2)))
                    if rng.random() < knobs["p_gate"] else [])
        scope_tags = (sorted(rng.sample(TAG_VOCAB, rng.randint(1, 3)))
                      if rng.random() < knobs["p_soft"] else [])
        labels = sorted(rng.sample(TAG_VOCAB, rng.randint(0, 2)))
        if rng.random() < knobs["p_mand"]:
            mt = rng.choice(MANDATORY_TAGS)
            if rng.random() < 0.7:
                labels = sorted(set(labels) | {mt})
            else:
                scope_tags = sorted(set(scope_tags) | {mt})
        priority = rng.choice([50, 70, 90]) if rng.random() < 0.4 else rng.randint(0, 100)
        c, v, s = rng.randrange(knobs["n_clusters"]), rng.randrange(4), rng.randrange(3)
        insts.append({
            "id": iid,
            "type": rng.choice(TYPES),
            "priority": priority,
            "content": f"Instruction {iid} <<c={c} v={v} s={s}>>",
            "labels": labels,
            "scope_tags": scope_tags,
            "required_tags": required,
            "conflicts_with": [],
            "supersedes": [],
            "requires": [],
        })
    by_id = {d["id"]: d for d in insts}

    def target(j: int) -> str:
        if rng.random() < knobs["p_missing"]:
            return f"ghost{rng.randrange(5)}"
        t = rng.randrange(n - 1)
        return ids[t if t < j else t + 1]

    for j, d in enumerate(insts):
        if rng.random() < knobs["p_conf"]:
            for _ in range(rng.randint(1, 2)):
                t = target(j)
                _add(d["conflicts_with"], t)
                if t in by_id and rng.random() < 0.5:
                    _add(by_id[t]["conflicts_with"], d["id"])
        if rng.random() < knobs["p_sup"]:
            _add(d["supersedes"], target(j))
        if rng.random() < knobs["p_req"]:
            for _ in range(rng.randint(1, 2)):
                _add(d["requires"], target(j))
        if rng.random() < 0.02:
            _add(d["requires"], d["id"])          # self-requirement

    # Structures the independent edges produce too rarely.
    if rng.random() < 0.5:                          # requires cycle of length 2 or 3
        cyc = rng.sample(ids, rng.randint(2, 3))
        for a, b in zip(cyc, cyc[1:] + cyc[:1]):
            _add(by_id[a]["requires"], b)
    if rng.random() < 0.5:                          # supersede chain a > b > c
        a, b, c = rng.sample(ids, 3)
        _add(by_id[a]["supersedes"], b)
        _add(by_id[b]["supersedes"], c)
    mand_ids = [d["id"] for d in insts
                if (set(d["labels"]) | set(d["scope_tags"])) & set(MANDATORY_TAGS)]
    opt_ids = [i for i in ids if i not in mand_ids]
    if len(mand_ids) >= 2 and rng.random() < 0.5:   # mandatory against mandatory
        a, b = rng.sample(mand_ids, 2)
        _add(by_id[a]["conflicts_with"], b)
    if mand_ids and opt_ids and rng.random() < 0.5:  # mandatory against a high-priority optional
        m = rng.choice(mand_ids)
        o = max(opt_ids, key=lambda i: by_id[i]["priority"])
        _add(by_id[o]["conflicts_with"], m)
    if mand_ids and opt_ids and rng.random() < 0.3:  # optional tries to supersede mandatory
        _add(by_id[rng.choice(opt_ids)]["supersedes"], rng.choice(mand_ids))
    return {"index": index, "knobs": knobs, "n_clusters": knobs["n_clusters"],
            "instructions": insts}


def generate_cases(corpus: dict) -> list[dict]:
    """Random contexts and queries for one corpus."""
    rng = random.Random(f"wp1-cases-{BASE_SEED}-{corpus['index']}")
    cases = []
    for ci in range(CASES_PER_CORPUS):
        if rng.random() < 0.25:
            tags, gate_tags = [], []
        else:
            tags = sorted(rng.sample(TAG_VOCAB, rng.randint(1, 4)))
            if rng.random() < 0.1:
                tags.append(rng.choice(MANDATORY_TAGS))
            gate_tags = (sorted(rng.sample(TAG_VOCAB, rng.randint(1, 2)))
                         if rng.random() < 0.3 else [])
        c = rng.randrange(corpus["n_clusters"])
        v, s = rng.randrange(4), rng.randrange(3)
        cases.append({"tags": tags, "gate_tags": gate_tags,
                      "query": f"query {ci} <<c={c} v={v} s={s}>>"})
    return cases


# ---------------------------------------------------------------------------
# Retriever construction and traced retrieval
# ---------------------------------------------------------------------------

def build_instruction(d: dict) -> Instruction:
    return Instruction(
        id=d["id"],
        type=InstructionType(d["type"]),
        priority=d["priority"],
        content=d["content"],
        scope=ScopeCondition(tags=list(d["scope_tags"]),
                             required_tags=list(d["required_tags"])),
        conflicts_with=list(d["conflicts_with"]),
        supersedes=list(d["supersedes"]),
        requires=list(d["requires"]),
        tags=list(d["labels"]),
    )


def config_kwargs(config_name: str, extra: dict | None = None) -> dict:
    spec = CONFIGS[config_name]
    kw = dict(default_top_k=DEFAULT_TOP_K, default_threshold=THRESHOLD,
              priority_weight=PRIORITY_WEIGHT, mandatory_tags=list(MANDATORY_TAGS),
              embedding_query_prefix="", embedding_passage_prefix="")
    if spec["embedder"] == "hash":
        kw.update(embedding_model="hash", embedding_dim=768)
    elif spec["embedder"] == "bm25":
        kw.update(embedding_model="bm25", embedding_backend=EmbeddingBackend.BM25,
                  embedding_dim=0)
    else:
        kw.update(embedding_model="wp1-clustered-stub", embedding_dim=EMBED_DIM)
    kw.update(spec["overrides"])
    kw.update(extra or {})
    return kw


def build_retriever(instructions: list[dict], config_name: str,
                    extra: dict | None = None) -> tuple[Retriever, Config]:
    lexical = drops_rows(config_name)
    corpus = Corpus()
    for d in instructions:
        if lexical:
            d = dict(d, content=lexical_text(d["content"], False))
        corpus.add(build_instruction(d))
    config = Config(**config_kwargs(config_name, extra))
    embedder = STUB if CONFIGS[config_name]["embedder"] == "stub" else None
    r = Retriever(corpus, config=config, embedder=embedder)
    r._wp1_lexical = lexical  # read by query_of, not a BEAR attribute
    r.build_index()
    return r, config


def case_for(config_name: str, case: dict) -> dict:
    """The case as a configuration sees it: under a "gate" context, every
    context tag travels as a gate tag, so it gates without entering the
    query text or the soft scope match."""
    if CONFIGS[config_name].get("context") != "gate":
        return case
    return {"tags": [], "gate_tags": sorted(set(case["tags"]) | set(case["gate_tags"])),
            "query": case["query"]}


def make_context(case: dict) -> Context:
    return Context(tags=list(case["tags"]), gate_tags=list(case["gate_tags"]))


def traced(r: Retriever, case: dict, k: int, threshold: float | None = None):
    """Results and the public RetrievalTrace for one retrieval."""
    return r.retrieve_with_trace(query_of(r, case), make_context(case), top_k=k,
                                 threshold=threshold)


def _with_marks(instructions: list[dict], marks: list[str]) -> list[dict]:
    out = []
    for d, m in zip(instructions, marks):
        e = dict(d)
        e["content"] = ClusteredEmbedder.MARK.sub(m, d["content"])
        out.append(e)
    return out


def stub_similarities(instructions: list[dict], case: dict) -> dict[str, float]:
    """Cosine of each instruction with the query under the stub embedder,
    computed here from the markers, independently of the retriever."""
    q = STUB.embed_single(case["query"], is_query=True)
    return {d["id"]: float(np.dot(q, STUB.embed_single(d["content"]))) for d in instructions}


def order_variants(instructions: list[dict], case: dict, config_name: str,
                   seed: str) -> list[tuple[str, list[dict]]]:
    """The same corpus with the similarity order of its instructions changed (I10).

    Only the similarity markers move. Metadata, ids and the rest of the text
    stay, so with the threshold off and top_k=ALL the admitted set is the same.
    With the stub the order for this query is reversed exactly: the instruction
    at similarity rank r takes the marker of the one at rank n-1-r. Shuffles
    are added for every embedder (the only option for hash embeddings).
    """
    marks = [ClusteredEmbedder.MARK.search(d["content"]).group(0) for d in instructions]
    variants = []
    if CONFIGS[config_name]["embedder"] == "stub":
        sims = stub_similarities(instructions, case)
        rank = sorted(range(len(instructions)),
                      key=lambda j: (-sims[instructions[j]["id"]], instructions[j]["id"]))
        rev = list(marks)
        for r_, j in enumerate(rank):
            rev[j] = marks[rank[len(rank) - 1 - r_]]
        variants.append(("reversed", _with_marks(instructions, rev)))
    for s in range(ORDER_SHUFFLES + (0 if variants else 1)):
        shuffled = list(marks)
        random.Random(f"{seed}-{s}").shuffle(shuffled)
        variants.append((f"shuffle {s}", _with_marks(instructions, shuffled)))
    return variants


def resolved_set(r: Retriever, case: dict) -> set[str]:
    """Resolved set with admission held fixed: no cut, threshold off."""
    return resolved_and_admitted(r, case)[0]


def resolved_and_admitted(r: Retriever, case: dict) -> tuple[set[str], tuple]:
    """Resolved set, and how each instruction was admitted (search, backfill,
    mandatory or requires), with no cut and the threshold off."""
    out, trace = traced(r, case, Retriever.ALL, threshold=-2.0)
    return {s.id for s in out}, tuple(sorted(trace.admitted.items()))


def similarity_retriever(instructions: list[dict], config_name: str) -> Retriever:
    """A retriever over the same texts with relationships and mandatory tags
    stripped, for reading similarities through the public API."""
    stripped = [dict(d, conflicts_with=[], supersedes=[], requires=[]) for d in instructions]
    return build_retriever(stripped, config_name, {"mandatory_tags": []})[0]


def public_similarities(instructions: list[dict], case: dict, config_name: str,
                        r: Retriever | None = None) -> dict[str, float]:
    """Similarity of every instruction to the query under a configuration's
    embedder, through the public API. With relationships and mandatory tags
    stripped, the threshold off and top_k=ALL, every instruction is either a
    result or a gate exclusion, and both carry the similarity."""
    r = r or similarity_retriever(instructions, config_name)
    out, trace = traced(r, case, Retriever.ALL, threshold=-2.0)
    sims = {s.id: float(s.similarity) for s in out}
    for i, e in trace.excluded.items():
        if e.get("similarity") is not None:
            sims.setdefault(i, float(e["similarity"]))
    if drops_rows(config_name):
        # A row BM25 did not return shares no term with the query: score 0.
        for d in instructions:
            sims.setdefault(d["id"], 0.0)
    return sims


def signature(out) -> list:
    return [(s.id, repr(float(s.final_score)), repr(float(s.similarity)), bool(s.mandatory))
            for s in out]


# ---------------------------------------------------------------------------
# Invariant checks
# ---------------------------------------------------------------------------

class CaseInfo:
    """Spec-level facts about one (corpus, context) pair, computed independently
    of the retriever from the corpus metadata."""

    def __init__(self, instructions: list[dict], case: dict, mandatory_tags,
                 sims: dict[str, float] | None = None) -> None:
        # Similarity of each instruction to the query, for I11.
        self.sims = sims
        tags = set(case["tags"])
        all_tags = tags | set(case["gate_tags"])
        mand_tags = set(mandatory_tags)
        self.ids = [d["id"] for d in instructions]
        self.by_id = {d["id"]: d for d in instructions}
        self.gate, self.soft, self.mand = {}, {}, {}
        for d in instructions:
            i = d["id"]
            req = d["required_tags"]
            self.gate[i] = (not req) or (bool(all_tags) and set(req) <= all_tags)
            self.soft[i] = (not d["scope_tags"]) or bool(set(d["scope_tags"]) & tags)
            self.mand[i] = bool((set(d["labels"]) | set(d["scope_tags"])) & mand_tags)
        self.req = {i: self.by_id[i]["requires"] for i in self.ids}
        self.conf = {i: self.by_id[i]["conflicts_with"] for i in self.ids}
        self.sup = {i: self.by_id[i]["supersedes"] for i in self.ids}
        self.prio = {i: self.by_id[i]["priority"] for i in self.ids}
        self.adm_mand = [i for i in self.ids if self.mand[i] and self.gate[i]]
        self.gate_passing = [i for i in self.ids if self.gate[i]]
        self.corpus_gates = any(d["required_tags"] for d in instructions)
        # I10 is non-vacuous where two gate-passing items share a conflict or
        # supersede edge, the only place resolution order can matter.
        gp = set(self.gate_passing)
        self.relation_among_admissible = any(
            x in gp for i in self.gate_passing
            for x in (*self.by_id[i]["conflicts_with"], *self.by_id[i]["supersedes"]))
        # BEAR ranks the whole corpus when the corpus has a gate and the
        # context any tag; otherwise it ranks a pool.
        self.gated_query = (any(d["required_tags"] for d in instructions)
                            and bool(all_tags))
        # I2: a mandatory item may be absent only if an admissible mandatory
        # item supersedes it or can beat it in a declared conflict.
        self.mand_excused = {}
        for m in self.adm_mand:
            self.mand_excused[m] = [
                o for o in self.adm_mand if o != m and (
                    m in self.sup[o]
                    or ((m in self.conf[o] or o in self.conf[m])
                        and self.prio[o] >= self.prio[m]))]
        # I8 is non-vacuous where an admissible mandatory item has an edge to
        # an admissible optional one.
        self.mand_opt_edge = any(
            (not self.mand[o]) and self.gate[o] and (
                m in self.conf[o] or o in self.conf[m] or m in self.sup[o])
            for m in self.adm_mand for o in self.ids)


def check_output(info: CaseInfo, out, trace, k: int, threshold: float,
                 alpha: float, flat_backfill: bool = False) -> dict:
    """Return {inv: (violated, nonvacuous, detail)} for one output."""
    ids = [s.id for s in out]
    O = set(ids)
    res: dict[str, tuple[bool, bool, str | None]] = {}

    # I1 gate soundness
    bad = [d for d in ids if not info.gate[d]]
    res["I1"] = (bool(bad), any(info.by_id[d]["required_tags"] for d in ids),
                 f"gate-failing items in output: {bad}" if bad else None)

    # I2 mandatory completeness
    missing = [m for m in info.adm_mand if m not in O and not info.mand_excused[m]]
    res["I2"] = (bool(missing), bool(info.adm_mand),
                 f"admissible mandatory items absent with no mandatory displacer: {missing}"
                 if missing else None)

    # I2b budget bound
    n_mand = sum(1 for d in ids if info.mand[d])
    free = [d for d in ids if not info.mand[d]
            and not any(d in info.req[e] for e in ids if e != d)]
    room = max(0, k - n_mand)
    res["I2b"] = (len(free) > room, True,
                  f"{len(free)} free optional items > room {room} (k={k}, mandatory={n_mand}): {free}"
                  if len(free) > room else None)

    # I3 conflict freeness
    pairs = [(a, b) for a in ids for b in info.conf[a] if b in O]
    admitted = set(trace.admitted)
    nonvac3 = any(b in admitted for a in admitted if a in info.conf for b in info.conf[a])
    res["I3"] = (bool(pairs), nonvac3,
                 f"conflicting pairs both in output: {pairs}" if pairs else None)

    # I3b supersede consistency
    spairs = [(a, b) for a in ids for b in info.sup[a]
              if b in O and not (info.mand[b] and not info.mand[a])]
    nonvac3b = any(b in admitted for a in admitted if a in info.sup for b in info.sup[a])
    res["I3b"] = (bool(spairs), nonvac3b,
                  f"(superseder, superseded) both in output: {spairs}" if spairs else None)

    # I4 dependency closure
    bad4 = []
    for d in ids:
        miss = set(info.req[d]) - O
        if not info.mand[d]:
            if miss:
                bad4.append(f"{d} (optional) lacks {sorted(miss)}")
        else:
            rec = set(trace.missing_prerequisites.get(d, []))
            if rec != miss:
                bad4.append(f"{d} (mandatory) lacks {sorted(miss)} but trace records {sorted(rec)}")
    res["I4"] = (bool(bad4), any(info.req[d] for d in ids),
                 "; ".join(bad4) if bad4 else None)

    # I5 no orphan prerequisites (reachability from items admitted on merit)
    req_only = {d for d in ids if trace.admitted.get(d) == "requires"}
    roots = [d for d in ids if d not in req_only]
    reach = set(roots)
    stack = list(roots)
    while stack:
        x = stack.pop()
        for r in info.req.get(x, []):
            if r in O and r not in reach:
                reach.add(r)
                stack.append(r)
    orphans = req_only - reach
    # Where the orphan arises. R is the set left by relationship resolution,
    # before the cut: admitted, and not removed by superseded, conflict,
    # prerequisite or unrequired (an item the cut removes is recorded as
    # top_k). An output orphan already unreachable within R was left by
    # resolution, whose "unrequired" rule removes only prerequisites no kept
    # item requires, so prerequisites that require each other (a cycle, or a
    # self-requirement) survive their dependent. Otherwise the cut stranded
    # it: it took a slot on its own priority score while its dependent was cut.
    R = {d for d in trace.admitted
         if (trace.excluded.get(d) or {}).get("reason") in (None, "top_k")}
    roots_R = [d for d in R if trace.admitted.get(d) != "requires"]
    reach_R = set(roots_R)
    stack = list(roots_R)
    while stack:
        x = stack.pop()
        for r in info.req.get(x, []):
            if r in R and r not in reach_R:
                reach_R.add(r)
                stack.append(r)
    by_cut = sorted(d for d in orphans if d in reach_R)
    by_res = sorted(d for d in orphans if d not in reach_R)
    head = "items admitted only as prerequisites, unreachable from any item admitted on its own: "
    res["I5"] = (bool(orphans), bool(req_only),
                 head + str(sorted(orphans)) if orphans else None)
    res["I5a"] = (bool(by_cut), bool(req_only),
                  f"{head}{by_cut}; their dependents were cut by top-k" if by_cut else None)
    res["I5b"] = (bool(by_res), bool(req_only),
                  f"{head}{by_res}; already orphaned after relationship resolution "
                  f"(kept alive by a requires cycle)" if by_res else None)

    # I8 mandatory never displaced by an optional item (trace)
    bad8 = []
    for m in info.adm_mand:
        if m in O:
            continue
        rec = trace.excluded.get(m)
        if (rec is None or rec["reason"] not in ("superseded", "conflict")
                or rec["by"] not in info.mand or not info.mand[rec["by"]]):
            bad8.append(f"{m}: {rec}")
    res["I8"] = (bool(bad8), info.mand_opt_edge or bool(bad8),
                 "; ".join(bad8) if bad8 else None)

    # I9 threshold removes only soft-scope failures
    bad9 = []
    n_thr = 0
    for d, rec in trace.excluded.items():
        if rec["reason"] != "threshold":
            continue
        n_thr += 1
        sim = rec["similarity"]
        if d not in info.gate or info.soft[d] or not info.gate[d] or sim is None or sim >= threshold:
            bad9.append(f"{d} (soft={info.soft.get(d)}, gate={info.gate.get(d)}, sim={sim})")
    res["I9"] = (bool(bad9), n_thr > 0, "; ".join(bad9) if bad9 else None)

    # I11 pool admissibility: the ranked pool is the p = min(pool,
    # #gate-passing) most similar gate-passing instructions. (a) Every
    # gate-passing one strictly above the p-th similarity was a candidate, so
    # it appears in the trace other than as a gate exclusion. (b) None strictly
    # below it was a search candidate (admitted by "search" or set aside by
    # the threshold). Instructions outside the pool may still enter through
    # mandatory injection or requires, which (b) allows. Ties at the boundary
    # are left alone.
    if info.sims is not None and info.gate_passing:
        g_sims = sorted((info.sims[i] for i in info.gate_passing), reverse=True)
        p = min(trace.pool, len(g_sims))
        if p >= len(g_sims):
            above, below = list(info.gate_passing), []
        elif p > 0:
            boundary = g_sims[p - 1]
            above = [i for i in info.gate_passing if info.sims[i] > boundary + SIM_TOL]
            below = [i for i in info.gate_passing if info.sims[i] < boundary - SIM_TOL]
        else:
            above, below = [], list(info.gate_passing)
        if getattr(info, "drops_rows", False):
            # A backend that drops rows cannot rank a row it never returns.
            above = [i for i in above if info.sims[i] > SIM_TOL]
        seen = set(trace.admitted) | {d for d, e in trace.excluded.items() if e["reason"] != "gate"}
        searched = ({d for d, h in trace.admitted.items() if h == "search"}
                    | {d for d, e in trace.excluded.items() if e["reason"] == "threshold"})
        missed = sorted(i for i in above if i not in seen)
        extra = sorted(i for i in below if i in searched)
        bad11 = []
        if missed:
            bad11.append(f"gate-passing items within the top {p} never candidates: {missed}")
        if extra:
            bad11.append(f"gate-passing items below the top {p} searched: {extra}")
        res["I11"] = (bool(bad11), (not trace.gated) and info.corpus_gates,
                      f"pool {trace.pool}, gated={trace.gated}: " + "; ".join(bad11)
                      if bad11 else None)
    else:
        res["I11"] = (False, False, None)

    # I15 admission completeness: every candidate the admission rule admits
    # is admitted. Gated query: the whole corpus is ranked, so every
    # instruction is a candidate. Ungated query: the pool, as in I11 (not
    # restricted for row-dropping backends, since that restriction is what
    # this checks).
    if info.sims is not None:
        if trace.gated:
            cands = list(info.gate_passing)
        else:
            g_sims15 = sorted((info.sims[i] for i in info.gate_passing), reverse=True)
            p15 = min(trace.pool, len(g_sims15))
            if p15 >= len(g_sims15):
                cands = list(info.gate_passing)
            elif p15 > 0:
                b15 = g_sims15[p15 - 1]
                cands = [i for i in info.gate_passing if info.sims[i] > b15 + SIM_TOL]
            else:
                cands = []
        rule15 = [i for i in cands
                  if info.soft[i] or info.sims[i] >= threshold + SIM_TOL]
        missing15 = sorted(i for i in rule15 if i not in trace.admitted)
        res["I15"] = (bool(missing15), bool(rule15),
                      f"admissible candidates never admitted (gated={trace.gated}, pool "
                      f"{trace.pool}): " + ", ".join(
                          f"{i} (soft={info.soft[i]}, sim={info.sims[i]:.4f}, "
                          f"required={info.by_id[i]['required_tags']})" for i in missing15)
                      if missing15 else None)
    else:
        res["I15"] = (False, False, None)

    # I16 canonical tie order among ranked rows, in the output and at the cut.
    def ranked_row(d: str) -> bool:
        return (not info.mand.get(d)) and trace.admitted.get(d) in ("search", "required_tags")

    ranked = [sc for sc in out if ranked_row(sc.id)]
    bad16 = []
    n_ties = 0
    for a_, b_ in zip(ranked, ranked[1:]):
        if (float(a_.final_score) == float(b_.final_score)
                and info.prio[a_.id] == info.prio[b_.id]):
            n_ties += 1
            if not a_.id < b_.id:
                bad16.append(f"{a_.id} listed before {b_.id} at equal score "
                             f"{float(a_.final_score)!r} and priority {info.prio[a_.id]}")
    # Compare cut rows only with kept rows that took a ranked slot. A row no
    # other output row requires took one. A required row may be in the output
    # only through closure (the cut keeps a kept row's prerequisites), so it is
    # left out of this comparison, which can miss a violation but not invent one.
    required_by_out = {r for e in ids for r in info.req[e] if r != e}
    kept_keys: dict[tuple, list[str]] = {}
    for sc in ranked:
        if sc.id in required_by_out:
            continue
        kept_keys.setdefault((float(sc.final_score), info.prio[sc.id]), []).append(sc.id)
    for d, e in trace.excluded.items():
        if e["reason"] != "top_k" or not ranked_row(d):
            continue
        pn = info.prio[d] / 100.0
        if trace.admitted.get(d) == "required_tags":
            score = pn if flat_backfill else alpha * pn
        else:
            sim = float(e["similarity"]) if e.get("similarity") is not None else 0.0
            score = (1 - alpha) * sim + alpha * pn
        tied = kept_keys.get((score, info.prio[d]), [])
        if tied:
            n_ties += 1
            larger = [x for x in tied if x > d]
            if larger:
                bad16.append(f"{d} cut while {larger} kept at equal score {score!r} and "
                             f"priority {info.prio[d]}")
    res["I16"] = (bool(bad16), n_ties > 0, "; ".join(bad16) if bad16 else None)

    # I12 no acting after removal: a conflict or superseded exclusion never
    # names a remover that was already excluded when it was recorded.
    order_ex = {d: n for n, d in enumerate(trace.excluded)}
    bad12 = [f"{d} removed ({e['reason']}) by {e['by']}, already excluded "
             f"({trace.excluded[e['by']]['reason']})"
             for d, e in trace.excluded.items()
             if e["reason"] in ("conflict", "superseded") and e["by"] in order_ex
             and order_ex[e["by"]] < order_ex[d]]
    n_removals = sum(1 for e in trace.excluded.values() if e["reason"] in ("conflict", "superseded"))
    res["I12"] = (bool(bad12), n_removals > 1, "; ".join(bad12) if bad12 else None)

    # I13 ranked score rule: a non-mandatory output row that entered by search
    # or by the backfill scores (1 - alpha) * sim + alpha * p / 100, where sim
    # is 0 for a row the search did not return (the backfill), and that row
    # records similarity 0. Mandatory injection and prerequisites are exempt
    # from the cut and keep priority / 100, so they are not checked here.
    bad13 = []
    n_backfilled_out = 0
    for sc in out:
        d = sc.id
        how = trace.admitted.get(d)
        if info.mand.get(d) or how not in ("search", "required_tags"):
            continue
        sim = float(sc.similarity)
        if how == "required_tags":
            n_backfilled_out += 1
            if sim != 0.0:
                bad13.append(f"{d} backfilled with recorded similarity {sim}")
            sim = 0.0
        want = (1.0 - alpha) * sim + alpha * info.prio[d] / 100.0
        if abs(float(sc.final_score) - want) > SCORE_TOL:
            bad13.append(f"{d} ({how}) scores {float(sc.final_score):.6f}, rule gives {want:.6f}")
    res["I13"] = (bool(bad13), n_backfilled_out > 0, "; ".join(bad13) if bad13 else None)

    # I14 backfill admission: gate, and soft scope or threshold <= 0.
    backfilled = [d for d, h in trace.admitted.items() if h == "required_tags"]
    bad14 = [f"{d} backfilled with gate={info.gate.get(d)}, soft={info.soft.get(d)}, "
             f"theta={threshold}"
             for d in backfilled
             if not (info.gate.get(d) and (info.soft.get(d) or threshold <= 0.0))]
    rejected = sum(1 for e in trace.excluded.values()
                   if e["reason"] == "threshold" and e.get("similarity") == 0.0)
    res["I14"] = (bool(bad14), bool(backfilled) or rejected > 0,
                  "; ".join(bad14) if bad14 else None)
    return res


def is_subsequence(a: list, b: list) -> bool:
    it = iter(b)
    return all(x in it for x in a)


# ---------------------------------------------------------------------------
# Per-corpus work
# ---------------------------------------------------------------------------

def _empty_inv_stats() -> dict:
    return {inv: {"outputs_violated": 0, "outputs_nonvacuous": 0, "outputs": 0,
                  "cases_violated": 0, "first": None} for inv in INV_KEYS}


def run_config_on_corpus(corpus: dict, cases: list[dict], config_name: str,
                         want_digest: bool = False) -> dict:
    r, config = build_retriever(corpus["instructions"], config_name)
    threshold = config.default_threshold
    pool_base = config.retrieval_pool or 3 * config.default_top_k
    inv = _empty_inv_stats()
    info_stats = defaultdict(float)
    digest = hashlib.sha256()
    is_stub = CONFIGS[config_name]["embedder"] == "stub"
    # Similarities for I11: from the stub's markers, or through the public API.
    sim_r = None if is_stub else similarity_retriever(corpus["instructions"], config_name)
    # I10 retrievers over order variants, cached by their texts.
    variant_cache: dict[tuple, Retriever] = {}

    def variant_retriever(ins: list[dict]) -> Retriever:
        key = tuple(d["content"] for d in ins)
        if key not in variant_cache:
            variant_cache[key] = build_retriever(ins, config_name)[0]
        return variant_cache[key]

    cases = [case_for(config_name, c) for c in cases]
    flat = bool(getattr(config, "restore_flat_backfill", False)
                or getattr(config, "restore_below_threshold", False))
    for ci, case in enumerate(cases):
        sims = (stub_similarities(corpus["instructions"], case) if is_stub
                else public_similarities(corpus["instructions"], case, config_name, sim_r))
        info = CaseInfo(corpus["instructions"], case, config.mandatory_tags, sims=sims)
        info.drops_rows = drops_rows(config_name)
        case_viol = set()
        prev_ids = None
        outputs = {}
        for k in K_VALUES:
            out, trace = traced(r, case, k)
            outputs[k] = (out, trace)
            ids = [s.id for s in out]
            if want_digest:
                digest.update(json.dumps([ci, k, signature(out)]).encode())
            res = check_output(info, out, trace, k, threshold, config.priority_weight,
                               flat_backfill=flat)
            # I7, consecutive k within the pool base
            if prev_ids is not None and k <= pool_base:
                ok = set(prev_ids) <= set(ids)
                ok_order = ok and is_subsequence(prev_ids, ids)
                res["I7"] = (not ok_order, True,
                             None if ok_order else
                             f"k={k-1} -> {prev_ids}; k={k} -> {ids}"
                             + ("" if ok else f"; dropped {sorted(set(prev_ids) - set(ids))}"))
                info_stats["i7_pairs"] += 1
                info_stats["i7_prefix"] += ids[:len(prev_ids)] == prev_ids
            prev_ids = ids
            for key, (viol, nonvac, detail) in res.items():
                st = inv[key]
                st["outputs"] += 1
                st["outputs_nonvacuous"] += bool(nonvac)
                if viol:
                    st["outputs_violated"] += 1
                    case_viol.add(key)
                    if st["first"] is None:
                        st["first"] = {"corpus": corpus["index"], "case": ci, "k": k,
                                       "detail": detail}
            # descriptive statistics
            info_stats["outputs"] += 1
            info_stats["out_size"] += len(ids)
            info_stats["out_gt_k"] += len(ids) > k
            info_stats["threshold_removals"] += sum(
                1 for e in trace.excluded.values() if e["reason"] == "threshold")
            info_stats["requires_admissions"] += sum(
                1 for h in trace.admitted.values() if h == "requires")
            n_bf = sum(1 for h in trace.admitted.values() if h == "required_tags")
            info_stats["backfill_admissions"] += n_bf
            info_stats["outputs_with_backfill_admission"] += n_bf > 0
            info_stats["backfill_rejections"] += sum(
                1 for e in trace.excluded.values()
                if e["reason"] == "threshold" and e.get("similarity") == 0.0)
            info_stats["backfilled_in_output"] += sum(
                1 for sc in out if trace.admitted.get(sc.id) == "required_tags")
            info_stats["outputs_with_missing_prereq_record"] += bool(trace.missing_prerequisites)
            # An item displaced (conflict or superseded) by a winner that is not
            # in the output either: the winner was cut by top-k, or removed in
            # resolution itself. Both follow from the precedence order (the
            # relationships act on the admitted set, before the cut), and the
            # spec should say so. Not an invariant.
            O = set(ids)
            cut_w = rem_w = False
            for e in trace.excluded.values():
                if (e["reason"] in ("conflict", "superseded") and e["by"] in info.by_id
                        and e["by"] not in O):
                    w = trace.excluded.get(e["by"])
                    if w is not None and w["reason"] == "top_k":
                        cut_w = True
                    else:
                        rem_w = True
            info_stats["outputs_displaced_by_cut_winner"] += cut_w
            info_stats["outputs_displaced_by_removed_winner"] += rem_w
            info_stats["mand_displaced_by_mand"] += sum(
                1 for m in info.adm_mand if m not in O and info.mand_excused[m])
            info_stats["topk_cut_binding"] += any(
                e["reason"] == "top_k" for e in trace.excluded.values())

        # Lexical admission gap (row-dropping backends): admissible under the
        # admission rule (gate, and soft scope or similarity >= threshold, a
        # non-mandatory row) yet never a candidate, because the search dropped
        # it and the backfill covers only rows with required tags.
        if info.drops_rows:
            _, tr_all = traced(r, case, Retriever.ALL)
            seen_all = set(tr_all.admitted) | set(tr_all.excluded)
            gap = [i for i in info.ids if info.gate[i] and not info.mand[i]
                   and (info.soft[i] or info.sims.get(i, 0.0) >= threshold)
                   and i not in seen_all]
            info_stats["lexical_gap_rows"] += len(gap)
            info_stats["lexical_gap_cases"] += bool(gap)
            info_stats["lexical_gap_rows_with_required_tags"] += sum(
                1 for i in gap if info.by_id[i]["required_tags"])

        # I6 determinism, on three k values per case
        rng = random.Random(f"wp1-det-{BASE_SEED}-{corpus['index']}-{ci}")
        det_ks = sorted({1, rng.choice(K_VALUES), K_VALUES[-1]})
        r_fresh, _ = build_retriever(corpus["instructions"], config_name)
        det_bad = []
        for k in det_ks:
            ref = signature(outputs[k][0])
            again, _ = traced(r, case, k)
            public = r.retrieve(query_of(r, case), make_context(case), top_k=k)
            fresh, _ = traced(r_fresh, case, k)
            for name, sig in (("repeat", signature(again)), ("public", signature(public)),
                              ("fresh", signature(fresh))):
                if sig != ref:
                    det_bad.append(f"k={k} {name}: {sig} != {ref}")
        st = inv["I6"]
        st["outputs"] += len(det_ks)
        st["outputs_nonvacuous"] += len(det_ks)
        if det_bad:
            st["outputs_violated"] += 1
            case_viol.add("I6")
            if st["first"] is None:
                st["first"] = {"corpus": corpus["index"], "case": ci, "k": det_ks[0],
                               "detail": "; ".join(det_bad)}

        # I10 resolution order-independence. top_k=ALL and the threshold off
        # fix the admitted set (every gate-passing item), so only the
        # similarity order of the candidates differs.
        ref_set, ref_adm = resolved_and_admitted(r, case)
        diffs = []
        for label, ins in order_variants(corpus["instructions"], case, config_name,
                                         perm_prefix(corpus["index"])):
            got, got_adm = resolved_and_admitted(variant_retriever(ins), case)
            if got_adm != ref_adm:
                # Only where the search drops rows: the variant admits other
                # rows, so resolution order is not what changed.
                info_stats["i10_variants_skipped_admitted_set_changed"] += 1
                continue
            info_stats["i10_variants_compared"] += 1
            if got != ref_set:
                diffs.append(f"{label}: only original {sorted(ref_set - got)}, "
                             f"only reordered {sorted(got - ref_set)}")
        st = inv["I10"]
        st["outputs"] += 1
        st["outputs_nonvacuous"] += info.relation_among_admissible
        if diffs:
            st["outputs_violated"] += 1
            case_viol.add("I10")
            if st["first"] is None:
                st["first"] = {"corpus": corpus["index"], "case": ci, "k": Retriever.ALL,
                               "detail": "; ".join(diffs)}
        for key in case_viol:
            inv[key]["cases_violated"] += 1
        info_stats["cases"] += 1
        info_stats["ungated_cases"] += not info.gated_query
    return {"inv": inv, "info": dict(info_stats),
            "digest": digest.hexdigest() if want_digest else None}


def sensitivity_on_corpus(corpus: dict, cases: list[dict]) -> dict:
    """Pool growth under main defaults: k above the base, and pool at fixed k."""
    out: dict = {"above_base": defaultdict(int), "fixed_k": {}, "examples": {}}
    infos = [CaseInfo(corpus["instructions"], c, MANDATORY_TAGS) for c in cases]

    # (a) retrieval_pool = SENS_POOL_BASE, k from 1 to 30. For each item that
    # drops out as k grows, record the trace reason at the larger k.
    r, _ = build_retriever(corpus["instructions"], "main",
                           {"retrieval_pool": SENS_POOL_BASE})
    for ci, (case, info) in enumerate(zip(cases, infos)):
        tag = "gated" if info.gated_query else "ungated"
        prev = None
        for k in K_VALUES:
            res, trace = traced(r, case, k)
            ids = [s.id for s in res]
            if prev is not None:
                region = "within" if k <= SENS_POOL_BASE else "above"
                out["above_base"][f"{tag}_{region}_pairs"] += 1
                dropped = sorted(set(prev) - set(ids))
                if dropped:
                    out["above_base"][f"{tag}_{region}_violations"] += 1
                    for d in dropped:
                        rec = trace.excluded.get(d) or {}
                        reason = rec.get("reason", "none")
                        out["above_base"][f"{tag}_{region}_reason_{reason}"] += 1
                        key = f"{tag}_{region}_{reason}"
                        if key not in out["examples"]:
                            out["examples"][key] = {
                                "corpus": corpus["index"], "case": ci, "k": k,
                                "before": prev, "after": ids, "dropped": d,
                                "trace_record": rec}
            prev = ids
    out["above_base"] = dict(out["above_base"])

    # (b) pool varied at fixed k, against a whole-corpus pool
    rets = {p: build_retriever(corpus["instructions"], "main", {"retrieval_pool": p})[0]
            for p in (*SENS_POOLS, WHOLE_POOL)}
    for k in SENS_FIXED_K:
        rows = {p: {"cases": 0, "differ": 0, "jaccard_sum": 0.0} for p in SENS_POOLS}
        for case, info in zip(cases, infos):
            if info.gated_query:
                continue
            ref = {s.id for s in rets[WHOLE_POOL].retrieve(query_of(rets[WHOLE_POOL], case),
                                                           make_context(case), top_k=k)}
            for p in SENS_POOLS:
                got = {s.id for s in rets[p].retrieve(query_of(rets[p], case),
                                                      make_context(case), top_k=k)}
                rows[p]["cases"] += 1
                rows[p]["differ"] += got != ref
                union = got | ref
                rows[p]["jaccard_sum"] += (len(got & ref) / len(union)) if union else 1.0
        out["fixed_k"][k] = rows
    return out


def worker(task: tuple) -> list[dict]:
    indices, config_names, do_sensitivity, digest_only = task
    results = []
    for idx in indices:
        corpus = generate_corpus(idx)
        cases = generate_cases(corpus)
        row = {"index": idx, "n": len(corpus["instructions"]), "configs": {}}
        for name in config_names:
            row["configs"][name] = run_config_on_corpus(
                corpus, cases, name, want_digest=(name == "main"))
            if digest_only:
                row["configs"][name] = {"digest": row["configs"][name]["digest"]}
        if do_sensitivity and not digest_only:
            row["sensitivity"] = sensitivity_on_corpus(corpus, cases)
        results.append(row)
    return results


def run_parallel(indices: list[int], config_names: list[str], do_sensitivity: bool,
                 digest_only: bool, workers: int, chunk: int = 20) -> list[dict]:
    tasks = [(indices[i:i + chunk], config_names, do_sensitivity, digest_only)
             for i in range(0, len(indices), chunk)]
    rows: list[dict] = []
    if workers <= 1:
        for t in tasks:
            rows.extend(worker(t))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for part in ex.map(worker, tasks):
                rows.extend(part)
    rows.sort(key=lambda r: r["index"])
    return rows


# ---------------------------------------------------------------------------
# Counterexample shrinking
# ---------------------------------------------------------------------------

def perm_prefix(corpus_index: int) -> str:
    """Seed prefix for a corpus's I10 permutations, shared by the run and the shrinker."""
    return f"wp1-perm-{BASE_SEED}-{corpus_index}"


def violates(config_name: str, instructions: list[dict], case: dict, k: int, inv: str,
             perm: str = "wp1-perm") -> tuple[bool, str | None]:
    if not instructions:
        return False, None
    r, config = build_retriever(instructions, config_name)
    is_stub = CONFIGS[config_name]["embedder"] == "stub"
    if inv == "I10":
        ref, ref_adm = resolved_and_admitted(r, case)
        for label, ins in order_variants(instructions, case, config_name, perm):
            got, got_adm = resolved_and_admitted(build_retriever(ins, config_name)[0], case)
            if got_adm != ref_adm:
                continue
            if got != ref:
                return True, (f"resolved set {sorted(ref)} becomes {sorted(got)} when the "
                              f"similarity order is changed ({label})")
        return False, None
    sims = (stub_similarities(instructions, case) if is_stub
            else public_similarities(instructions, case, config_name))
    info = CaseInfo(instructions, case, config.mandatory_tags, sims=sims)
    info.drops_rows = drops_rows(config_name)
    if inv == "I7":
        if k < 2:
            return False, None
        a = [s.id for s in r.retrieve(query_of(r, case), make_context(case), top_k=k - 1)]
        b = [s.id for s in r.retrieve(query_of(r, case), make_context(case), top_k=k)]
        bad = not (set(a) <= set(b) and is_subsequence(a, b))
        return bad, (f"k={k-1} -> {a}; k={k} -> {b}" if bad else None)
    if inv == "I6":
        x, _ = traced(r, case, k)
        r2, _ = build_retriever(instructions, config_name)
        y, _ = traced(r2, case, k)
        z = r.retrieve(query_of(r, case), make_context(case), top_k=k)
        bad = not (signature(x) == signature(y) == signature(z))
        return bad, ("outputs differ" if bad else None)
    out, trace = traced(r, case, k)
    flat = bool(getattr(config, "restore_flat_backfill", False)
                or getattr(config, "restore_below_threshold", False))
    viol, _, detail = check_output(info, out, trace, k, config.default_threshold,
                                   config.priority_weight, flat_backfill=flat)[inv]
    return viol, detail


def _scrub(instructions: list[dict], drop_id: str) -> list[dict]:
    out = []
    for d in instructions:
        if d["id"] == drop_id:
            continue
        e = dict(d)
        for f in ("conflicts_with", "supersedes", "requires"):
            e[f] = [x for x in d[f] if x != drop_id]
        out.append(e)
    return out


def shrink(config_name: str, instructions: list[dict], case: dict, k: int, inv: str,
           max_rounds: int = 6, perm: str = "wp1-perm") -> tuple[list[dict], dict, int]:
    """Greedy delta-debugging: smallest k, fewest instructions, fewest edges and tags."""
    def fails(ins, cs, kk):
        try:
            return violates(config_name, ins, cs, kk, inv, perm)[0]
        except Exception:  # noqa: BLE001
            return False

    lo = 2 if inv == "I7" else 1
    for kk in range(lo, k):
        if fails(instructions, case, kk):
            k = kk
            break
    for _ in range(max_rounds):
        changed = False
        for d in list(instructions):
            cand = _scrub(instructions, d["id"])
            if fails(cand, case, k):
                instructions, changed = cand, True
                continue
            cand = [e for e in instructions if e["id"] != d["id"]]
            if fails(cand, case, k):
                instructions, changed = cand, True
        for j in range(len(instructions)):
            for f in ("conflicts_with", "supersedes", "requires", "labels",
                      "scope_tags", "required_tags"):
                for x in list(instructions[j][f]):
                    cand = [dict(e) for e in instructions]
                    cand[j][f] = [y for y in instructions[j][f] if y != x]
                    if fails(cand, case, k):
                        instructions, changed = cand, True
        for f in ("tags", "gate_tags"):
            for x in list(case[f]):
                cs = dict(case)
                cs[f] = [y for y in case[f] if y != x]
                if fails(instructions, cs, k):
                    case, changed = cs, True
        for kk in range(lo, k):
            if fails(instructions, case, kk):
                k, changed = kk, True
                break
        if not changed:
            break
    return instructions, case, k


def describe_counterexample(config_name: str, instructions: list[dict], case: dict,
                            k: int, inv: str, perm: str = "wp1-perm") -> dict:
    r, config = build_retriever(instructions, config_name)
    out, trace = traced(r, case, k, threshold=-2.0 if inv == "I10" else None)
    _, detail = violates(config_name, instructions, case, k, inv, perm)
    # Similarity of every instruction to the query under this configuration's embedder.
    sims = {i: round(s, 4) for i, s in
            public_similarities(instructions, case, config_name).items()}
    return {
        "config": config_name,
        "config_overrides": CONFIGS[config_name]["overrides"],
        "config_full": {k_: (v_ if not isinstance(v_, tuple) else list(v_))
                        for k_, v_ in config_kwargs(config_name).items()},
        "invariant": inv,
        "invariant_label": INV_LABEL[inv],
        "k": k,
        "context": {"tags": case["tags"], "gate_tags": case["gate_tags"]},
        "query": case["query"],
        "query_as_retrieved": query_of(r, case),
        "instructions": instructions,
        "similarity_to_query": sims,
        "output": [(s.id, round(float(s.final_score), 4)) for s in out],
        "trace_admitted": dict(trace.admitted),
        "trace_excluded": dict(trace.excluded),
        "trace_missing_prerequisites": dict(trace.missing_prerequisites),
        "trace_pool": trace.pool,
        "trace_gated": trace.gated,
        "violation": detail,
    }


# ---------------------------------------------------------------------------
# Statistics and reporting
# ---------------------------------------------------------------------------

def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    lo = 0.0 if x == 0 else float(stats.beta.ppf(alpha / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(stats.beta.ppf(1 - alpha / 2, x + 1, n - x))
    return lo, hi


def aggregate(rows: list[dict], config_names: list[str]) -> dict:
    agg = {}
    for name in config_names:
        inv_tot = {inv: {"corpora_violated": 0, "cases_violated": 0, "outputs_violated": 0,
                         "outputs": 0, "outputs_nonvacuous": 0, "first": None}
                   for inv in INV_KEYS}
        info = defaultdict(float)
        for row in rows:
            cr = row["configs"][name]
            for inv in INV_KEYS:
                s = cr["inv"][inv]
                t = inv_tot[inv]
                t["corpora_violated"] += s["outputs_violated"] > 0
                t["cases_violated"] += s["cases_violated"]
                t["outputs_violated"] += s["outputs_violated"]
                t["outputs"] += s["outputs"]
                t["outputs_nonvacuous"] += s["outputs_nonvacuous"]
                if t["first"] is None and s["first"] is not None:
                    t["first"] = s["first"]
            for key, val in cr["info"].items():
                info[key] += val
        n_corpora = len(rows)
        for inv in INV_KEYS:
            t = inv_tot[inv]
            t["n_corpora"] = n_corpora
            t["corpus_rate"] = t["corpora_violated"] / n_corpora if n_corpora else float("nan")
            t["corpus_ci"] = clopper_pearson(t["corpora_violated"], n_corpora)
            t["output_rate"] = t["outputs_violated"] / t["outputs"] if t["outputs"] else float("nan")
            t["output_ci"] = clopper_pearson(t["outputs_violated"], t["outputs"])
            t["n_cases"] = int(info["cases"])
        o = info["outputs"] or 1
        summary = {
            "outputs": int(info["outputs"]),
            "cases": int(info["cases"]),
            "ungated_cases": int(info["ungated_cases"]),
            "mean_output_size": info["out_size"] / o,
            "frac_output_longer_than_k": info["out_gt_k"] / o,
            "frac_topk_cut_binding": info["topk_cut_binding"] / o,
            "threshold_removals_per_output": info["threshold_removals"] / o,
            "requires_admissions_per_output": info["requires_admissions"] / o,
            "backfill_admissions_per_output": info["backfill_admissions"] / o,
            "frac_outputs_with_backfill_admission": info["outputs_with_backfill_admission"] / o,
            "backfill_rejections_per_output": info["backfill_rejections"] / o,
            "backfilled_in_output_per_output": info["backfilled_in_output"] / o,
            "i10_variants_compared": int(info["i10_variants_compared"]),
            "i10_variants_skipped_admitted_set_changed":
                int(info["i10_variants_skipped_admitted_set_changed"]),
            "lexical_gap_rows": int(info["lexical_gap_rows"]),
            "lexical_gap_cases": int(info["lexical_gap_cases"]),
            "lexical_gap_rows_with_required_tags": int(info["lexical_gap_rows_with_required_tags"]),
            "frac_outputs_with_missing_prereq_record": info["outputs_with_missing_prereq_record"] / o,
            "frac_outputs_displaced_by_cut_winner": info["outputs_displaced_by_cut_winner"] / o,
            "frac_outputs_displaced_by_removed_winner": info["outputs_displaced_by_removed_winner"] / o,
            "mandatory_displaced_by_mandatory": int(info["mand_displaced_by_mand"]),
            "i7_pairs": int(info["i7_pairs"]),
            "i7_frac_strict_prefix": info["i7_prefix"] / info["i7_pairs"] if info["i7_pairs"] else float("nan"),
        }
        agg[name] = {"invariants": inv_tot, "summary": summary}
    return agg


def aggregate_sensitivity(rows: list[dict]) -> dict:
    above = defaultdict(int)
    fixed: dict = {}
    examples: dict = {}
    for row in rows:
        sens = row.get("sensitivity")
        if not sens:
            continue
        for key, val in sens["above_base"].items():
            above[key] += val
        for key, ex in sens.get("examples", {}).items():
            examples.setdefault(key, ex)
        for k, prow in sens["fixed_k"].items():
            fk = fixed.setdefault(str(k), {str(p): {"cases": 0, "differ": 0, "jaccard_sum": 0.0}
                                           for p in SENS_POOLS})
            for p, v in prow.items():
                for f in ("cases", "differ", "jaccard_sum"):
                    fk[str(p)][f] += v[f]
    above_out = {}
    for tag in ("ungated", "gated"):
        for region in ("within", "above"):
            pairs = above.get(f"{tag}_{region}_pairs", 0)
            viol = above.get(f"{tag}_{region}_violations", 0)
            prefix = f"{tag}_{region}_reason_"
            above_out[f"{tag}_{region}"] = {
                "pairs": pairs, "violations": viol,
                "rate": viol / pairs if pairs else float("nan"),
                "ci": clopper_pearson(viol, pairs),
                "dropped_by_reason": {k_[len(prefix):]: v_ for k_, v_ in above.items()
                                      if k_.startswith(prefix)}}
    for k, prow in fixed.items():
        for p, v in prow.items():
            v["frac_differ"] = v["differ"] / v["cases"] if v["cases"] else float("nan")
            v["frac_differ_ci"] = clopper_pearson(v["differ"], v["cases"])
            v["mean_jaccard"] = v["jaccard_sum"] / v["cases"] if v["cases"] else float("nan")
    return {"pool_base": SENS_POOL_BASE, "above_base": above_out,
            "fixed_k": fixed, "pools": list(SENS_POOLS), "examples": examples}


def bear_install_provenance() -> dict:
    """Where the installed BEAR came from: direct_url and an export's recorded sha."""
    info: dict = {}
    try:
        import importlib.metadata as md
        du = md.distribution("bear").read_text("direct_url.json")
        if du:
            url = json.loads(du).get("url")
            info["direct_url"] = url
            if url and url.startswith("file://"):
                for name in ("BEAR_GIT_SHA", "EXPORTED_SHA"):
                    f = Path(url[len("file://"):]) / name
                    if f.exists():
                        info["export_sha"] = f.read_text(encoding="utf-8").strip()
                        break
    except Exception:  # noqa: BLE001
        pass
    return info


def fmt_rate(x: int, n: int, ci: tuple[float, float]) -> str:
    if n == 0:
        return "n/a"
    return f"{x}/{n} = {x / n:.4f} [{ci[0]:.4f}, {ci[1]:.4f}]"


def print_tables(agg: dict, sens: dict | None, config_names: list[str],
                 pending: set[str] = frozenset()) -> None:
    active = [inv for inv in INV_KEYS if inv not in pending]
    for name in config_names:
        a = agg[name]
        s = a["summary"]
        print(f"\n--- {name} ({CONFIGS[name]['label']}) ---")
        print(f"cases={s['cases']} (ungated {s['ungated_cases']}), outputs={s['outputs']}, "
              f"mean |output|={s['mean_output_size']:.2f}, "
              f"P(|output|>k)={s['frac_output_longer_than_k']:.3f}, "
              f"P(top-k cut removes >=1)={s['frac_topk_cut_binding']:.3f}")
        print(f"threshold removals/output={s['threshold_removals_per_output']:.3f}, "
              f"requires admissions/output={s['requires_admissions_per_output']:.3f}, "
              f"P(missing-prereq record)={s['frac_outputs_with_missing_prereq_record']:.4f}, "
              f"P(loser of a winner cut by top-k)={s['frac_outputs_displaced_by_cut_winner']:.4f}, "
              f"P(loser of a winner removed in resolution)={s['frac_outputs_displaced_by_removed_winner']:.4f}, "
              f"mandatory displaced by mandatory={s['mandatory_displaced_by_mandatory']}, "
              f"I7 strict-prefix share={s['i7_frac_strict_prefix']:.4f}")
        print(f"backfill admissions/output={s['backfill_admissions_per_output']:.3f} "
              f"(P(any)={s['frac_outputs_with_backfill_admission']:.3f}), "
              f"backfilled rows in output/output={s['backfilled_in_output_per_output']:.3f}, "
              f"backfill rejections (threshold at similarity 0)/output="
              f"{s['backfill_rejections_per_output']:.3f}")
        if s["i10_variants_skipped_admitted_set_changed"] or s["lexical_gap_cases"]:
            print(f"I10 variants compared={s['i10_variants_compared']}, skipped because the "
                  f"admitted set changed={s['i10_variants_skipped_admitted_set_changed']}; "
                  f"lexical admission gap: {s['lexical_gap_rows']} rows in "
                  f"{s['lexical_gap_cases']}/{s['cases']} cases "
                  f"({s['lexical_gap_rows_with_required_tags']} with required tags)")
        print(f"{'Inv':<5} {'Invariant':<42} {'Corpora violated [95% CP CI]':<34} "
              f"{'Outputs violated':<18} {'Non-vacuous outputs':<20}")
        print("-" * 124)
        for block, invs in (("", active),
                            ("pending (expected to hold only on the final release sha)",
                             [i for i in INV_KEYS if i in pending])):
            if not invs:
                continue
            if block:
                print(f"  {block}")
            for inv in invs:
                t = a["invariants"][inv]
                print(f"{inv:<5} {INV_LABEL[inv]:<42} "
                      f"{fmt_rate(t['corpora_violated'], t['n_corpora'], t['corpus_ci']):<34} "
                      f"{t['outputs_violated']}/{t['outputs']:<12} {t['outputs_nonvacuous']}")

    print("\n--- Corpus-level violation rate by configuration (violated corpora / corpora) ---\n")
    header = f"{'Inv':<5}" + "".join(f"{n[:16]:>18}" for n in config_names)
    print(header)
    for inv in INV_KEYS:
        line = f"{inv:<5}"
        for n in config_names:
            t = agg[n]["invariants"][inv]
            line += f"{t['corpora_violated']:>12}/{t['n_corpora']:<5}"
        print(line + ("   (pending)" if inv in pending else ""))

    if sens:
        print("\n--- Pool growth sensitivity (main defaults, stub embedder) ---\n")
        print(f"(a) retrieval_pool = {sens['pool_base']}, k = 1..30, nesting of consecutive k:")
        for key, v in sens["above_base"].items():
            print(f"    {key:<16} pairs={v['pairs']:<7} non-nested={v['violations']:<5} "
                  f"rate={v['rate']:.4f} [{v['ci'][0]:.4f}, {v['ci'][1]:.4f}]"
                  + (f"  dropped items by trace reason: {v['dropped_by_reason']}"
                     if v["dropped_by_reason"] else ""))
        for key, ex in sorted(sens.get("examples", {}).items()):
            print(f"    example {key}: corpus {ex['corpus']} case {ex['case']} k {ex['k'] - 1}->{ex['k']}: "
                  f"{ex['dropped']} dropped, trace {ex['trace_record']}")
        print("\n(b) Ungated cases, output at pool p versus whole-corpus pool:")
        for k, prow in sens["fixed_k"].items():
            print(f"    k = {k}")
            for p, v in prow.items():
                print(f"      pool={p:>3}  cases={v['cases']:<6} differ={v['frac_differ']:.4f} "
                      f"[{v['frac_differ_ci'][0]:.4f}, {v['frac_differ_ci'][1]:.4f}]  "
                      f"mean Jaccard={v['mean_jaccard']:.4f}")


class _Tee:
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
        return len(data)

    def flush(self):
        for s in self._streams:
            s.flush()

    def __getattr__(self, name):
        return getattr(self._streams[0], name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n-corpora", type=int, default=N_CORPORA)
    p.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=list(CONFIGS))
    p.add_argument("--workers", type=int, default=min(16, max(1, (os.cpu_count() or 2) - 2)))
    p.add_argument("--skip-sensitivity", action="store_true")
    p.add_argument("--skip-cross-process", action="store_true")
    p.add_argument("--output", type=Path, default=project_root / "results" / "invariants.json")
    p.add_argument("--counterexamples", type=Path,
                   default=project_root / "results" / "invariants_counterexamples.json")
    p.add_argument("--log-file", type=Path,
                   default=project_root / "results" / "invariants_output.txt")
    p.add_argument("--pending", nargs="*", default=sorted(PENDING_INVARIANTS),
                   choices=INV_KEYS, metavar="INV",
                   help="Invariants to report apart as pending, for a sha that predates "
                        "the rule they state (for example --pending I10 I11 I12).")
    p.add_argument("--overwrite", action="store_true",
                   help="Allow replacing existing output files (refused by default).")
    p.add_argument("--digest-only", action="store_true", help=argparse.SUPPRESS)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    indices = list(range(args.n_corpora))

    if args.digest_only:
        rows = run_parallel(indices, ["main"], False, True, args.workers)
        print(json.dumps({str(r["index"]): r["configs"]["main"]["digest"] for r in rows}))
        return

    config_names = list(args.configs)
    if "main" not in config_names:
        config_names.insert(0, "main")
    unknown = {n: sorted(k for k in CONFIGS[n]["overrides"] if k not in Config.model_fields)
               for n in config_names}
    skipped = {n: u for n, u in unknown.items() if u}
    if skipped:
        print(f"Skipping configurations whose switches BEAR {bear.__version__} lacks: {skipped}")
        config_names = [n for n in config_names if n not in skipped]
    pending = set(args.pending)
    if not args.overwrite:
        for path in (args.output, args.counterexamples, args.log_file):
            if path and str(path).strip() and Path(path).exists():
                raise SystemExit(f"{path} exists. Pass new --output, --counterexamples and "
                                 "--log-file paths, or --overwrite.")

    log_handle = None
    original_stdout = sys.stdout
    if args.log_file and str(args.log_file).strip():
        args.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = args.log_file.open("w", encoding="utf-8")
        sys.stdout = _Tee(original_stdout, log_handle)  # type: ignore[assignment]
    try:
        t0 = time.time()
        print(f"\n=== BEAR retrieval invariants: {args.n_corpora} random corpora ===\n")
        print(f"Corpora: {MIN_N}-{MAX_N} instructions, {CASES_PER_CORPUS} contexts each, "
              f"k = {K_VALUES[0]}..{K_VALUES[-1]}, default_top_k = {DEFAULT_TOP_K} "
              f"(pool base {3 * DEFAULT_TOP_K}), threshold = {THRESHOLD}, "
              f"priority_weight = {PRIORITY_WEIGHT}, mandatory_tags = {list(MANDATORY_TAGS)}")
        print(f"Configurations: {config_names}")
        print(f"Workers: {args.workers}")

        rows = run_parallel(indices, config_names, not args.skip_sensitivity, False, args.workers)
        sizes = [r["n"] for r in rows]
        print(f"\nRan in {time.time() - t0:.1f}s. Corpus sizes: mean {np.mean(sizes):.1f}, "
              f"range {min(sizes)}-{max(sizes)}")

        agg = aggregate(rows, config_names)
        sens = None if args.skip_sensitivity else aggregate_sensitivity(rows)

        # Cross-process determinism (I6, part d)
        cross = None
        if not args.skip_cross_process:
            n_cp = min(CROSS_PROCESS_CORPORA, args.n_corpora)
            env = dict(os.environ, PYTHONHASHSEED=CROSS_PROCESS_HASHSEED)
            proc = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--digest-only",
                 "--n-corpora", str(n_cp), "--workers", str(args.workers)],
                capture_output=True, text=True, env=env, check=False)
            try:
                other = json.loads(proc.stdout.strip().splitlines()[-1])
                ours = {str(r["index"]): r["configs"]["main"]["digest"] for r in rows[:n_cp]}
                mismatched = sorted(int(i) for i in ours if ours[i] != other.get(i))
                cross = {"corpora": n_cp, "pythonhashseed_other": CROSS_PROCESS_HASHSEED,
                         "pythonhashseed_this": os.environ.get("PYTHONHASHSEED", "(random)"),
                         "mismatched": mismatched}
            except Exception as e:  # noqa: BLE001
                cross = {"error": f"{e!r}", "stderr": proc.stderr[-2000:]}
            if isinstance(cross, dict) and cross.get("mismatched"):
                t = agg["main"]["invariants"]["I6"]
                t["cross_process_mismatches"] = len(cross["mismatched"])

        print_tables(agg, sens, config_names, pending)
        if cross is not None:
            print(f"\nCross-process determinism (main, {cross.get('corpora')} corpora, "
                  f"PYTHONHASHSEED {cross.get('pythonhashseed_this')} vs "
                  f"{cross.get('pythonhashseed_other')}): "
                  + (f"{len(cross['mismatched'])} digest mismatches" if "mismatched" in cross
                     else f"FAILED TO RUN: {cross.get('error')}"))

        # Counterexamples
        print("\n--- Minimal counterexamples ---")
        cexs = []
        for name in config_names:
            for inv in INV_KEYS:
                first = agg[name]["invariants"][inv]["first"]
                if first is None:
                    continue
                if inv in pending and name != "main":
                    # A pending invariant is expected to fail on a sha without the
                    # rule it states, so one shrunk example (main) is enough.
                    cexs.append({"config": name, "invariant": inv, "pending": True,
                                 "reproduced": None, "first": first})
                    continue
                corpus = generate_corpus(first["corpus"])
                case = case_for(name, generate_cases(corpus)[first["case"]])
                perm = perm_prefix(first["corpus"])
                ok, _ = violates(name, corpus["instructions"], case, first["k"], inv, perm)
                if not ok:
                    print(f"  {name} {inv}: first violation did not reproduce in isolation "
                          f"(corpus {first['corpus']}, case {first['case']}, k {first['k']})")
                    cexs.append({"config": name, "invariant": inv, "reproduced": False,
                                 "first": first})
                    continue
                ins, cs, kk = shrink(name, corpus["instructions"], case, first["k"], inv, perm=perm)
                cex = describe_counterexample(name, ins, cs, kk, inv, perm)
                cex["source"] = first
                cex["reproduced"] = True
                cex["pending"] = inv in pending
                cexs.append(cex)
                print(f"\n  [{name}] {inv} {INV_LABEL[inv]}"
                      f"{' (pending)' if inv in pending else ''}: corpus {first['corpus']}, "
                      f"case {first['case']}, k {first['k']} -> shrunk to "
                      f"{len(ins)} instructions, k={kk}")
                print(f"    context: {cex['context']}  query: {cex['query']!r}")
                for d in ins:
                    rel = {f: d[f] for f in ("required_tags", "scope_tags", "labels",
                                             "conflicts_with", "supersedes", "requires") if d[f]}
                    print(f"    {d['id']}: p={d['priority']} "
                          f"sim={cex['similarity_to_query'].get(d['id'])} {rel}")
                print(f"    output: {cex['output']}")
                print(f"    trace admitted: {cex['trace_admitted']}")
                print(f"    violation: {cex['violation']}")
        if not cexs:
            print("  none")

        result = {
            "parameters": {
                "n_corpora": args.n_corpora, "min_n": MIN_N, "max_n": MAX_N,
                "cases_per_corpus": CASES_PER_CORPUS, "k_values": K_VALUES,
                "default_top_k": DEFAULT_TOP_K, "threshold": THRESHOLD,
                "priority_weight": PRIORITY_WEIGHT, "mandatory_tags": list(MANDATORY_TAGS),
                "tag_vocab": TAG_VOCAB, "embed_dim": EMBED_DIM, "base_seed": BASE_SEED,
                "configs": {n: CONFIGS[n] for n in config_names},
            },
            "bear_version": getattr(bear, "__version__", "?"),
            "bear_path": bear.__file__,
            "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)"),
            "bear_install": bear_install_provenance(),
            "invariant_labels": INV_LABEL,
            "pending_invariants": sorted(pending),
            "results": agg,
            "sensitivity": sens,
            "cross_process_determinism": cross,
            "per_corpus": [
                {"index": r["index"], "n": r["n"],
                 "violations": {n: {inv: r["configs"][n]["inv"][inv]["outputs_violated"]
                                    for inv in INV_KEYS} for n in config_names}}
                for r in rows],
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as f:
            json.dump(result, f, indent=1, default=float)
        with args.counterexamples.open("w") as f:
            json.dump(cexs, f, indent=1, default=float)
        print(f"\nWrote {args.output}")
        print(f"Wrote {args.counterexamples}")
        print(f"\nElapsed: {time.time() - t0:.1f}s")
        print_repro_footer(extra={
            "n_corpora": args.n_corpora, "configs": config_names,
            "bear_path": bear.__file__,
            "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)")})
    finally:
        if log_handle is not None:
            sys.stdout = original_stdout
            log_handle.close()


if __name__ == "__main__":
    main()
