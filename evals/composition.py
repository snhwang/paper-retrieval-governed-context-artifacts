"""Composition layer: BEAR + external systems, no changes to BEAR core.

This module demonstrates the paper's composition claim as working code. BEAR
governs candidate-set construction (hard gate, priority weighting, mandatory
injection, relationships) and external systems refine the governed candidate
set downstream. Everything here goes through BEAR's public API
(``Retriever.retrieve``); the BEAR release itself is unmodified, pinned at the
version the paper reports (v0.1.10).

Two pieces:

``CrossEncoderReranker``
    Wraps a released cross-encoder (default ``BAAI/bge-reranker-base``, the
    reranking component shipped in LlamaIndex and LangChain stacks) as a
    post-stage: it reorders (query, text) candidate pairs and cannot admit an
    item the governed first stage did not surface.

``ComposedRetriever``
    Drop-in wrapper with the same ``retrieve(query, context, top_k)`` shape as
    a BEAR retriever. It over-fetches the governed candidate set to
    ``overfetch`` depth, applies the post-stage, and cuts to ``top_k``. With
    ``stage=None`` it degrades to plain governed retrieval.

Used by ``eval_reranker_composition.py``, which measures the four-arm
comparison reported in the paper (Table 21): the composed system is the
strongest measured on ToolBench (Recall@5 0.742 versus 0.688 governed alone),
and on Pet Sim, where the gate already reduces the corpus to ~11 candidates at
recall 0.997, reranking subtracts. ``min_candidates`` exists for deployments
that want to skip the reranker in that regime; the evals leave it at 0 so the
measured arms always rerank.

Example::

    from bear import Context
    from composition import CrossEncoderReranker, ComposedRetriever

    stage = CrossEncoderReranker()                  # released reranker
    composed = ComposedRetriever(bear_retriever, stage, texts, overfetch=50)
    results = composed.retrieve("query text", Context(tags=[...]), top_k=5)

Beyond the measured reranker, two further adapters show how the mechanisms of
other cited methods attach to the governed candidate set. Neither claims to
reproduce the cited system; each demonstrates that the mechanism composes with
governance instead of replacing it. Both are deterministic and dependency-free.

``OutcomeReweightStage``
    Outcome-aware reordering in the spirit of OATS (Chen et al.): blend the
    governed rank with a per-item prior derived from historical success. OATS
    folds the signal into the embedding; here it stays outside the vector
    space, applied to the governed candidate list.

``GroupBoostStage``
    Hierarchy-aware reordering in the spirit of Tool-to-Agent Retrieval and
    Agent-as-a-Graph (Lumer et al., Nizar et al.): candidates that share a
    parent (a ToolBench tool owning several APIs, an agent owning tools) are
    promoted together, keyed by the parent's best-ranked member.

Two remaining shapes from the literature fit the same ``PostStage`` interface
and are intentionally not implemented here: an iterative LLM loop that
re-queries per sub-task (ToolReAGt) and an execution-based validator that
filters candidates by sandboxed trial (GRETEL). Both consume an upstream
candidate set, which is exactly what the governed first stage supplies.
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

# A post-stage maps (query, ordered candidate ids) -> reordered candidate ids.
PostStage = Callable[[str, Sequence[str]], list[str]]


class CrossEncoderReranker:
    """A released cross-encoder as a post-stage over governed candidates.

    Scores each (query, document text) pair and reorders by descending score.
    Ties keep the governed order (stable argsort), so the stage is
    deterministic given the same candidate list.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base",
                 device: str | None = None, batch_size: int = 64):
        from sentence_transformers import CrossEncoder  # heavy import, local

        if device is None:
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = CrossEncoder(model_name, device=device)
        self._texts: dict[str, str] = {}

    def set_texts(self, texts: dict[str, str]) -> None:
        """Provide the id -> document text mapping candidates are scored on."""
        self._texts = texts

    def __call__(self, query: str, candidate_ids: Sequence[str]) -> list[str]:
        if not candidate_ids:
            return []
        pairs = [(query, self._texts.get(cid, "")) for cid in candidate_ids]
        scores = self._model.predict(pairs, batch_size=self.batch_size,
                                     show_progress_bar=False)
        order = np.argsort(-np.asarray(scores, dtype=float), kind="stable")
        return [candidate_ids[i] for i in order]


class OutcomeReweightStage:
    """Outcome-aware reordering of governed candidates (OATS-inspired).

    ``priors`` maps item id to a success prior in [0, 1] (e.g., the fraction
    of historical queries the item served successfully). Candidates are
    reordered by ``(1 - weight) * rank_score + weight * prior``, where
    rank_score decays linearly with governed position. Items without a prior
    fall back to 0.5 (no evidence either way). Weight 0 is a no-op.

    Where OATS folds the outcome signal into the tool's dense embedding, this
    stage keeps it outside the vector space, applied after governance. The
    governance-native endpoint of the same idea is updating the declared
    priority field itself, which the paper leaves to future work.
    """

    def __init__(self, priors: dict[str, float], weight: float = 0.3):
        if not 0.0 <= weight <= 1.0:
            raise ValueError("weight must be in [0, 1]")
        self.priors = priors
        self.weight = weight

    def __call__(self, query: str, candidate_ids: Sequence[str]) -> list[str]:
        n = len(candidate_ids)
        if n == 0 or self.weight == 0.0:
            return list(candidate_ids)
        w = self.weight
        scored = [((1.0 - w) * (1.0 - pos / n) + w * self.priors.get(cid, 0.5), pos, cid)
                  for pos, cid in enumerate(candidate_ids)]
        scored.sort(key=lambda t: (-t[0], t[1]))  # stable: governed order breaks ties
        return [cid for _, _, cid in scored]


class GroupBoostStage:
    """Hierarchy-aware reordering of governed candidates (Tool-to-Agent-inspired).

    ``group_of`` maps an item id to its parent key (for ToolBench ids of the
    form ``toolbench/<category>/<tool>/<api>``, the owning tool). Candidates
    are reordered by their group's best governed rank, keeping the governed
    order within each group, so siblings of a strongly-matched parent surface
    together. Confined to the governed candidate set by construction: the
    stage promotes admitted siblings but cannot admit anything the gate
    excluded.
    """

    def __init__(self, group_of: Callable[[str], str]):
        self.group_of = group_of

    def __call__(self, query: str, candidate_ids: Sequence[str]) -> list[str]:
        best: dict[str, int] = {}
        pos_of: dict[str, int] = {}
        for pos, cid in enumerate(candidate_ids):
            pos_of[cid] = pos
            g = self.group_of(cid)
            if g not in best:
                best[g] = pos
        return sorted(candidate_ids,
                      key=lambda cid: (best[self.group_of(cid)], pos_of[cid]))


def toolbench_parent_tool(item_id: str) -> str:
    """Parent key for ToolBench ids: ``toolbench/<category>/<tool>/<api>``."""
    parts = item_id.split("/")
    return "/".join(parts[:3]) if len(parts) >= 4 else item_id


class ComposedRetriever:
    """BEAR retriever + optional post-stage, same retrieve() shape as BEAR.

    Governance runs first and is authoritative: the post-stage sees only the
    governed candidate set, so gate exclusions and mandatory injections are
    preserved by construction. The stage only changes ordering within it.
    """

    def __init__(self, retriever, stage: PostStage | None,
                 texts: dict[str, str] | None = None,
                 overfetch: int = 50, min_candidates: int = 0):
        self.retriever = retriever
        self.stage = stage
        self.overfetch = overfetch
        # Skip the stage when the governed set is at or below this size.
        # The Pet Sim boundary condition (Table 21): with ~11 candidates at
        # recall 0.997 there is nothing useful left to reorder. 0 = always run.
        self.min_candidates = min_candidates
        if texts is not None and hasattr(stage, "set_texts"):
            stage.set_texts(texts)

    def retrieve_ids(self, query: str, context, top_k: int) -> list[str]:
        """Ordered ids after governance and (optionally) the post-stage."""
        deep = self.retriever.retrieve(query, context, top_k=self.overfetch)
        ids = [d.id for d in deep]
        if self.stage is not None and len(ids) > self.min_candidates:
            ids = self.stage(query, ids)
        return ids[:top_k]

    def candidate_ids(self, query: str, context) -> list[str]:
        """The governed candidate set at over-fetch depth (pre-stage)."""
        deep = self.retriever.retrieve(query, context, top_k=self.overfetch)
        return [d.id for d in deep]
