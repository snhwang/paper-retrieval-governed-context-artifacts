"""Evaluate BEAR on external tool-retrieval benchmarks: ToolBench + MetaTool.

Measures how well BEAR's governance-aware retrieval performs on established
tool-selection benchmarks, compared against vanilla embedding retrieval.

**ToolBench** (OpenBMB, ICLR 2024 Spotlight):
  - 16,464 APIs across 49 RapidAPI categories
  - Benchmark queries with ground-truth relevant_apis
  - Tests: g1_instruction, g1_category, g1_tool, g2_*, g3_*

**MetaTool** (HowieHwong, ICLR 2024):
  - 201 tools from OpenAI plugin store
  - 20,630 single-tool + 497 multi-tool queries with ground truth
  - Simpler but well-validated benchmark

For each benchmark, we evaluate:
  1. BEAR + BGE-base (dense, with governance)
  2. BEAR + BM25 (sparse, with governance)
  3. BEAR + BGE-base (no governance -- ablation)
  4. Embedding-only baseline (BGE-base, no scope filtering)

Metrics: Recall@k, NDCG@k, F1@k with 95% bootstrap CIs.

Usage:
    python eval_toolbench.py                       # both benchmarks
    python eval_toolbench.py --metatool-only        # MetaTool only (faster, no HF download)
    python eval_toolbench.py --toolbench-only       # ToolBench only
    python eval_toolbench.py --max-queries 200      # limit queries for quick testing
    python eval_toolbench.py --top-k 5              # evaluate at k=5
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bear import Corpus, Config, Context, Retriever, EmbeddingBackend
from bear.models import Instruction, InstructionType, ScopeCondition, ScoredInstruction
from stat_utils import bootstrap_ci, format_ci, format_ci_latex, welch_ttest, cohens_d_ind

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent / "data" / "external_benchmarks"
METATOOL_DIR = DATA_DIR / "metatool"
TOOLBENCH_DIR = DATA_DIR / "toolbench"

DEFAULT_TOP_K = 5
PRIORITY_WEIGHT = 0.3
THRESHOLD = 0.15  # Lower threshold for large corpora
BOOTSTRAP_ITERS = 10_000

EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def recall_at_k(retrieved_ids: set[str], expected_ids: set[str], k: int) -> float:
    """Recall@k: fraction of expected items found in top-k retrieved."""
    if not expected_ids:
        return 0.0
    tp = len(retrieved_ids & expected_ids)
    return tp / len(expected_ids)


def precision_at_k(retrieved_ids: set[str], expected_ids: set[str], k: int) -> float:
    """Precision@k: fraction of retrieved items that are relevant."""
    if not retrieved_ids:
        return 0.0
    tp = len(retrieved_ids & expected_ids)
    return tp / len(retrieved_ids)


def f1_at_k(retrieved_ids: set[str], expected_ids: set[str], k: int) -> float:
    """F1@k: harmonic mean of Precision@k and Recall@k."""
    p = precision_at_k(retrieved_ids, expected_ids, k)
    r = recall_at_k(retrieved_ids, expected_ids, k)
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def ndcg_at_k(retrieved_ids: list[str], expected_ids: set[str], k: int) -> float:
    """NDCG@k with binary relevance.

    Args:
        retrieved_ids: Ordered list of retrieved IDs (rank order matters).
        expected_ids: Set of ground-truth relevant IDs.
        k: Evaluation cutoff.

    Returns:
        NDCG@k score in [0, 1].
    """
    if not expected_ids:
        return 0.0

    # DCG: sum of 1/log2(rank+1) for relevant items in top-k
    dcg = 0.0
    for rank, rid in enumerate(retrieved_ids[:k]):
        if rid in expected_ids:
            dcg += 1.0 / math.log2(rank + 2)  # rank is 0-indexed, log2(1+1)=1

    # Ideal DCG: all relevant items ranked at top
    n_relevant = min(len(expected_ids), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_relevant))

    if idcg == 0:
        return 0.0
    return dcg / idcg


# ---------------------------------------------------------------------------
# MetaTool data loading
# ---------------------------------------------------------------------------

def load_metatool_corpus() -> tuple[Corpus, list[Instruction]]:
    """Load MetaTool tools as BEAR instructions.

    Returns:
        (corpus, instruction_list)
    """
    des_path = METATOOL_DIR / "plugin_des.json"
    info_path = METATOOL_DIR / "plugin_info.json"

    if not des_path.exists():
        raise FileNotFoundError(
            f"MetaTool data not found at {des_path}. "
            "Run toolbench_setup.py first to download."
        )

    with open(des_path) as f:
        tool_des = json.load(f)

    tool_info: list[dict] | None = None
    if info_path.exists():
        with open(info_path) as f:
            tool_info = json.load(f)

    # Build info lookup
    info_lookup: dict[str, dict] = {}
    if tool_info:
        for entry in tool_info:
            key = entry.get("name_for_model", "")
            if key:
                info_lookup[key] = entry

    corpus = Corpus()
    instructions = []

    for tool_name, short_desc in tool_des.items():
        info = info_lookup.get(tool_name, {})
        model_desc = info.get("description_for_model", "")
        human_desc = info.get("description_for_human", short_desc)

        content_parts = [f"Tool: {tool_name}"]
        if human_desc:
            content_parts.append(f"Description: {human_desc}")
        if model_desc and model_desc != human_desc:
            content_parts.append(f"Usage: {model_desc}")

        inst = Instruction(
            id=f"metatool/{tool_name}",
            type=InstructionType.TOOL,
            priority=50,
            content="\n".join(content_parts),
            scope=ScopeCondition(tags=[tool_name.lower()]),
            metadata={"source": "metatool", "tool_name": tool_name},
            tags=[tool_name.lower()],
        )
        corpus.add(inst)
        instructions.append(inst)

    return corpus, instructions


def load_metatool_queries(
    max_queries: int | None = None,
) -> list[tuple[str, list[str], set[str]]]:
    """Load MetaTool ground-truth queries.

    Returns list of (query_text, context_tags, expected_tool_ids).
    """
    queries = []

    # Single-tool queries from CSV
    csv_path = METATOOL_DIR / "all_clean_data.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                query_text = ""
                tool_name = ""
                # Detect column names (may vary)
                for col in row:
                    if "query" in col.lower() or "question" in col.lower() or "prompt" in col.lower():
                        query_text = row[col]
                    if "tool" in col.lower() or "plugin" in col.lower():
                        tool_name = row[col]
                if query_text and tool_name:
                    tool_id = f"metatool/{tool_name}"
                    # No governance tags for baseline -- MetaTool has no categories
                    queries.append((query_text.strip(), [], {tool_id}))

    # Multi-tool queries
    multi_path = METATOOL_DIR / "multi_tool_query_golden.json"
    if multi_path.exists():
        with open(multi_path) as f:
            multi_data = json.load(f)
        for entry in multi_data:
            query_text = entry.get("query", "")
            tools = entry.get("tool", [])
            if query_text and tools:
                expected = {f"metatool/{t}" for t in tools}
                queries.append((query_text.strip(), [], expected))

    if max_queries and len(queries) > max_queries:
        rng = np.random.default_rng(42)
        indices = rng.choice(len(queries), size=max_queries, replace=False)
        queries = [queries[i] for i in sorted(indices)]

    return queries


# ---------------------------------------------------------------------------
# ToolBench data loading
# ---------------------------------------------------------------------------



def load_metatool_corpus_tagged(
    tags_path: Path | None = None,
) -> tuple[Corpus, list[Instruction]]:
    """Load MetaTool corpus with LLM-generated category tags.

    Loads plugin_tags.json (generated by metatool_generate_tags.py) and
    applies required_tags to each tool instruction, enabling BEAR governance.

    Returns:
        (tagged_corpus, instruction_list)
    """
    tags_file = tags_path or (METATOOL_DIR / "plugin_tags.json")
    if not tags_file.exists():
        raise FileNotFoundError(
            f"Tags file not found: {tags_file}. "
            "Run metatool_generate_tags.py first."
        )
    with open(tags_file) as f:
        tool_tags: dict[str, list[str]] = json.load(f)

    # Load base corpus
    corpus_base, instructions_base = load_metatool_corpus()

    # Rebuild with required_tags applied
    corpus = Corpus()
    instructions = []
    for inst in instructions_base:
        tool_name = inst.metadata.get("tool_name", "")
        cat_tags = tool_tags.get(tool_name, [])
        # Build new instruction with required_tags = category tags
        tagged_inst = Instruction(
            id=inst.id,
            type=inst.type,
            priority=inst.priority,
            content=inst.content,
            scope=ScopeCondition(
                tags=cat_tags,
                required_tags=cat_tags,  # hard gate on category tags
            ),
            metadata=inst.metadata,
            tags=cat_tags,
        )
        corpus.add(tagged_inst)
        instructions.append(tagged_inst)

    return corpus, instructions


def load_metatool_queries_tagged(
    tags_path: Path | None = None,
    max_queries: int | None = None,
) -> list[tuple[str, list[str], set[str]]]:
    """Load MetaTool queries with context tags derived from the target tool's tags.

    For each query, uses the LLM-generated tags of its target tool as the
    context_tags — simulating a governed retrieval scenario where the query
    context is labeled with domain categories.

    Returns list of (query_text, context_tags, expected_tool_ids).
    """
    tags_file = tags_path or (METATOOL_DIR / "plugin_tags.json")
    with open(tags_file) as f:
        tool_tags: dict[str, list[str]] = json.load(f)

    queries_base = load_metatool_queries(max_queries=max_queries)

    tagged_queries = []
    for query_text, _, expected_ids in queries_base:
        # Get context tags from the expected tool's tags
        context_tags: list[str] = []
        for tool_id in expected_ids:
            tool_name = tool_id.replace("metatool/", "")
            tags = tool_tags.get(tool_name, [])
            context_tags.extend(tags)
        # Deduplicate while preserving order
        seen: set[str] = set()
        context_tags = [t for t in context_tags if not (t in seen or seen.add(t))]
        tagged_queries.append((query_text, context_tags, expected_ids))

    return tagged_queries



def load_metatool_queries_from_query_tags(
    query_tags_path: Path | None = None,
    max_queries: int | None = None,
) -> list[tuple[str, list[str], set[str]]]:
    """Load MetaTool queries with context tags derived from query text only.

    This is the stronger test: the LLM tagged each query based solely on
    its text (not knowing the target tool). If governance helps here, the
    taxonomy genuinely generalizes to new queries.

    Returns list of (query_text, context_tags, expected_tool_ids).
    """
    tags_file = query_tags_path or (METATOOL_DIR / "query_tags.json")
    if not tags_file.exists():
        raise FileNotFoundError(
            f"Query tags not found: {tags_file}. "
            "Run metatool_generate_query_tags.py first."
        )
    with open(tags_file) as f:
        query_data = json.load(f)

    queries = []
    for entry in query_data:
        query_text = entry.get("query", "").strip()
        context_tags = entry.get("context_tags", [])
        tools = entry.get("tools", [])
        if query_text and tools:
            expected = {f"metatool/{t}" for t in tools}
            queries.append((query_text, context_tags, expected))

    if max_queries and len(queries) > max_queries:
        import numpy as _np
        rng = _np.random.default_rng(42)
        indices = rng.choice(len(queries), size=max_queries, replace=False)
        queries = [queries[i] for i in sorted(indices)]

    return queries


def load_toolbench_corpus_and_queries(
    max_queries: int | None = None,
    splits: list[str] | None = None,
) -> tuple[Corpus, list[tuple[str, list[str], set[str]]], dict[str, str]]:
    """Load ToolBench benchmark data as BEAR corpus + queries.

    Returns:
        (corpus, queries, category_map)
        queries: list of (query_text, context_tags, expected_api_ids)
        category_map: api_id -> category_tag
    """
    bench_path = TOOLBENCH_DIR / "benchmark_data.json"
    if not bench_path.exists():
        raise FileNotFoundError(
            f"ToolBench data not found at {bench_path}. "
            "Run toolbench_setup.py first to download."
        )

    with open(bench_path) as f:
        data = json.load(f)

    if "status" in data and data.get("status") == "datasets_library_required":
        raise RuntimeError(
            "ToolBench data not yet downloaded. Install 'datasets' library "
            "and re-run toolbench_setup.py."
        )

    if splits is None:
        splits = list(data.keys())

    # First pass: collect all unique APIs to build the corpus
    all_apis: dict[str, dict] = {}  # id -> api dict
    category_map: dict[str, str] = {}  # id -> category_tag

    queries: list[tuple[str, list[str], set[str]]] = []

    for split_name in splits:
        if split_name not in data:
            continue
        for row in data[split_name]:
            query_text = row.get("query", "")
            if not query_text:
                continue

            # Parse api_list (all APIs available for this query)
            api_list_str = row.get("api_list", "[]")
            try:
                api_list = json.loads(api_list_str) if isinstance(api_list_str, str) else api_list_str
            except (json.JSONDecodeError, TypeError):
                api_list = []

            # Parse relevant_apis (ground truth)
            rel_str = row.get("relevant_apis", "[]")
            try:
                relevant_apis = json.loads(rel_str) if isinstance(rel_str, str) else rel_str
            except (json.JSONDecodeError, TypeError):
                relevant_apis = []

            # Register all APIs in corpus
            for api in api_list:
                if not isinstance(api, dict):
                    continue
                cat = api.get("category_name", "unknown")
                tool = api.get("tool_name", "unknown")
                api_name = api.get("api_name", "unknown")
                cat_tag = cat.lower().replace(" ", "_").replace("&", "and")
                api_id = f"toolbench/{cat_tag}/{tool}/{api_name}"
                all_apis[api_id] = api
                category_map[api_id] = cat_tag

            # Build a lookup from (tool_name, api_name) -> category for this query
            api_cat_lookup: dict[tuple[str, str], str] = {}
            for api in api_list:
                if isinstance(api, dict):
                    api_cat_lookup[(api.get("tool_name", ""), api.get("api_name", ""))] = \
                        api.get("category_name", "unknown")

            # Build expected set from relevant_apis
            # Format: [["tool_name", "api_name"], ...] (pairs, not dicts)
            expected_ids = set()
            query_cats = set()
            for api in relevant_apis:
                if isinstance(api, (list, tuple)) and len(api) >= 2:
                    tool_name, api_name = api[0], api[1]
                    cat = api_cat_lookup.get((tool_name, api_name), "unknown")
                elif isinstance(api, dict):
                    cat = api.get("category_name", "unknown")
                    tool_name = api.get("tool_name", "unknown")
                    api_name = api.get("api_name", "unknown")
                else:
                    continue
                cat_tag = cat.lower().replace(" ", "_").replace("&", "and")
                api_id = f"toolbench/{cat_tag}/{tool_name}/{api_name}"
                expected_ids.add(api_id)
                query_cats.add(cat_tag)
                # Register in corpus if not already there
                if api_id not in all_apis:
                    all_apis[api_id] = {"category_name": cat, "tool_name": tool_name,
                                        "api_name": api_name, "api_description": ""}
                    category_map[api_id] = cat_tag

            if expected_ids:
                context_tags = sorted(query_cats)
                queries.append((query_text.strip(), context_tags, expected_ids, split_name))

    # Build corpus from all collected APIs
    corpus = Corpus()
    for api_id, api in all_apis.items():
        cat = api.get("category_name", "unknown")
        tool = api.get("tool_name", "unknown")
        api_name = api.get("api_name", "unknown")
        desc = api.get("api_description", f"{tool} - {api_name}")
        cat_tag = cat.lower().replace(" ", "_").replace("&", "and")

        content_parts = [f"API: {tool} / {api_name}", f"Category: {cat}"]
        if desc:
            content_parts.append(f"Description: {desc}")

        # Parameters
        req_params = api.get("required_parameters", [])
        opt_params = api.get("optional_parameters", [])
        if req_params:
            parts = []
            for p in req_params:
                if isinstance(p, dict):
                    parts.append(f"  {p.get('name', '?')}: {p.get('description', '')}")
            if parts:
                content_parts.append("Required: " + "; ".join(parts))
        if opt_params:
            parts = []
            for p in opt_params:
                if isinstance(p, dict):
                    parts.append(f"  {p.get('name', '?')}: {p.get('description', '')}")
            if parts:
                content_parts.append("Optional: " + "; ".join(parts))

        inst = Instruction(
            id=api_id,
            type=InstructionType.TOOL,
            priority=50,
            content="\n".join(content_parts),
            scope=ScopeCondition(
                required_tags=[cat_tag],
                tags=[cat_tag, tool.lower()],
            ),
            metadata={"source": "toolbench", "category": cat, "tool_name": tool, "api_name": api_name},
            tags=[cat_tag, tool.lower()],
        )
        corpus.add(inst)

    if max_queries and len(queries) > max_queries:
        rng = np.random.default_rng(42)
        indices = rng.choice(len(queries), size=max_queries, replace=False)
        queries = [queries[i] for i in sorted(indices)]

    return corpus, queries, category_map


# ---------------------------------------------------------------------------
# Retriever construction
# ---------------------------------------------------------------------------

# Backend specifications: model, dim, query_prefix, extra kwargs
BACKEND_SPECS = {
    "bge": {
        "model": "BAAI/bge-base-en-v1.5",
        "dim": 768,
        "query_prefix": "Represent this sentence for retrieving relevant documents: ",
    },
    "bge-m3": {
        "model": "BAAI/bge-m3",
        "dim": 1024,
        "query_prefix": "",
    },
    "qwen3-0.6b": {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "dim": 1024,
        "query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
    },
    "qwen3-4b": {
        "model": "Qwen/Qwen3-Embedding-4B",
        "dim": 2560,
        "query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "trust_remote_code": True,
    },
    "nemotron-8b": {
        "model": "nvidia/llama-embed-nemotron-8b",
        "dim": 4096,
        "query_prefix": "Instruct: Retrieve behavioral instructions relevant to this query\nQuery: ",
        "trust_remote_code": True,
        "model_kwargs": {"attn_implementation": "flash_attention_2" if __import__("torch").cuda.is_available() else "eager", "torch_dtype": "bfloat16"},
        "tokenizer_kwargs": {"padding_side": "left"},
    },
}


def build_retriever(
    corpus: Corpus,
    backend: str = "bge",
    governance: bool = True,
    mandatory_tags: list[str] | None = None,
) -> Retriever:
    """Build a BEAR retriever for a given corpus and configuration.

    backend: "bge", "bge-m3", "qwen3-0.6b", "qwen3-4b", "nemotron-8b",
             "bm25", "hash", or "itr"
    """
    if backend == "bm25":
        config = Config(
            embedding_model="bm25",
            embedding_backend=EmbeddingBackend.BM25,
            embedding_dim=0,
            embedding_query_prefix="",
            embedding_passage_prefix="",
            priority_weight=PRIORITY_WEIGHT if governance else 0.0,
            default_threshold=0.0,
            default_top_k=DEFAULT_TOP_K,
            mandatory_tags=mandatory_tags or [],
        )
    elif backend == "hash":
        config = Config(
            embedding_model="hash",
            embedding_backend=EmbeddingBackend.NUMPY,
            embedding_dim=768,
            embedding_query_prefix="",
            embedding_passage_prefix="",
            priority_weight=PRIORITY_WEIGHT if governance else 0.0,
            default_threshold=THRESHOLD,
            default_top_k=DEFAULT_TOP_K,
            mandatory_tags=mandatory_tags or [],
        )
    elif backend == "itr":
        config = Config(
            embedding_model="hash",
            embedding_backend=EmbeddingBackend.ITR,
            embedding_dim=768,
            embedding_query_prefix="",
            embedding_passage_prefix="",
            priority_weight=PRIORITY_WEIGHT if governance else 0.0,
            default_threshold=THRESHOLD,
            default_top_k=DEFAULT_TOP_K,
            mandatory_tags=mandatory_tags or [],
        )
    elif backend in BACKEND_SPECS:
        spec = BACKEND_SPECS[backend]
        config = Config(
            embedding_model=spec["model"],
            embedding_backend=EmbeddingBackend.NUMPY,
            embedding_dim=spec["dim"],
            embedding_query_prefix=spec["query_prefix"],
            embedding_passage_prefix="",
            embedding_trust_remote_code=spec.get("trust_remote_code", False),
            embedding_model_kwargs=spec.get("model_kwargs", {}),
            embedding_tokenizer_kwargs=spec.get("tokenizer_kwargs", {}),
            priority_weight=PRIORITY_WEIGHT if governance else 0.0,
            default_threshold=THRESHOLD,
            default_top_k=DEFAULT_TOP_K,
            mandatory_tags=mandatory_tags or [],
        )
    else:
        raise ValueError(f"Unknown backend: {backend}")

    retriever = Retriever(corpus, config=config)

    if backend == "itr":
        from bear.backends.embeddings.itr_backend import ITRBackend
        retriever._backend = ITRBackend(
            dense_weight=0.7,
            sparse_weight=0.3,
            embedding_model=EMBEDDING_MODEL,
        )

    retriever.build_index()
    return retriever


def strip_governance(corpus: Corpus) -> Corpus:
    """Return a copy of the corpus with all scope conditions removed."""
    stripped = Corpus()
    for inst in corpus:
        ic = inst.model_copy(deep=True)
        ic.scope = ScopeCondition()  # Empty scope = matches everything
        stripped.add(ic)
    return stripped


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------

def evaluate_retriever(
    retriever: Retriever,
    queries: list[tuple[str, list[str], set[str]]],
    top_k: int = DEFAULT_TOP_K,
    use_tags: bool = True,
) -> dict[str, np.ndarray]:
    """Run retrieval on all queries, return per-query metric arrays.

    Args:
        retriever: BEAR retriever instance.
        queries: List of (query_text, context_tags, expected_ids).
        top_k: Number of results to retrieve.
        use_tags: Whether to pass context tags to the retriever.

    Returns:
        Dict with recall, precision, f1, ndcg arrays.
    """
    recalls, precisions, f1s, ndcgs = [], [], [], []

    for query_text, tags, expected in queries:
        ctx = Context(tags=tags if use_tags else [])
        results = retriever.retrieve(query_text, ctx, top_k=top_k)

        # Ordered list for NDCG
        retrieved_ordered = [r.id for r in results]
        retrieved_set = set(retrieved_ordered)

        recalls.append(recall_at_k(retrieved_set, expected, top_k))
        precisions.append(precision_at_k(retrieved_set, expected, top_k))
        f1s.append(f1_at_k(retrieved_set, expected, top_k))
        ndcgs.append(ndcg_at_k(retrieved_ordered, expected, top_k))

    return {
        "recall": np.array(recalls),
        "precision": np.array(precisions),
        "f1": np.array(f1s),
        "ndcg": np.array(ndcgs),
    }


# ---------------------------------------------------------------------------
# Experiment configurations
# ---------------------------------------------------------------------------

EXPERIMENTS = [
    # --- Governed backends ---
    {"name": "BEAR+BGE (gov)", "backend": "bge", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+BGE-M3 (gov)", "backend": "bge-m3", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+Qwen3-0.6B (gov)", "backend": "qwen3-0.6b", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+Qwen3-4B (gov)", "backend": "qwen3-4b", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+BM25 (gov)", "backend": "bm25", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+Hash (gov)", "backend": "hash", "governance": True, "use_tags": True, "strip_scope": False},
    {"name": "BEAR+ITR (gov)", "backend": "itr", "governance": True, "use_tags": True, "strip_scope": False},
    # --- Mandatory-only ablation (required_tags removed, mandatory injection kept) ---
    {"name": "BEAR+BGE (mand-only)", "backend": "bge", "governance": True, "use_tags": False, "strip_scope": False},
    {"name": "BEAR+BGE-M3 (mand-only)", "backend": "bge-m3", "governance": True, "use_tags": False, "strip_scope": False},
    {"name": "BEAR+Qwen3-0.6B (mand-only)", "backend": "qwen3-0.6b", "governance": True, "use_tags": False, "strip_scope": False},
    {"name": "BEAR+Qwen3-4B (mand-only)", "backend": "qwen3-4b", "governance": True, "use_tags": False, "strip_scope": False},
    {"name": "BEAR+BM25 (mand-only)", "backend": "bm25", "governance": True, "use_tags": False, "strip_scope": False},
    {"name": "BEAR+Hash (mand-only)", "backend": "hash", "governance": True, "use_tags": False, "strip_scope": False},
    # --- No governance ablations ---
    {"name": "BGE (no gov)", "backend": "bge", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "BGE-M3 (no gov)", "backend": "bge-m3", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "Qwen3-0.6B (no gov)", "backend": "qwen3-0.6b", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "Qwen3-4B (no gov)", "backend": "qwen3-4b", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "Hash (no gov)", "backend": "hash", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "ITR (no gov)", "backend": "itr", "governance": False, "use_tags": False, "strip_scope": True},
    {"name": "BM25 (no gov)", "backend": "bm25", "governance": False, "use_tags": False, "strip_scope": True},
]


def run_benchmark(
    benchmark_name: str,
    corpus: Corpus,
    queries: list[tuple[str, list[str], set[str]]],
    top_k: int = DEFAULT_TOP_K,
    experiment_names: list[str] | None = None,
) -> dict:
    """Run experiment configurations on a benchmark.

    Args:
        experiment_names: If provided, only run experiments whose name is in this list.

    Returns:
        Dict of results keyed by experiment name.
    """
    experiments = EXPERIMENTS
    if experiment_names:
        experiments = [e for e in EXPERIMENTS if e["name"] in experiment_names]
        if not experiments:
            print(f"  WARNING: No matching experiments for: {experiment_names}")
            print(f"  Available: {[e['name'] for e in EXPERIMENTS]}")
            return {}

    print(f"\n{'=' * 72}")
    print(f"  {benchmark_name}")
    print(f"  Corpus: {len(corpus)} instructions, Queries: {len(queries)}, k={top_k}")
    print(f"  Experiments: {len(experiments)}")
    print(f"{'=' * 72}")

    stripped_corpus = strip_governance(corpus)
    results = {}

    for exp in experiments:
        name = exp["name"]
        print(f"\n  {name}...")
        t0 = time.time()

        # Choose corpus
        corp = stripped_corpus if exp["strip_scope"] else corpus

        # Build retriever
        try:
            retriever = build_retriever(
                corp,
                backend=exp["backend"],
                governance=exp["governance"],
                mandatory_tags=[],
            )
        except Exception as e:
            print(f"    SKIPPED: {e}")
            continue

        # Evaluate overall
        metrics = evaluate_retriever(
            retriever, queries, top_k=top_k, use_tags=exp["use_tags"]
        )

        # Evaluate per split (ToolBench difficulty levels)
        by_split = {}
        split_names = sorted(set(q[3] for q in queries if len(q) > 3))
        for split in split_names:
            split_queries = [q for q in queries if len(q) > 3 and q[3] == split]
            if split_queries:
                sm = evaluate_retriever(retriever, split_queries, top_k=top_k, use_tags=exp["use_tags"])
                by_split[split] = {k: float(v.mean()) for k, v in sm.items()}
        elapsed = time.time() - t0

        # Bootstrap CIs
        metric_cis = {}
        for metric_name, values in metrics.items():
            ci = bootstrap_ci(values, n_boot=BOOTSTRAP_ITERS)
            metric_cis[metric_name] = ci

        results[name] = {
            "metrics": {k: v.tolist() for k, v in metrics.items()},
            "cis": metric_cis,
            "by_split": by_split,
            "elapsed_s": elapsed,
            "n_queries": len(queries),
        }

        # Print summary
        for metric_name in ["recall", "ndcg", "f1"]:
            ci = metric_cis[metric_name]
            print(f"    {metric_name:>10}@{top_k}: {format_ci(ci)}")
        print(f"    {'time':>10}:   {elapsed:.1f}s")

    # Statistical comparisons — paired tests (same queries across conditions)
    from scipy.stats import ttest_rel, wilcoxon

    print(f"\n  --- Statistical Tests (paired t-test, Wilcoxon, Cohen's d) ---")

    def _paired_cohens_d(a: np.ndarray, b: np.ndarray) -> float:
        diff = a - b
        sd = np.std(diff, ddof=1)
        return float(np.mean(diff) / sd) if sd > 0 else float('inf')

    def _compare(name_a: str, name_b: str):
        a = results.get(name_a, {})
        b = results.get(name_b, {})
        if not a or not b:
            return
        print(f"\n    {name_a}  vs  {name_b}:")
        for metric_name in ["recall", "ndcg", "f1"]:
            a_vals = np.array(a["metrics"].get(metric_name, []))
            b_vals = np.array(b["metrics"].get(metric_name, []))
            if len(a_vals) == 0 or len(b_vals) == 0:
                continue
            # Arrays must be same length for paired tests
            n = min(len(a_vals), len(b_vals))
            a_vals, b_vals = a_vals[:n], b_vals[:n]

            # Paired t-test
            if np.std(a_vals - b_vals) > 0:
                t_stat, t_p = ttest_rel(a_vals, b_vals)
            else:
                t_stat, t_p = 0.0, 1.0

            # Wilcoxon signed-rank (needs non-zero differences)
            diff = a_vals - b_vals
            nonzero = diff[diff != 0]
            if len(nonzero) >= 5:
                w_stat, w_p = wilcoxon(nonzero)
                w_str = f"W={w_stat:.0f}, p={w_p:.4f}"
            else:
                w_str = "skipped (<5 non-zero diffs)"

            d = _paired_cohens_d(a_vals, b_vals)
            sig = "***" if t_p < 0.001 else ("**" if t_p < 0.01 else ("*" if t_p < 0.05 else "n.s."))
            print(f"      {metric_name:>10}: paired-t={t_stat:.3f}, "
                  f"p={t_p:.4f} {sig}, d={d:.3f}; {w_str}")

    # Governance vs no governance (same backend)
    _compare("BEAR+BGE (gov)", "BGE (no gov)")
    _compare("BEAR+BGE-M3 (gov)", "BGE-M3 (no gov)")
    _compare("BEAR+Qwen3-0.6B (gov)", "Qwen3-0.6B (no gov)")
    _compare("BEAR+Qwen3-4B (gov)", "Qwen3-4B (no gov)")
    _compare("BEAR+Nemotron-8B (gov)", "Nemotron-8B (no gov)")
    _compare("BEAR+Hash (gov)", "Hash (no gov)")
    _compare("BEAR+ITR (gov)", "ITR (no gov)")
    _compare("BEAR+BM25 (gov)", "BM25 (no gov)")
    # Cross-backend with governance
    _compare("BEAR+BGE (gov)", "BEAR+BGE-M3 (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+Qwen3-0.6B (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+Qwen3-4B (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+Nemotron-8B (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+BM25 (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+Hash (gov)")
    _compare("BEAR+BGE (gov)", "BEAR+ITR (gov)")
    # Governed vs ungoverned (different backends)
    _compare("BEAR+BM25 (gov)", "BGE (no gov)")
    _compare("BEAR+ITR (gov)", "BGE (no gov)")

    return results


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------

def generate_latex_table(
    all_results: dict[str, dict],
    top_k: int,
) -> str:
    """Generate a LaTeX table from all benchmark results."""
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{BEAR performance on external tool-retrieval benchmarks.}",
        r"\label{tab:external-benchmarks}",
        r"\small",
        r"\begin{tabular}{ll" + "c" * 3 + "}",
        r"\toprule",
        f"Benchmark & Method & Recall@{top_k} & NDCG@{top_k} & F1@{top_k} \\\\",
        r"\midrule",
    ]

    for bench_name, bench_results in all_results.items():
        first = True
        for exp_name, exp_data in bench_results.items():
            cis = exp_data.get("cis", {})
            recall_ci = cis.get("recall", {})
            ndcg_ci = cis.get("ndcg", {})
            f1_ci = cis.get("f1", {})

            bench_col = bench_name if first else ""
            first = False

            # Short experiment name
            short_name = exp_name.replace("BEAR+", "").replace(" (full governance)", " +gov")
            short_name = short_name.replace(" (no governance)", " -gov")
            short_name = short_name.replace("embedding-only", "embed")

            r_str = format_ci_latex(recall_ci) if recall_ci else "---"
            n_str = format_ci_latex(ndcg_ci) if ndcg_ci else "---"
            f_str = format_ci_latex(f1_ci) if f1_ci else "---"

            lines.append(
                f"{bench_col} & {short_name} & {r_str} & {n_str} & {f_str} \\\\"
            )
        lines.append(r"\midrule")

    # Remove trailing midrule, add bottomrule
    if lines[-1] == r"\midrule":
        lines[-1] = r"\bottomrule"

    lines.extend([
        r"\end{tabular}",
        r"\end{table}",
    ])

    return "\n".join(lines)



def generate_ablation_by_split_table(
    full_gov_results: dict,
    mand_only_results: dict,
    no_gov_results: dict,
    top_k: int,
    backend: str = "BGE",
) -> str:
    """Generate governance ablation table broken down by ToolBench difficulty level."""
    splits = ["g1_instruction", "g1_category", "g1_tool", "g2_instruction", "g2_category", "g3_instruction"]
    short = {"g1_instruction": "g1-inst", "g1_category": "g1-cat", "g1_tool": "g1-tool",
             "g2_instruction": "g2-inst", "g2_category": "g2-cat", "g3_instruction": "g3-inst"}

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        f"\\caption{{Governance ablation by query difficulty on ToolBench ({backend}, Recall@{top_k}, 95\\% bootstrap CI).}}",
        f"\\label{{tab:toolbench-ablation-splits}}",
        r"\small",
        r"\begin{tabular}{@{}l" + "c" * len(splits) + "@{}}",
        r"\toprule",
        "Condition & " + " & ".join(short[s] for s in splits) + r" \\",
        r"\midrule",
    ]

    def get_split_recall(results_dict, split):
        key = f"BEAR+{backend} (gov)"
        if key not in results_dict:
            key = next(iter(results_dict), None)
        if key is None:
            return "---"
        split_data = results_dict.get(key, {}).get("by_split", {}).get(split, {})
        recall = split_data.get("recall_mean", None)
        return f"{recall:.3f}" if recall is not None else "---"

    for label, res in [("Full governance", full_gov_results),
                        ("Mandatory only", mand_only_results),
                        ("No governance", no_gov_results)]:
        row = label
        for split in splits:
            row += " & " + get_split_recall(res, split)
        lines.append(row + r" \\")

    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate BEAR on ToolBench + MetaTool benchmarks."
    )
    parser.add_argument("--metatool-only", action="store_true",
                        help="Only run MetaTool benchmark.")
    parser.add_argument("--toolbench-only", action="store_true",
                        help="Only run ToolBench benchmark.")
    parser.add_argument("--max-queries", type=int, default=None,
                        help="Limit number of queries per benchmark.")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                        help=f"Retrieve top-k (default: {DEFAULT_TOP_K}).")
    parser.add_argument("--backends", nargs="+", default=None,
                        help="Specific experiment names to run (e.g. 'BEAR+BGE (gov)' 'BGE (no gov)').")
    parser.add_argument("--all", action="store_true",
                        help="Run all backends (default if --backends not specified).")
    parser.add_argument("--output", type=str, default=None,
                        help="JSON output file path.")
    parser.add_argument("--latex", action="store_true",
                        help="Print LaTeX table to stdout.")
    parser.add_argument("--metatool-query-tags-only", action="store_true",
                        help="Only run MetaTool+QueryTags condition (fastest MetaTool eval).")
    parser.add_argument("--metatool-base-only", action="store_true",
                        help="Only run base MetaTool (no tags) condition.")
    args = parser.parse_args()

    do_metatool = not args.toolbench_only
    do_toolbench = not args.metatool_only
    metatool_query_tags_only = getattr(args, 'metatool_query_tags_only', False)
    metatool_base_only = getattr(args, 'metatool_base_only', False)

    # Determine which experiments to run
    exp_names = args.backends if args.backends else None  # None = all

    all_results = {}

    # --- MetaTool (no tags — negative control) ---
    if do_metatool and not metatool_query_tags_only:
        try:
            corpus, instructions = load_metatool_corpus()
            queries = load_metatool_queries(max_queries=args.max_queries)
            print(f"\nMetaTool (no tags) loaded: {len(corpus)} tools, {len(queries)} queries")

            if queries:
                results = run_benchmark("MetaTool", corpus, queries, top_k=args.top_k,
                                        experiment_names=exp_names)
                all_results["MetaTool"] = results
            else:
                print("  No MetaTool queries loaded (check data files)")
        except FileNotFoundError as e:
            print(f"\n[SKIP] MetaTool: {e}")

    # --- MetaTool+Tags (LLM-generated tags — tests metadata hypothesis) ---
    if do_metatool and not metatool_query_tags_only and not metatool_base_only:
        tags_file = METATOOL_DIR / "plugin_tags.json"
        if tags_file.exists():
            try:
                corpus_t, _ = load_metatool_corpus_tagged(tags_file)
                queries_t = load_metatool_queries_tagged(tags_file, max_queries=args.max_queries)
                tagged_count = sum(1 for _, ctx, _ in queries_t if ctx)
                print(f"\nMetaTool+Tags loaded: {len(corpus_t)} tools, {len(queries_t)} queries")
                print(f"  Queries with context tags: {tagged_count}/{len(queries_t)}")

                if queries_t:
                    results_t = run_benchmark("MetaTool+Tags", corpus_t, queries_t,
                                              top_k=args.top_k, experiment_names=exp_names)
                    all_results["MetaTool+Tags"] = results_t
            except Exception as e:
                print(f"\n[SKIP] MetaTool+Tags: {e}")
        else:
            print(f"\n[SKIP] MetaTool+Tags: plugin_tags.json not found")
            print("  Run: python metatool_generate_tags.py --model claude-sonnet-4-5-20251101")

    # --- MetaTool+QueryTags (tags from query text — strongest test) ---
    if do_metatool and not metatool_base_only:
        query_tags_file = METATOOL_DIR / "query_tags.json"
        tool_tags_file = METATOOL_DIR / "plugin_tags.json"
        if query_tags_file.exists() and tool_tags_file.exists():
            try:
                corpus_qt, _ = load_metatool_corpus_tagged(tool_tags_file)
                queries_qt = load_metatool_queries_from_query_tags(
                    query_tags_file, max_queries=args.max_queries
                )
                tagged_count = sum(1 for _, ctx, _ in queries_qt if ctx)
                print(f"\nMetaTool+QueryTags loaded: {len(corpus_qt)} tools, {len(queries_qt)} queries")
                print(f"  Queries with context tags: {tagged_count}/{len(queries_qt)}")
                if queries_qt:
                    results_qt = run_benchmark(
                        "MetaTool+QueryTags", corpus_qt, queries_qt,
                        top_k=args.top_k, experiment_names=exp_names
                    )
                    all_results["MetaTool+QueryTags"] = results_qt
            except Exception as e:
                print(f"\n[SKIP] MetaTool+QueryTags: {e}")
        else:
            missing = []
            if not tool_tags_file.exists():
                missing.append("plugin_tags.json (run metatool_generate_tags.py)")
            if not query_tags_file.exists():
                missing.append("query_tags.json (run metatool_generate_query_tags.py)")
            print(f"\n[SKIP] MetaTool+QueryTags: missing {', '.join(missing)}")

    # --- ToolBench ---
    if do_toolbench:
        try:
            corpus, queries, cat_map = load_toolbench_corpus_and_queries(
                max_queries=args.max_queries,
            )
            print(f"\nToolBench loaded: {len(corpus)} APIs, {len(queries)} queries")
            cats = set(cat_map.values())
            print(f"  Categories: {len(cats)}")

            if queries:
                results = run_benchmark("ToolBench", corpus, queries, top_k=args.top_k,
                                        experiment_names=exp_names)
                all_results["ToolBench"] = results
            else:
                print("  No ToolBench queries with ground truth found")
                print("  (The HuggingFace benchmark split may need 'datasets' library)")
        except FileNotFoundError as e:
            print(f"\n[SKIP] ToolBench: {e}")
        except RuntimeError as e:
            print(f"\n[SKIP] ToolBench: {e}")

    # --- Output ---
    if not all_results:
        print("\nNo benchmarks were run. Run toolbench_setup.py first to download data.")
        return

    # Save JSON
    output_path = args.output or str(
        Path(__file__).resolve().parent / "results" / "toolbench_eval.json"
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # Make JSON serialisable (convert numpy)
    def _serialise(obj):
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=_serialise)
    print(f"\nResults saved to {output_path}")

    # LaTeX table
    if args.latex:
        print("\n" + generate_latex_table(all_results, args.top_k))

    # --- Governance ablation by split table (ToolBench only) ---
    if "ToolBench" in all_results:
        tb = all_results["ToolBench"]
        # Find matching conditions for each governance level
        def find_results(suffix, backend="BGE"):
            key = f"BEAR+{backend} ({suffix})"
            return {key: tb[key]} if key in tb else {}

        full = find_results("gov")
        mand = find_results("mand-only")
        no_g = find_results("no gov")
        if full and mand and no_g:
            print("\n% === Governance ablation by difficulty split ===")
            print(generate_ablation_by_split_table(full, mand, no_g, args.top_k))

    # Summary
    print(f"\n{'=' * 72}")
    print("  Summary")
    print(f"{'=' * 72}")
    for bench_name, bench_results in all_results.items():
        print(f"\n  {bench_name}:")
        for exp_name, exp_data in bench_results.items():
            cis = exp_data.get("cis", {})
            recall_ci = cis.get("recall", {})
            ndcg_ci = cis.get("ndcg", {})
            recall_str = format_ci(recall_ci) if recall_ci else "n/a"
            ndcg_str = format_ci(ndcg_ci) if ndcg_ci else "n/a"
            print(f"    {exp_name:<35} R@{args.top_k}={recall_str}  NDCG@{args.top_k}={ndcg_str}")


if __name__ == "__main__":
    main()
