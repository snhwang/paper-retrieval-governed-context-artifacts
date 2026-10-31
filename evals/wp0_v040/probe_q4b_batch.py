"""Does Qwen3-Embedding-4B (bf16, GPU) fit under the allocator cap at a given
encode batch, on the longest texts BEAR embeds? (coordinator, 2026-10-31)

sentence-transformers sorts an encode call by length, longest first, so the
first batch of a call holds its longest texts. For each corpus the failing
steps embed, this encodes the B longest passage texts (as BEAR builds them,
with BEAR's passage prefix, none for Qwen3-4B) and the B longest query texts
(with the query instruction) as one batch, and records the peak allocated and
reserved memory against the cap (WP0_GPU_CAP_GIB, set by gpu_gate.sh). No
cache, no truncation, max_seq_length as loaded.

    python probe_q4b_batch.py --batches 2 1 --out probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))


def texts_for(corpus, spec):
    from bear import Config, Retriever
    cfg = Config(embedding_model=spec["model"], embedding_dim=spec["dim"],
                 embedding_query_prefix=spec["query_prefix"], embedding_passage_prefix="",
                 embedding_trust_remote_code=spec.get("trust_remote_code", False))
    r = Retriever(corpus, config=cfg)
    return [r._instruction_text(i) for i in corpus]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batches", nargs="+", type=int, default=[2, 1])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    import torch
    from sentence_transformers import SentenceTransformer
    import eval_toolbench as et
    import eval_toolbench_e2e as e2e

    spec = et.BACKEND_SPECS["qwen3-4b"]
    qprefix = spec["query_prefix"]
    tb_corpus, tb_queries = et.load_toolbench_corpus_and_queries()[:2]
    e2e_corpus, e2e_queries = e2e.load_toolbench_data()
    mt_corpus, _ = et.load_metatool_corpus()
    sets = {
        "ToolBench (eval_toolbench) passages": texts_for(tb_corpus, spec),
        "ToolBench e2e passages": texts_for(e2e_corpus, spec),
        "MetaTool passages": texts_for(mt_corpus, spec),
        "ToolBench queries": [qprefix + q[0] for q in tb_queries],
        "ToolBench e2e queries": [qprefix + q[0] for q in e2e_queries],
    }
    model = SentenceTransformer(spec["model"], device="cuda", trust_remote_code=spec.get("trust_remote_code", False),
                                model_kwargs={"torch_dtype": torch.bfloat16})
    tok = model.tokenizer
    cap = float(os.environ.get("WP0_GPU_CAP_GIB", "0") or 0)
    out = {"model": spec["model"], "dtype": "bfloat16", "max_seq_length": model.max_seq_length,
           "cap_gib": cap, "weights_gib": torch.cuda.memory_allocated() / 2**30, "sets": {}}
    for name, texts in sets.items():
        lens = sorted(((len(tok(t, add_special_tokens=True)["input_ids"]), t) for t in texts), reverse=True)
        rec = {"n": len(texts), "longest_tokens": [x[0] for x in lens[:4]], "batches": {}}
        for b in a.batches:
            batch = [t for _, t in lens[:b]]
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            try:
                model.encode(batch, batch_size=b, convert_to_numpy=True)
                rec["batches"][b] = {"ok": True,
                                     "peak_allocated_gib": round(torch.cuda.max_memory_allocated() / 2**30, 3),
                                     "peak_reserved_gib": round(torch.cuda.max_memory_reserved() / 2**30, 3)}
            except torch.OutOfMemoryError as exc:
                rec["batches"][b] = {"ok": False, "error": str(exc)[:160]}
            print(name, b, rec["batches"][b], flush=True)
        out["sets"][name] = rec
    Path(a.out).write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
