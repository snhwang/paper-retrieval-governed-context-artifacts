"""Shared helpers for the TIST round-2 baselines and stress tests (WP2, WP5, WP6).

Every retrieval in these scripts goes through BEAR's public API
(``Retriever.retrieve_with_trace`` and ``bear.RetrievalTrace``). What this
module adds is the plumbing that lets the same retrieval run thousands of
times without recomputing embeddings, and without touching the GPU outside
one locked step.

Three phases, used by every script that imports this module:

  collect   Run BEAR once over every base condition with a recording
            embedder. It returns placeholder vectors and records each text
            BEAR asks to embed, so the text set is exactly what BEAR builds
            (its structured instruction and query headers included).
  embed     Embed the recorded texts with the real model, in batches, and
            store them on disk. This is the only step that loads a model or
            calls the embedding service. Run it under
            ``flock ~/tist-gpu.lock``.
  run       Retrieve with a strict cached embedder. A text that was not
            embedded in the embed phase raises, so a run can never fall back
            to computing on the GPU, and can never mix in an unrecorded text.

Caching is valid because a vector depends only on the model, the side
(query or document) and the text. BEAR applies the query prefix inside its
own Embedder, so the cache stores whatever BEAR's Embedder returns for that
text and side.

BM25 is lexical and needs no embedding. Its search is memoized per
(document texts, query, k) by ``enable_bm25_memo``, which is a pure-function
cache: it returns the exact list the backend computed the first time. It is
checked against uncached output by ``check_bm25_memo``.

Backends and their settings mirror the scripts that produced the published
rows. ToolBench and MetaTool use ``eval_toolbench.BACKEND_SPECS``. Pet Sim
uses ``eval_retrieval_backends.BACKEND_CONFIGS``. Nemotron is reached through
``bear.remote_embedder.RemoteEmbedder`` on port 8360.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

EVALS_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVALS_DIR.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))

import bear  # noqa: E402
from bear import Config, Context, Corpus, EmbeddingBackend, Retriever  # noqa: E402
from bear.retriever import Embedder  # noqa: E402

logging.basicConfig()
logging.getLogger("bear").setLevel(os.environ.get("TIST_BEAR_LOG", "ERROR"))

# 0.4.0 produced the committed results. 0.4.1 changes only the required-tags
# backfill (scored at similarity 0), which only a row-dropping search reaches.
# 0.4.2 makes BM25 return every row and breaks exact ties by id.
EXPECTED_BEAR_VERSIONS = ("0.4.0", "0.4.1", "0.4.2")
# Config fields set on every Config that make_config builds, such as one BEAR
# restore switch ({"restore_tie_order": True}), so a check can rerun an
# evaluation with one behavior restored. Empty for every committed run.
CONFIG_OVERRIDES: dict = {}
NEMOTRON_URL = os.environ.get("TIST_NEMOTRON_URL", "http://localhost:8360")
FORBIDDEN_PORTS = (":8355",)  # the shared LLM server, kept idle for other runs
EMB_CACHE_DIR = Path(os.environ.get(
    "TIST_EMB_CACHE", str(Path.home() / ".cache" / "tist-r2-embeddings")))

ALL_BACKENDS = ["bm25", "hash", "bge", "bge-m3", "qwen3-0.6b", "qwen3-4b", "nemotron"]
# Backends to load in float16 (Qwen3-4B always is). Set when the shared GPU
# has little headroom. Recorded in each store's settings.
FP16_BACKENDS = {b for b in os.environ.get("TIST_FP16_BACKENDS", "").split(",") if b}
CHAR_BUDGET = int(os.environ.get("TIST_CHAR_BUDGET", "16000"))
DENSE_BACKENDS = ["bge", "bge-m3", "qwen3-0.6b", "qwen3-4b", "nemotron"]
BACKEND_LABEL = {"bm25": "BM25", "hash": "Hash", "bge": "BGE-base", "bge-m3": "BGE-M3",
                 "qwen3-0.6b": "Qwen3-0.6B", "qwen3-4b": "Qwen3-4B",
                 "nemotron": "Nemotron-embed-1B"}

for _p in FORBIDDEN_PORTS:
    if _p in NEMOTRON_URL:
        raise SystemExit(f"Refusing to use {NEMOTRON_URL}: port {_p[1:]} must stay idle.")


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def bear_provenance() -> dict:
    """Version, path and source commit of the BEAR in use.

    The source commit is read from the install's direct_url (a local export
    named for its sha) and from BEAR_SOURCE_SHA when set.
    """
    info = {"bear_version": getattr(bear, "__version__", "?"), "bear_path": bear.__file__,
            "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)")}
    try:
        import importlib.metadata as md
        dist = md.distribution("bear")
        du = dist.read_text("direct_url.json")
        if du:
            url = json.loads(du).get("url")
            info["bear_direct_url"] = url
            # A local export records its commit in BEAR_GIT_SHA (or EXPORTED_SHA).
            if url and url.startswith("file://"):
                src = Path(url[len("file://"):])
                for name in ("BEAR_GIT_SHA", "EXPORTED_SHA"):
                    f = src / name
                    if f.exists():
                        info["bear_export_sha"] = f.read_text(encoding="utf-8").strip()
                        break
    except Exception:  # noqa: BLE001
        pass
    return info


def require_bear_040() -> None:
    """BEAR 0.4.0 (the committed runs) or 0.4.1 (the backfill fix), with the trace API."""
    v = getattr(bear, "__version__", "?")
    if v not in EXPECTED_BEAR_VERSIONS:
        raise SystemExit(f"BEAR {v} is installed. These evaluations expect one of "
                         f"{EXPECTED_BEAR_VERSIONS}.")
    if not hasattr(Retriever, "retrieve_with_trace") or not hasattr(bear, "RetrievalTrace"):
        raise SystemExit("This BEAR lacks the public trace API.")


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _toolbench_specs() -> dict:
    from eval_toolbench import BACKEND_SPECS
    return BACKEND_SPECS


def _petsim_specs() -> dict:
    from eval_retrieval_backends import BACKEND_CONFIGS
    return BACKEND_CONFIGS


def embedder_settings(backend: str, family: str) -> dict:
    """Model, dimension and prefixes for a dense or hash backend.

    ``family`` is "toolbench" (ToolBench and MetaTool), "petsim" or "cs"
    (procedural customer support, which uses BGE-base with BEAR's default
    prefix). Qwen3-4B is loaded in float16 so it fits the 15 GB budget on the
    shared GPU, where the published runs used the library default.
    """
    if backend == "hash":
        return {"model": "hash", "dim": 768, "query_prefix": "", "passage_prefix": "",
                "trust_remote_code": False, "model_kwargs": {}}
    if backend == "nemotron":
        return {"model": f"remote:{NEMOTRON_URL}", "dim": 2048, "query_prefix": "",
                "passage_prefix": "", "trust_remote_code": False, "model_kwargs": {}}
    if family == "petsim":
        key = {"qwen3-0.6b": "qwen3"}.get(backend, backend)
        c = _petsim_specs()[key]
        out = {"model": c["embedding_model"], "dim": c["embedding_dim"],
               "query_prefix": c["embedding_query_prefix"],
               "passage_prefix": c["embedding_passage_prefix"],
               "trust_remote_code": c.get("embedding_trust_remote_code", False),
               "model_kwargs": dict(c.get("embedding_model_kwargs", {}))}
    elif family == "cs":
        if backend != "bge":
            raise ValueError("The procedural corpus is run on BGE-base only.")
        out = {"model": "BAAI/bge-base-en-v1.5", "dim": 768,
               "query_prefix": "Represent this sentence for retrieving relevant documents: ",
               "passage_prefix": "", "trust_remote_code": False, "model_kwargs": {}}
    else:
        s = _toolbench_specs()[backend]
        out = {"model": s["model"], "dim": s["dim"], "query_prefix": s["query_prefix"],
               "passage_prefix": "", "trust_remote_code": s.get("trust_remote_code", False),
               "model_kwargs": dict(s.get("model_kwargs", {}))}
    if backend == "qwen3-4b" or backend in FP16_BACKENDS:
        out["model_kwargs"]["torch_dtype"] = "float16"
    return out


def make_config(backend: str, family: str, *, k: int, threshold: float,
                priority_weight: float, mandatory_tags: Iterable[str] = (),
                retrieval_pool: int | None = None) -> Config:
    common = dict(priority_weight=priority_weight, default_threshold=threshold,
                  default_top_k=k, mandatory_tags=list(mandatory_tags),
                  retrieval_pool=retrieval_pool, **CONFIG_OVERRIDES)
    if backend == "bm25":
        return Config(embedding_model="bm25", embedding_backend=EmbeddingBackend.BM25,
                      embedding_dim=0, embedding_query_prefix="", embedding_passage_prefix="",
                      **common)
    s = embedder_settings(backend, family)
    return Config(embedding_model=s["model"], embedding_backend=EmbeddingBackend.NUMPY,
                  embedding_dim=s["dim"], embedding_query_prefix=s["query_prefix"],
                  embedding_passage_prefix=s["passage_prefix"],
                  embedding_trust_remote_code=s["trust_remote_code"],
                  embedding_model_kwargs=s["model_kwargs"], **common)


# ---------------------------------------------------------------------------
# Embedders
# ---------------------------------------------------------------------------

class RecordingEmbedder:
    """Records every text BEAR asks to embed and returns placeholder vectors."""

    model_name = "recording"

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim
        self.queries: dict[str, None] = {}
        self.docs: dict[str, None] = {}

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        bucket = self.queries if is_query else self.docs
        for t in texts:
            bucket.setdefault(t, None)
        return np.ones((len(texts), self.dim), dtype=np.float32)

    def embed_single(self, text: str, is_query: bool = False) -> np.ndarray:
        return self.embed([text], is_query=is_query)[0]


class EmbeddingStore:
    """Vectors for one backend and one text family, persisted on disk.

    Two files per store: ``<name>.json`` (texts, model, settings) and
    ``<name>.npz`` (``q`` and ``d`` float32 matrices in the same order).
    """

    def __init__(self, backend: str, family: str, name: str | None = None) -> None:
        self.backend = backend
        self.family = family
        self.name = name or f"{family}__{backend}"
        self.json_path = EMB_CACHE_DIR / f"{self.name}.json"
        self.npz_path = EMB_CACHE_DIR / f"{self.name}.npz"
        self.q: dict[str, np.ndarray] = {}
        self.d: dict[str, np.ndarray] = {}
        self.meta: dict = {}
        self.load()

    def load(self) -> None:
        if not (self.json_path.exists() and self.npz_path.exists()):
            return
        meta = json.loads(self.json_path.read_text(encoding="utf-8"))
        with np.load(self.npz_path) as z:
            qv, dv = z["q"], z["d"]
        self.q = dict(zip(meta["query_texts"], qv))
        self.d = dict(zip(meta["doc_texts"], dv))
        self.meta = {k: v for k, v in meta.items() if k not in ("query_texts", "doc_texts")}

    def save(self) -> None:
        EMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        qt, dt = list(self.q), list(self.d)
        dim = next(iter(self.q.values()), next(iter(self.d.values()), np.zeros(1))).shape[-1]
        qv = np.stack([self.q[t] for t in qt]).astype(np.float32) if qt else np.zeros((0, dim), np.float32)
        dv = np.stack([self.d[t] for t in dt]).astype(np.float32) if dt else np.zeros((0, dim), np.float32)
        tmp = self.npz_path.with_name(self.npz_path.stem + ".tmp.npz")
        np.savez(tmp, q=qv, d=dv)
        os.replace(tmp, self.npz_path)
        meta = dict(self.meta)
        meta.update(query_texts=qt, doc_texts=dt)
        self.json_path.write_text(json.dumps(meta), encoding="utf-8")

    def missing(self, queries: Iterable[str], docs: Iterable[str]) -> tuple[list[str], list[str]]:
        mq = [t for t in dict.fromkeys(queries) if t not in self.q]
        md = [t for t in dict.fromkeys(docs) if t not in self.d]
        return mq, md

    def fill(self, queries: Iterable[str], docs: Iterable[str],
             char_budget: int | None = None, max_batch: int = 64) -> dict:
        """Embed whatever is missing with the real model. Loads the model only if needed.

        Texts go longest first in batches sized to a character budget, so a
        batch of long documents stays small. BEAR's Embedder encodes a list of
        64 or fewer texts as one batch, and eager attention grows with the
        square of the longest text in it: 32 ToolBench documents of ~3,000
        tokens took about 18 GB in one batch on Qwen3-0.6B.
        """
        char_budget = char_budget or CHAR_BUDGET
        mq, md = self.missing(queries, docs)
        stats = {"backend": self.backend, "family": self.family,
                 "new_queries": len(mq), "new_docs": len(md),
                 "cached_queries": len(self.q), "cached_docs": len(self.d)}
        if not mq and not md:
            return stats
        want = embedder_settings(self.backend, self.family) if self.backend not in ("bm25", "nemotron") else None
        have = self.meta.get("settings")
        if want is not None and have is not None and have != want and (self.q or self.d):
            raise SystemExit(f"{self.name}: stored vectors were made with {have}, "
                             f"not {want}. Use a new store rather than mixing them.")
        t0 = time.time()
        last_save = time.time()
        inner = real_embedder(self.backend, self.family)
        for side, todo, bucket in ((True, mq, self.q), (False, md, self.d)):
            order = sorted(todo, key=len, reverse=True)
            i = done = 0
            while i < len(order):
                n = max(1, min(max_batch, char_budget // max(len(order[i]), 1)))
                part = order[i:i + n]
                i += n
                for attempt in range(5):
                    try:
                        vecs = inner.embed(part, is_query=side)
                        break
                    except RuntimeError as exc:
                        # A shared embedding service can stall under load.
                        if self.backend != "nemotron" or attempt == 4:
                            raise
                        wait = 15 * 2 ** attempt
                        print(f"    [{self.name}] {exc}; retrying in {wait}s", flush=True)
                        time.sleep(wait)
                for t, v in zip(part, vecs):
                    bucket[t] = np.asarray(v, dtype=np.float32)
                done += len(part)
                if time.time() - last_save > 120:
                    if want is not None:
                        self.meta["settings"] = want
                    self.save()  # keep progress if a later batch fails
                    last_save = time.time()
                    print(f"    [{self.name}] {'queries' if side else 'docs'} {done}/{len(order)}",
                          flush=True)
        s = embedder_settings(self.backend, self.family) if self.backend != "bm25" else {}
        self.meta.update(backend=self.backend, family=self.family, settings=s,
                         embedded_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         **({"service_identity": inner.identity()}
                            if hasattr(inner, "identity") else {}))
        self.save()
        stats["seconds"] = round(time.time() - t0, 1)
        try:
            import torch
            if torch.cuda.is_available():
                stats["cuda_max_reserved_gib"] = round(torch.cuda.max_memory_reserved() / 2**30, 2)
        except Exception:  # noqa: BLE001
            pass
        return stats


class CachedEmbedder:
    """Serves vectors from an EmbeddingStore. A miss raises."""

    def __init__(self, store: EmbeddingStore) -> None:
        self.store = store
        self.model_name = f"cached:{store.name}"
        self.dim = None

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        bucket = self.store.q if is_query else self.store.d
        try:
            return np.stack([bucket[t] for t in texts])
        except KeyError as exc:
            raise RuntimeError(
                f"Text not in embedding store {self.store.name} "
                f"({'query' if is_query else 'doc'}): {str(exc)[:120]!r}. "
                "Run the embed phase first.") from None

    def embed_single(self, text: str, is_query: bool = False) -> np.ndarray:
        return self.embed([text], is_query=is_query)[0]


GPU_CAP_GIB = float(os.environ.get("TIST_GPU_CAP_GIB", "13"))
_CAPPED = False


def cap_cuda_memory() -> None:
    """Cap this process's CUDA allocator at min(13 GiB, free - 1 GiB), or refuse.

    Mirrors the WP0 runner's gate, so a step never pushes the shared card
    over its budget. Does nothing when CUDA is hidden.
    """
    global _CAPPED
    if _CAPPED:
        return
    try:
        import torch
    except ImportError:
        return
    if not torch.cuda.is_available():
        return
    free, total = torch.cuda.mem_get_info()
    cap = min(GPU_CAP_GIB * 2**30, free - 2**30)
    if cap < 2 * 2**30:
        raise SystemExit(f"Only {free / 2**30:.1f} GiB of VRAM free. Not starting a GPU step.")
    torch.cuda.set_per_process_memory_fraction(cap / total)
    print(f"    CUDA allocator capped at {cap / 2**30:.1f} GiB "
          f"({free / 2**30:.1f} GiB free of {total / 2**30:.1f})", flush=True)
    _CAPPED = True


def real_embedder(backend: str, family: str):
    """The embedder BEAR itself would build for this backend (or the remote one)."""
    if backend == "nemotron":
        from bear.remote_embedder import RemoteEmbedder
        return RemoteEmbedder(NEMOTRON_URL, batch_size=64, timeout=180.0)
    cap_cuda_memory()
    s = embedder_settings(backend, family)
    model_kwargs = dict(s["model_kwargs"])
    if model_kwargs.get("torch_dtype") == "float16":
        import torch
        model_kwargs["torch_dtype"] = torch.float16
    return Embedder(model_name=s["model"], dim=s["dim"], query_prefix=s["query_prefix"],
                    passage_prefix=s["passage_prefix"], trust_remote_code=s["trust_remote_code"],
                    model_kwargs=model_kwargs, query_cache=0,
                    _suppress_hash_warning=(backend == "hash"))


def build_retriever(corpus: Corpus, backend: str, family: str, config: Config,
                    embedder: Any = None) -> Retriever:
    """A built retriever. Dense backends need ``embedder`` (cached or recording)."""
    if backend == "bm25":
        r = Retriever(corpus, config=config)
    else:
        if embedder is None:
            raise ValueError("pass a CachedEmbedder or RecordingEmbedder for dense backends")
        r = Retriever(corpus, config=config, embedder=embedder)
    r.build_index()
    return r


def store_for(backend: str, family: str) -> EmbeddingStore | None:
    return None if backend == "bm25" else EmbeddingStore(backend, family)


def record_texts(conditions: list[tuple[Corpus, list[tuple[str, Context]], Config]],
                 top_k: int) -> tuple[list[str], list[str]]:
    """Every (query, doc) text BEAR embeds for these conditions. Backend-free."""
    rec = RecordingEmbedder()
    for corpus, qs, cfg in conditions:
        r = Retriever(corpus, config=cfg, embedder=rec)
        r.build_index()
        for q, ctx in qs:
            r.retrieve(q, ctx, top_k=top_k)
    return list(rec.queries), list(rec.docs)


def save_texts(path: Path, queries: list[str], docs: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"queries": queries, "docs": docs}), encoding="utf-8")


def load_texts(path: Path) -> tuple[list[str], list[str]]:
    d = json.loads(path.read_text(encoding="utf-8"))
    return d["queries"], d["docs"]


# ---------------------------------------------------------------------------
# BM25 memo
# ---------------------------------------------------------------------------

_BM25_MEMO: dict = {}


def enable_bm25_memo() -> None:
    """Memoize BM25 search per (document texts, query, k). Exact, not approximate."""
    from bear.backends.embeddings.bm25_backend import BM25Backend
    if getattr(BM25Backend, "_tist_memo", False):
        return
    orig_build = BM25Backend.build_bm25_index
    orig_search = BM25Backend.search_bm25

    def build(self, texts, *a, **kw):
        out = orig_build(self, texts, *a, **kw)
        self._tist_fp = hashlib.sha1("\x1e".join(texts).encode("utf-8")).hexdigest()
        return out

    def search(self, query, top_k):
        key = (getattr(self, "_tist_fp", None), query, top_k)
        hit = _BM25_MEMO.get(key)
        if hit is None:
            res = orig_search(self, query, top_k)
            idx = np.fromiter((i for i, _ in res), dtype=np.int64, count=len(res))
            sc = np.fromiter((s for _, s in res), dtype=np.float64, count=len(res))
            _BM25_MEMO[key] = (idx, sc)
            return res
        idx, sc = hit
        return list(zip(idx.tolist(), sc.tolist()))

    BM25Backend.build_bm25_index = build
    BM25Backend.search_bm25 = search
    BM25Backend._tist_memo = True
    BM25Backend._tist_orig_search = orig_search


def check_bm25_memo(corpus: Corpus, queries: list[tuple[str, Context]], config: Config,
                    top_k: int, n: int = 50) -> int:
    """Count queries whose memoized BM25 result differs from a fresh one (want 0)."""
    from bear.backends.embeddings.bm25_backend import BM25Backend
    enable_bm25_memo()
    r = build_retriever(corpus, "bm25", "toolbench", config)
    bad = 0
    for q, ctx in queries[:n]:
        a = [(s.id, round(s.final_score, 12)) for s in r.retrieve(q, ctx, top_k=top_k)]
        b = [(s.id, round(s.final_score, 12)) for s in r.retrieve(q, ctx, top_k=top_k)]
        # third call bypasses the memo entirely
        memo_search = BM25Backend.search_bm25
        BM25Backend.search_bm25 = BM25Backend._tist_orig_search
        try:
            c = [(s.id, round(s.final_score, 12)) for s in r.retrieve(q, ctx, top_k=top_k)]
        finally:
            BM25Backend.search_bm25 = memo_search
        bad += int(not (a == b == c))
    return bad


# ---------------------------------------------------------------------------
# Metrics and statistics
# ---------------------------------------------------------------------------

def recall(got: Iterable[str], expected: set[str]) -> float:
    return len(set(got) & expected) / len(expected) if expected else 0.0


def ndcg(ordered: list[str], expected: set[str], k: int) -> float:
    if not expected:
        return 0.0
    dcg = sum(1.0 / np.log2(r + 2) for r, x in enumerate(ordered[:k]) if x in expected)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(expected), k)))
    return float(dcg / idcg) if idcg else 0.0


def prf(got: set[str], expected: set[str]) -> tuple[float, float, float]:
    tp = len(got & expected)
    p = tp / len(got) if got else 0.0
    r = tp / len(expected) if expected else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


LARGE_N = 2000  # above this, bootstrap the mean through value counts (same distribution)


def multinomial_boot_means(values, n_boot: int = 10_000, seed: int = 42) -> np.ndarray:
    """Bootstrap means of ``values`` drawn as multinomial counts over its distinct values.

    Resampling n items with replacement and averaging is the same as drawing
    how many times each distinct value is picked (multinomial with the
    observed frequencies) and averaging. Per-query retrieval metrics take few
    distinct values, so this is exact in distribution and avoids an
    n_boot x n index matrix (10,000 x 21,111 for MetaTool).
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    levels, counts = np.unique(v, return_counts=True)
    rng = np.random.default_rng(seed)
    draws = rng.multinomial(len(v), counts / len(v), size=n_boot)
    return draws @ levels / len(v)


def ci_summary(values, n_boot: int = 10_000) -> dict:
    v = np.asarray(values, dtype=float)
    if len(v) > LARGE_N:
        boots = multinomial_boot_means(v, n_boot)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        return {"mean": float(v.mean()), "ci": [float(lo), float(hi)],
                "sd": float(v.std(ddof=1)), "n": int(len(v)), "bootstrap": "multinomial"}
    from stat_utils import bootstrap_ci
    c = bootstrap_ci(v, n_boot=n_boot)
    return {"mean": c["point_estimate"], "ci": [c["ci_lower"], c["ci_upper"]],
            "sd": c["std"], "n": c["n"], "bootstrap": "resample"}


def _paired_bootstrap(a: np.ndarray, b: np.ndarray, n_boot: int) -> dict:
    if len(a) <= LARGE_N:
        from stat_utils import paired_bootstrap
        return paired_bootstrap(a, b, n_boot=n_boot)
    diff = a - b
    boots = multinomial_boot_means(diff, n_boot)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p = 2.0 * min((boots <= 0).mean(), (boots >= 0).mean())
    return {"delta": float(diff.mean()), "ci_lower": float(lo), "ci_upper": float(hi),
            "p_value": float(min(max(p, 1.0 / n_boot), 1.0)), "n": int(len(diff))}


def paired_summary(a, b, n_boot: int = 10_000) -> dict:
    """Paired bootstrap of mean(a - b), paired Cohen's d, Wilcoxon and paired t."""
    from scipy.stats import ttest_rel, wilcoxon
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    pb = _paired_bootstrap(a, b, n_boot)
    diff = a - b
    sd = diff.std(ddof=1) if len(diff) > 1 else 0.0
    # Undefined when every difference is the same (sd 0 up to float noise).
    d = float(diff.mean() / sd) if sd > 1e-12 else None
    nz = diff[diff != 0]
    if len(nz) >= 5:
        w_stat, w_p = wilcoxon(nz)
        w = {"W": float(w_stat), "p": float(w_p), "n_nonzero": int(len(nz))}
    else:
        w = {"W": None, "p": None, "n_nonzero": int(len(nz))}
    if sd > 1e-12:
        t_stat, t_p = ttest_rel(a, b)
        t = {"t": float(t_stat), "p": float(t_p)}
    else:
        t = {"t": None, "p": 1.0 if diff.mean() == 0 else 0.0}
    return {"delta": pb["delta"], "ci": [pb["ci_lower"], pb["ci_upper"]],
            "p_bootstrap": pb["p_value"], "cohens_d_paired": d, "wilcoxon": w,
            "paired_t": t, "n": pb["n"]}


def mcnemar_summary(a, b) -> dict:
    from stat_utils import mcnemar
    return mcnemar(np.asarray(a, dtype=int), np.asarray(b, dtype=int))


def clopper_pearson(x: int, n: int, alpha: float = 0.05) -> list[float]:
    from scipy import stats
    if n == 0:
        return [float("nan"), float("nan")]
    lo = 0.0 if x == 0 else float(stats.beta.ppf(alpha / 2, x, n - x + 1))
    hi = 1.0 if x == n else float(stats.beta.ppf(1 - alpha / 2, x + 1, n - x))
    return [lo, hi]


def fmt(s: dict, p: int = 3) -> str:
    return f"{s['mean']:.{p}f} [{s['ci'][0]:.{p}f}, {s['ci'][1]:.{p}f}]"


def fmt_delta(s: dict, p: int = 3) -> str:
    pv = s["p_bootstrap"]
    d = s["cohens_d_paired"]
    return (f"{s['delta']:+.{p}f} [{s['ci'][0]:+.{p}f}, {s['ci'][1]:+.{p}f}] "
            f"p={pv:.4f} d={'n/a' if d is None else format(d, '+.2f')}")


class Tee:
    """Write stdout to the console and a log file."""

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


def refuse_overwrite(*paths: Path) -> None:
    """Stop before clobbering a result file that already exists."""
    for p in paths:
        if p.exists():
            raise SystemExit(f"{p} exists. Results are never overwritten. "
                             "Pass a new --output/--log-file or move the old file.")


def json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    raise TypeError(type(o))
