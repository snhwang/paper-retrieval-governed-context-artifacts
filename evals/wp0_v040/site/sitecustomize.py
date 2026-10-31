"""Opt-in process hooks for the WP0/WP4 reruns on BEAR 0.4.0.

Python imports this module at startup when its directory is on PYTHONPATH.
Every hook is off unless its environment variable is set, so with none set
the eval scripts run exactly as committed.

WP0_QWEN4B_DTYPE=bfloat16
    Load Qwen/Qwen3-Embedding-4B in this dtype. sentence-transformers loads
    it in fp32 by default, and the fp32 weights alone are about 16.1 GB, which
    is above the 15 GB VRAM budget of the shared GPU. Only this one model is
    affected. Every other model loads as before.

WP0_SHARE_MODELS=1 (WP0_SHARE_QWEN4B=1 is an older name for the same switch)
    Reuse one instance for every SentenceTransformer built with exactly the
    same arguments (the most recent one only). Some scripts build a fresh
    retriever, and so a fresh model, for every condition, and while the next
    one loads the last one is still referenced, so two copies would sit in
    memory. With the VRAM left on the shared GPU that is enough to run out.
    Weights are read-only at inference, so the outputs are the same. Another
    caller that builds the same model with other arguments (LlamaIndex passes
    its own) gets its own instance.

WP0_GPU_CAP_GIB=13
    Cap PyTorch's CUDA caching allocator for this process
    (torch.cuda.set_per_process_memory_fraction). An allocation past the cap
    raises an out-of-memory error instead of growing into memory the model
    servers need.

WP0_REPORT_VRAM=<path>
    At exit, append this process's peak allocated and reserved CUDA memory to
    <path>, one JSON line per process.

WP0_EMB_CACHE=<dir>
    Cache SentenceTransformer.encode results in <dir>/emb.sqlite, keyed on the
    model (name, device, dtype, CPU thread count), the exact input texts and
    every encode argument. A hit returns a copy of the array an identical
    earlier call returned. Both BEAR 0.1.10 and 0.4.0 embed through
    encode(texts, convert_to_numpy=True, batch_size=...), so with the cache
    the two versions see bit-identical vectors, and a query embedded for one
    condition is not recomputed for the next. Used for CPU runs.
"""

from __future__ import annotations

import os
import sys

_DTYPE = os.environ.get("WP0_QWEN4B_DTYPE", "").strip()
_SHARE = (os.environ.get("WP0_SHARE_MODELS", "").strip() not in ("", "0")
          or os.environ.get("WP0_SHARE_QWEN4B", "").strip() not in ("", "0"))
_CAP = os.environ.get("WP0_GPU_CAP_GIB", "").strip()
_REPORT = os.environ.get("WP0_REPORT_VRAM", "").strip()

_Q4B = "Qwen3-Embedding-4B"


def _say(msg: str) -> None:
    print(f"[wp0-site] {msg}", file=sys.stderr, flush=True)


def _install_st_patch() -> None:
    import torch
    import sentence_transformers as st

    cls = st.SentenceTransformer
    if getattr(cls, "_wp0_patched", False):
        return
    orig_init = cls.__init__
    shared: dict = {}

    def _name(args, kwargs):
        if args:
            return args[0]
        return kwargs.get("model_name_or_path")

    def _is_q4b(name) -> bool:
        return isinstance(name, str) and name.rstrip("/").endswith(_Q4B)

    def _key(name, args, kwargs):
        rest = {k: v for k, v in kwargs.items() if k != "model_name_or_path"}
        return (name, repr(args[1:]), repr(sorted((k, repr(v)) for k, v in rest.items())))

    def _new(klass, *args, **kwargs):
        name = _name(args, kwargs)
        if _SHARE and isinstance(name, str):
            inst = shared.get(_key(name, args, kwargs))
            if inst is not None:
                _say(f"reusing shared {name}")
                return inst
        return object.__new__(klass)

    def _init(self, *args, **kwargs):
        if self.__dict__.get("_wp0_ready", False):
            return
        name = _name(args, kwargs)
        key = _key(name, args, kwargs) if isinstance(name, str) else None
        if _DTYPE and _is_q4b(name):
            mk = dict(kwargs.get("model_kwargs") or {})
            mk.setdefault("torch_dtype", getattr(torch, _DTYPE))
            kwargs["model_kwargs"] = mk
            _say(f"loading {name} with torch_dtype={_DTYPE}")
        orig_init(self, *args, **kwargs)
        self.__dict__["_wp0_ready"] = True
        if _SHARE and key is not None:
            # Keep the WP0_SHARE_KEEP most recent models (default 1). With 1,
            # a small model loaded in between (ITR's encoder) evicts
            # Qwen3-4B, and the next Qwen3-4B load makes a second 16 GB copy
            # while the first is still referenced (decomposed_q4b, rc 143 at
            # the 20G cap, 2026-10-30). Steps like that run with 2.
            shared.pop(key, None)
            shared[key] = self
            while len(shared) > max(1, int(os.environ.get("WP0_SHARE_KEEP", "1") or 1)):
                shared.pop(next(iter(shared)))

    cls.__new__ = staticmethod(_new)
    cls.__init__ = _init
    cls._wp0_patched = True


def _install_cap() -> None:
    import torch
    if not torch.cuda.is_available():
        return
    total = torch.cuda.get_device_properties(0).total_memory
    frac = min(1.0, float(_CAP) * 2**30 / total)
    torch.cuda.set_per_process_memory_fraction(frac, 0)
    _say(f"CUDA allocator capped at {_CAP} GiB ({frac:.4f} of {total / 2**30:.1f} GiB)")


def _install_report() -> None:
    import atexit
    import json
    import time

    def _dump():
        try:
            import torch
            if not torch.cuda.is_available() or not torch.cuda.is_initialized():
                return
            rec = {
                "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "argv": sys.argv,
                "max_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
                "max_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
            }
            with open(_REPORT, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as exc:  # noqa: BLE001
            _say(f"VRAM report failed: {exc}")

    atexit.register(_dump)


_LEGACY = [s.strip() for s in os.environ.get("WP0_BEAR_LEGACY", "").split(",") if s.strip()]


def _install_legacy() -> None:
    """WP0_BEAR_LEGACY=<switch,...|all>: turn on BEAR 0.4.0 legacy switches
    (Config.restore_*) in every Config the scripts build, to attribute a
    changed result to one release change. A switch the script set itself is
    left as set."""
    import bear.config as bc
    fields = [f for f in bc.Config.model_fields if f.startswith("restore_")]
    if _LEGACY == ["all"]:
        want = fields
    else:
        want = [s if s.startswith("restore_") else f"restore_{s}" for s in _LEGACY]
    unknown = [w for w in want if w not in fields]
    if unknown:
        raise RuntimeError(f"unknown legacy switches {unknown}; this BEAR has {fields}")
    orig = bc.Config.__init__

    def __init__(self, /, **data):
        for w in want:
            data.setdefault(w, True)
        orig(self, **data)

    bc.Config.__init__ = __init__
    _say(f"BEAR legacy switches on: {want}")


_NO_LOCAL = os.environ.get("WP0_NO_LOCAL_MODELS", "").strip() not in ("", "0")


def _install_no_local_models() -> None:
    """WP0_NO_LOCAL_MODELS=1: refuse to load any local model (sentence-
    transformers bi-encoders and cross-encoders, transformers models). Loading
    BGE in WSL crashed the distro three times on 2026-10-30, and the
    coordinator put local model loads on hold. BM25, hash embeddings and the
    remote Nemotron service load no model, so they still run. A script that
    catches the error (the ITR row of eval_governance_decomposed.py) carries
    on without that row."""
    import sentence_transformers as st
    import transformers

    msg = ("WP0_NO_LOCAL_MODELS is set: local model loads are on hold "
           "(BGE loads crashed WSL); run BM25, hash or the remote Nemotron backend")

    def _deny(*_a, **_k):
        raise RuntimeError(msg)

    st.SentenceTransformer.__init__ = _deny
    st.CrossEncoder.__init__ = _deny
    transformers.PreTrainedModel.from_pretrained = classmethod(lambda cls, *a, **k: _deny())
    for name in ("AutoModel", "AutoModelForSequenceClassification", "AutoModelForCausalLM"):
        cls = getattr(transformers, name, None)
        if cls is not None:
            cls.from_pretrained = classmethod(lambda c, *a, **k: _deny())
    _say("local model loads refused (WP0_NO_LOCAL_MODELS)")


_ENCODE_BATCH = os.environ.get("WP0_ENCODE_BATCH", "").strip()


def _install_batch_cap() -> None:
    """WP0_ENCODE_BATCH=<n>: cap the batch size of every
    SentenceTransformer.encode call at n. Local models run on CPU inside a
    memory-capped scope (coordinator, 2026-10-30), and a batch of 32 long
    ToolBench documents needs tens of GB for attention on CPU. Installed
    outside the embedding cache, so cache keys record the batch size used. A
    smaller batch changes padding, so vectors can differ from batch-32 runs at
    the level of float rounding."""
    import sentence_transformers as st
    cap = int(_ENCODE_BATCH)
    cls = st.SentenceTransformer
    inner = cls.encode

    empty = os.environ.get("WP0_EMPTY_CACHE", "").strip() not in ("", "0")

    def encode(self, sentences, *args, **kwargs):
        b = kwargs.get("batch_size", 32)
        kwargs["batch_size"] = max(1, min(int(b), cap))
        if empty:  # hand freed blocks back before each call (GPU under a cap); vectors unchanged
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        return inner(self, sentences, *args, **kwargs)

    cls.encode = encode
    _say(f"encode batch size capped at {cap}")


_TRACE_LOG = os.environ.get("WP0_TRACE_LOG", "").strip()


def _install_trace_log() -> None:
    """WP0_TRACE_LOG=<jsonl>: route Retriever.retrieve through
    retrieve_with_trace (BEAR 0.4.0+) and log, per call, how many items were
    admitted with trace reason "required_tags" (the backfill 0.4.1 changes)
    and how many of those were returned. On each retriever's first calls the
    traced output is checked against the plain retrieve(); a difference
    raises, so the hook cannot change a result unnoticed."""
    import atexit
    import json
    import bear.retriever as br

    cls = br.Retriever
    if not hasattr(cls, "retrieve_with_trace"):
        _say("trace log: this BEAR has no retrieve_with_trace; hook off")
        return
    orig = cls.retrieve
    step = os.environ.get("WP0_STEP", "")
    buf: list[str] = []
    checked: dict[int, int] = {}

    def retrieve(self, *args, **kwargs):
        out, trace = self.retrieve_with_trace(*args, **kwargs)
        n = checked.get(id(self), 0)
        if n < 3:
            ref = orig(self, *args, **kwargs)
            if [x.id for x in ref] != [x.id for x in out]:
                raise RuntimeError("retrieve_with_trace output differs from retrieve()")
            checked[id(self)] = n + 1
        rt = [i for i, h in trace.admitted.items() if h == "required_tags"]
        cfg = self._config
        query = args[0] if args else kwargs.get("query", "")
        buf.append(json.dumps({
            "step": step, "model": cfg.embedding_model,
            "backend": getattr(cfg.embedding_backend, "value", str(cfg.embedding_backend)),
            "priority_weight": cfg.priority_weight, "threshold": cfg.default_threshold,
            "mandatory_tags": list(cfg.mandatory_tags), "n_items": len(self._instruction_list),
            "query": str(query)[:120], "n_required_tags": len(rt),
            "n_required_tags_in_output": len(set(rt) & {x.id for x in out})}))
        if len(buf) >= 500:
            _flush()
        return out

    def _flush():
        if buf:
            with open(_TRACE_LOG, "a", encoding="utf-8") as f:
                f.write("\n".join(buf) + "\n")
            buf.clear()

    atexit.register(_flush)
    cls.retrieve = retrieve
    _say(f"trace log on: {_TRACE_LOG}")


_CACHE_DIR = os.environ.get("WP0_EMB_CACHE", "").strip()


def _install_encode_cache() -> None:
    import hashlib
    import json
    import sqlite3

    import numpy as np
    import torch
    import sentence_transformers as st

    cls = st.SentenceTransformer
    if getattr(cls, "_wp0_cached", False):
        return
    orig_encode = cls.encode
    os.makedirs(_CACHE_DIR, exist_ok=True)
    db = sqlite3.connect(os.path.join(_CACHE_DIR, "emb.sqlite"), timeout=120,
                         check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, shape TEXT, "
               "dtype TEXT, data BLOB)")
    db.commit()
    stats = {"hit": 0, "miss": 0}

    def _ident(model) -> str:
        try:
            name = model[0].auto_model.name_or_path
        except Exception:  # noqa: BLE001
            name = type(model).__name__
        try:
            dtype = str(next(model.parameters()).dtype)
        except Exception:  # noqa: BLE001
            dtype = "?"
        dev = str(model.device)
        threads = torch.get_num_threads() if dev == "cpu" else 0
        return f"{name}|{dev}|{dtype}|threads={threads}"

    def encode(self, sentences, *args, **kwargs):
        kw = {k: v for k, v in kwargs.items() if k != "show_progress_bar"}
        try:
            payload = json.dumps([_ident(self), sentences, [repr(a) for a in args],
                                  sorted((k, repr(v)) for k, v in kw.items())])
        except TypeError:
            return orig_encode(self, sentences, *args, **kwargs)
        key = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        row = db.execute("SELECT shape, dtype, data FROM emb WHERE k=?", (key,)).fetchone()
        if row is not None:
            stats["hit"] += 1
            shape = tuple(json.loads(row[0]))
            return np.frombuffer(row[2], dtype=np.dtype(row[1])).reshape(shape).copy()
        out = orig_encode(self, sentences, *args, **kwargs)
        if isinstance(out, np.ndarray):
            stats["miss"] += 1
            arr = np.ascontiguousarray(out)
            db.execute("INSERT OR IGNORE INTO emb VALUES (?,?,?,?)",
                       (key, json.dumps(list(arr.shape)), arr.dtype.str, arr.tobytes()))
            db.commit()
        return out

    def _report():
        _say(f"embedding cache: {stats['hit']} hits, {stats['miss']} misses ({_CACHE_DIR})")

    import atexit
    atexit.register(_report)
    cls.encode = encode
    cls._wp0_cached = True


try:
    if _NO_LOCAL:
        _install_no_local_models()
    if (_DTYPE or _SHARE) and not _NO_LOCAL:
        _install_st_patch()
    if _CACHE_DIR:
        _install_encode_cache()
    if _ENCODE_BATCH and not _NO_LOCAL:
        _install_batch_cap()
    if _LEGACY:
        _install_legacy()
    if _TRACE_LOG:
        _install_trace_log()
    if _CAP:
        _install_cap()
    if _REPORT:
        _install_report()
except Exception as _exc:  # noqa: BLE001
    _say(f"hook setup failed: {_exc!r}")
    raise
