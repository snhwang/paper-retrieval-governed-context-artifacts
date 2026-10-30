"""Shared helpers for the WP0/WP4 reruns: provenance and the Nemotron backend.

Provenance records which BEAR produced a file. ``bear_source_sha`` comes from
the BEAR_SOURCE_SHA environment variable (set by run_wp0_v040.sh from the
export's EXPORTED_SHA), and ``bear_pkg_sha256`` hashes the imported package's
.py files, so the record can be checked against the export itself.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import sys
from pathlib import Path

NEMOTRON_URL = os.environ.get("NEMOTRON_URL", "http://localhost:8360")

# Identities read from the embedding service's /health, one per retriever
# built, so a service swapped mid-run would show up as two entries.
EMBEDDER_IDENTITIES: list[dict] = []


def bear_identity() -> dict:
    import bear
    pkg = Path(bear.__file__).resolve().parent
    h = hashlib.sha256()
    for p in sorted(pkg.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        h.update(p.relative_to(pkg).as_posix().encode())
        h.update(b"\0")
        h.update(p.read_bytes())
    return {
        "bear_version": getattr(bear, "__version__", "?"),
        "bear_path": str(pkg),
        "bear_source_sha": os.environ.get("BEAR_SOURCE_SHA", "(unset)"),
        "bear_pkg_sha256": h.hexdigest(),
    }


def _versions() -> dict:
    out = {"python": sys.version.split()[0], "platform": platform.platform()}
    for mod in ("numpy", "scipy", "torch", "transformers", "sentence_transformers"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:  # noqa: BLE001
            out[mod] = "(not importable)"
    try:
        import torch
        if torch.cuda.is_available():
            out["cuda_device"] = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001
        pass
    return out


def provenance(extra: dict | None = None) -> dict:
    rec = {
        "written_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "argv": sys.argv,
        **bear_identity(),
        "hooks": {k: v for k, v in os.environ.items() if k.startswith("WP0_")},
        "versions": _versions(),
    }
    if EMBEDDER_IDENTITIES:
        rec["embedder_identities"] = EMBEDDER_IDENTITIES
    if extra:
        rec.update(extra)
    return rec


def stamp_json(path: str | Path, extra: dict | None = None) -> None:
    """Add a ``_provenance`` key to a JSON object file, or write a sidecar."""
    path = Path(path)
    prov = provenance(extra)
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data["_provenance"] = prov
        path.write_text(json.dumps(data, indent=2, default=float), encoding="utf-8")
    else:
        side = path.with_name(path.name + ".provenance.json")
        side.write_text(json.dumps(prov, indent=2), encoding="utf-8")


def assert_not_hash(retriever, backend: str) -> None:
    """Fail when a dense backend quietly fell back to hash embeddings.

    BEAR 0.1.10 falls back to hash embeddings when a model fails to load (a
    CUDA error, say) and only logs it, so its results would look like a
    finished run. 0.4.0 raises instead. This makes both versions fail.
    """
    if backend in ("bm25", "hash", "nemotron"):
        return
    emb = getattr(retriever, "_embedder", None)
    mode = getattr(emb, "_mode", None)
    if mode is None and emb is not None and hasattr(emb, "_ensure_loaded"):
        emb._ensure_loaded()
        mode = getattr(emb, "_mode", None)
    if mode != "sentence_transformers":
        raise RuntimeError(f"backend {backend!r} is not running its model (embedder mode {mode!r})")


def patient_remote_embedder():
    """BEAR's RemoteEmbedder with a long timeout and retries.

    The service is shared with other jobs, and a 64-document batch of long
    ToolBench texts took up to 14 s under load, so the default 30 s timeout
    can trip. A retry resends the same batch, and the service returns the
    same vectors for the same batch, so retries do not change results.

    Batches hold at most NEMOTRON_BATCH texts (default 16), because the WP7
    grid shares the service (coordinator, 2026-10-30). A document's vector
    depends slightly on what it is batched with (up to 0.0023 in cosine
    terms), so the batch size is part of the configuration and is recorded,
    and the response cache is keyed on the exact batch.
    """
    import time

    from bear.remote_embedder import RemoteEmbedder

    cache_path = os.environ.get("WP0_NEMO_CACHE", "").strip()

    class _Patient(RemoteEmbedder):
        """Also caches responses (WP0_NEMO_CACHE=<sqlite file>), keyed on the
        served model id, the side (query or document) and the exact batch of
        texts. The service runs one request at a time under a lock and
        returned bit-identical vectors on repeats, so a hit is the vector a
        new request would get. Vectors are kept as float32, the type
        RemoteEmbedder.embed casts them to, so nothing is lost."""

        _db = None

        def _cache(self):
            if not cache_path:
                return None
            if _Patient._db is None:
                import sqlite3
                Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
                db = sqlite3.connect(cache_path, timeout=120)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS nemo (k TEXT PRIMARY KEY, shape TEXT, data BLOB)")
                db.commit()
                _Patient._db = db
            return _Patient._db

        def _post(self, texts, is_query):
            db = self._cache()
            key = None
            if db is not None:
                ident = self._identity or {}
                key = hashlib.sha256(json.dumps(
                    [ident.get("model_id"), ident.get("dim"), bool(is_query), list(texts)]
                ).encode("utf-8")).hexdigest()
                row = db.execute("SELECT shape, data FROM nemo WHERE k=?", (key,)).fetchone()
                if row is not None:
                    import numpy as np
                    shape = tuple(json.loads(row[0]))
                    return np.frombuffer(row[1], dtype=np.float32).reshape(shape).tolist()
            out = self._post_retry(texts, is_query)
            if db is not None and (self._identity or {}).get("model_id"):
                import numpy as np
                arr = np.asarray(out, dtype=np.float32)
                db.execute("INSERT OR IGNORE INTO nemo VALUES (?,?,?)",
                           (key, json.dumps(list(arr.shape)), arr.tobytes()))
                db.commit()
            return out

        def _post_retry(self, texts, is_query):
            for attempt in range(5):
                try:
                    return super()._post(texts, is_query)
                except RuntimeError as exc:
                    if "unreachable" not in str(exc) or attempt == 4:
                        raise
                    print(f"[nemotron] retry {attempt + 1} after: {exc}", flush=True)
                    time.sleep(15 * (attempt + 1))
            raise RuntimeError("unreachable")

    return _Patient(NEMOTRON_URL, timeout=float(os.environ.get("NEMOTRON_TIMEOUT", "600")),
                    batch_size=int(os.environ.get("NEMOTRON_BATCH", "16")))


def nemotron_retriever(corpus, *, priority_weight: float, threshold: float,
                       top_k: int, mandatory_tags: list[str] | None = None):
    """A BEAR retriever over model-server's Nemotron embedding service.

    BEAR selects a remote embedder by passing ``embedder=RemoteEmbedder(url)``
    to ``Retriever`` (the Hermes plugin's ``embedding: remote:<url>`` setting
    does the same, bear/integrations/hermes/plugin.py). The Config mirrors the
    in-process dense backends of eval_toolbench.py. No query prefix is set,
    because the service applies its own query and document handling from the
    ``kind`` field the embedder sends.
    """
    from bear import Config, EmbeddingBackend, Retriever

    emb = patient_remote_embedder()
    ident = emb.identity()
    if not ident.get("model_id"):
        raise RuntimeError(f"embedding service at {NEMOTRON_URL} did not identify itself: {ident}")
    config = Config(
        embedding_model=str(ident["model_id"]),
        embedding_backend=EmbeddingBackend.NUMPY,
        embedding_dim=int(ident.get("dim") or 2048),
        embedding_query_prefix="",
        embedding_passage_prefix="",
        priority_weight=priority_weight,
        default_threshold=threshold,
        default_top_k=top_k,
        mandatory_tags=mandatory_tags or [],
    )
    r = Retriever(corpus, config=config, embedder=emb)
    r.build_index()
    after = emb.identity()
    EMBEDDER_IDENTITIES.append({"at_build": ident, "after_index": after, "batch_size": emb.batch_size,
                                "n_instructions": len(corpus)})
    if after.get("model_id") != ident.get("model_id") or after.get("dim") != ident.get("dim"):
        raise RuntimeError(f"embedding service changed during indexing: {ident} -> {after}")
    return r
