"""The manuscript's results and the files that hold them, for collect.py and verify.py.

One entry per manuscript item, in manuscript order. reproduce/MANIFEST.md is the
readable version, with the same ids. Paths are relative to a repo-shaped root:
$REPRO_OUT/assembled for your runs (70_assemble.sh), or this checkout for the
committed files. A path also matches its .gz copy.

status
  "b"       needs Scott's run: the paper attributes the number to BEAR 0.4.2 or
            to this revision. collect.py reads it from your runs only.
  "a"       Scott, previous version: a July or August 2026 run, kept unchanged
            with no claim that it ran on 0.4.2. collect.py reads your rerun if
            there is one (55_), else the committed file, which is that run.
  "static"  no number to reproduce (a design table, a figure drawn by hand, a
            configuration value).
"""
from __future__ import annotations

V = "results/v042/v042"
VL = "results/v042/logs"
D = "results/derived"          # reproduce/derive outputs, gathered by 70_assemble.sh


def tb(step: str) -> str:
    return f"{V}/{step}/toolbench_eval_{step}.json"


# The file and condition names of every Table 6, 8 and 9 row. Qwen3-4B pairs
# come from different steps per benchmark (encode batch 2 for ToolBench and base
# MetaTool, batch 8 for the tagged MetaTool variants), as reported.
BACKENDS = ["BGE", "BGE-M3", "Qwen3-0.6B", "Qwen3-4B", "BM25", "Hash", "Nemotron"]
STEP = {"BGE": "tb_bge", "BGE-M3": "tb_bgem3", "Qwen3-0.6B": "tb_qwen06", "BM25": "tb_bm25",
        "Hash": "tb_hash", "Nemotron": "tb_nemotron"}
Q4B = {"ToolBench": ("tb_qwen4b_tb_fix", "tb_qwen4b_tb_fix"),
       "MetaTool": ("tb_qwen4b_mt_gov_b2", "tb_qwen4b_mt_fix"),
       "MetaTool+Tags": ("tb_qwen4b", "tb_qwen4b"),
       "MetaTool+QueryTags-top5": ("tb_qwen4b", "tb_qwen4b")}


def tb_sources(bench: str) -> list[str]:
    out = [tb(STEP[b]) for b in BACKENDS if b != "Qwen3-4B"]
    out += sorted({tb(s) for s in Q4B[bench]})
    return out


def row_files(bench: str, backend: str) -> tuple[str, str]:
    """(file with the governed row, file with the ungated row)."""
    if backend == "Qwen3-4B":
        g, u = Q4B[bench]
        return tb(g), tb(u)
    return tb(STEP[backend]), tb(STEP[backend])


E2E = "results/v042/e2e_rerun/mistral-nemo"
JULY_E2E = ["evals/results/toolbench_e2e_scores.json", "evals/results/toolbench_e2e_results.json"]

ITEMS: list[dict] = [
    # ------------------------------------------------------------- front matter
    {"id": "A1", "label": "Abstract (L173-182)", "status": "b",
     "what": "headline effects. Each number repeats an item below (T06, T08, T09, T17, T17b, T21)",
     "script": "see T06, T08, T09, T17, T17b, T21", "sources": [], "extract": []},
    {"id": "T01", "label": "tab:capabilities (Table 1)", "status": "static",
     "what": "capability matrix, with its evidence in docs/capability-evidence.md", "script": "none", "sources": [], "extract": []},
    {"id": "F1", "label": "fig:instructions (Figure 1)", "status": "static",
     "what": "YAML example, a verbatim block in the .tex", "script": "none", "sources": [], "extract": []},
    {"id": "T02", "label": "tab:schema-cheatsheet (Table 2)", "status": "static", "what": "schema",
     "script": "none", "sources": [], "extract": []},
    {"id": "F2", "label": "fig:pipeline (Figure 2)", "status": "static",
     "what": "pipeline drawing, TikZ (Figure1.tex in the paper repo), no data", "script": "80_figures.sh",
     "sources": ["figures/Figure1-pipeline.pdf"], "extract": []},
    {"id": "RW297", "label": "Related work L297, 'NDCG@5 = 0.905'", "status": "b",
     "what": "no result file holds this number (stale text, see TEXT_FIXES.md)", "script": "none (TEXT_FIXES.md)",
     "sources": [], "extract": []},
    {"id": "X33", "label": "Sec 3.3 (L645), 'eight unit tests' and 'roughly twenty tokens per admitted tool'",
     "status": "b", "what": "test count of TestEmitToolSummary in BEAR v0.4.2, and the summary's cl100k tokens per tool",
     "script": "70_ (part derived: derive/composer_tests.py, derive/tool_summary_tokens.py)",
     "sources": [f"{D}/composer_tests.json", f"{D}/tool_summary_tokens.json"],
     "extract": [("flatten", {"path": f"{D}/composer_tests.json"}),
                 ("flatten", {"path": f"{D}/tool_summary_tokens.json"})]},
    {"id": "T03", "label": "tab:rq (Table 3)", "status": "static", "what": "research-question map",
     "script": "none", "sources": [], "extract": []},
    {"id": "T04", "label": "tab:model-roles (Table 4)", "status": "static", "what": "where models act",
     "script": "none", "sources": [], "extract": []},
    {"id": "T05", "label": "tab:provenance (Table 5)", "status": "static", "what": "tag provenance per condition",
     "script": "none", "sources": [], "extract": []},
    # ------------------------------------------------------- external benchmarks
    {"id": "X42s", "label": "Sec 4.2 setup (L764-783), 21,111 MetaTool queries (20,614 single-tool, 497 multi-tool)",
     "status": "b", "what": "query counts from the loader every MetaTool table uses",
     "script": "70_ (part derived: derive/metatool_split.py)",
     "sources": [f"{D}/metatool_split.json"], "extract": [("flatten", {"path": f"{D}/metatool_split.json"})]},
    {"id": "T06", "label": "tab:toolbench-results (Table 6)", "status": "b",
     "what": "ToolBench Recall@5, NDCG@5, governed minus ungated (d, p), seven backends",
     "script": "10_ (lex042, dense042), 20_ (gpuq4b042fix), 30_ (nemo042)",
     "sources": tb_sources("ToolBench"),
     "extract": [("toolbench_table", {"bench": "ToolBench"}), ("cross_backend", {"bench": "ToolBench"})]},
    {"id": "X42", "label": "Sec 4.2 results text (L787-807)", "status": "b",
     "what": "t and d per backend, cross-backend d against BGE, the Nemotron threshold diagnosis",
     "script": "as T06 and T08, and 30_ (diag) for the threshold",
     "sources": ["results/v042/diag/diag_nemotron_threshold.json"],
     "extract": [("flatten", {"path": "results/v042/diag/diag_nemotron_threshold.json"})]},
    {"id": "T07", "label": "tab:toolbench-inferred (Table 7)", "status": "b",
     "what": "oracle vs LLM-inferred categories (top-1, multi-tag, top-5). The inferred categories "
             "themselves are cached June API outputs (previous version)",
     "script": "10_ (dense042: t4_inferred, t4_multitag, t4_top5)",
     "sources": [f"{V}/t4_inferred/toolbench_inferred_metrics.json", f"{V}/t4_multitag/toolbench_multitag_metrics.json",
                 f"{V}/t4_top5/toolbench_top5_metrics.json"],
     "extract": [("flatten", {"path": f"{V}/t4_inferred/toolbench_inferred_metrics.json"}),
                 ("flatten", {"path": f"{V}/t4_multitag/toolbench_multitag_metrics.json"}),
                 ("flatten", {"path": f"{V}/t4_top5/toolbench_top5_metrics.json"})]},
    {"id": "T08", "label": "tab:metatool-results (Table 8)", "status": "b",
     "what": "base MetaTool, seven backends", "script": "10_, 20_ (gpuq4b042fix, gpuq4b042gov), 30_",
     "sources": tb_sources("MetaTool"), "extract": [("toolbench_table", {"bench": "MetaTool"})]},
    {"id": "T09", "label": "tab:metatool-tags-results (Table 9)", "status": "b",
     "what": "MetaTool+Tags and +QueryTags-top5, ungoverned references", "script": "10_, 20_ (gpuq4b042), 30_",
     "sources": sorted(set(tb_sources("MetaTool+Tags"))),
     "extract": [("toolbench_table", {"bench": "MetaTool+Tags"}),
                 ("toolbench_table", {"bench": "MetaTool+QueryTags-top5"})]},
    # --------------------------------------------------------------- end to end
    {"id": "T10a", "label": "tab:e2e (Table 10), rows rerun on 0.4.2", "status": "b",
     "what": "BEAR+BM25 (gov), BM25 (no gov), BEAR+BGE-M3 (gov), the BGE drift controls, and the "
             "governed vs ungated tests",
     "script": "50_e2e_ollama.sh (lists from 10_)",
     "sources": [f"{E2E}/{r}.scores.json" for r in ("bear_bm25_gov", "bm25_no_gov", "bear_bge-m3_gov",
                                                     "bear_bge_gov", "bge_no_gov")] + [f"{E2E}/rerun_summary.json"],
     "extract": [("e2e_rerun", {})]},
    {"id": "T10b", "label": "tab:e2e (Table 10), rows kept from July", "status": "a",
     "what": "BEAR+BGE, BEAR+Qwen3-0.6B, BEAR+Qwen3-4B (gov), BGE, BGE-M3, Qwen3-0.6B, Qwen3-4B (no gov)",
     "script": "55_e2e_previous_version.sh table10-july", "sources": JULY_E2E,
     "extract": [("e2e_july", {})]},
    {"id": "T10c", "label": "tab:e2e (Table 10), monolithic row", "status": "a",
     "what": "all 3,225 tools in the prompt: 0.251 / 0.186, recall 0.995",
     "script": "55_ table10-monolithic",
     "sources": ["evals/results/toolbench_e2e_results_partial.json", "evals/results/toolbench_e2e_scores_partial.json"],
     "extract": [("flatten", {"path": "evals/results/toolbench_e2e_results_partial.json"})]},
    {"id": "XE2Ea", "label": "E2E text (L1038-1050), statistics of the July runs", "status": "a",
     "what": "monolithic 3.3x and 4.0x (paired bootstrap p, d 0.86 to 1.01), every system vs monolithic (d 0.60 to "
             "1.01), hash vs monolithic (+0.024, p 0.13, d 0.05), McNemar 0.48 (Qwen3-0.6B vs Qwen3-4B), the cap-128 "
             "run (2.2%, n = 24), the chance rate, and the 14 colliding names over 22 endpoints",
     "script": "collect.py (from the July per-query arrays), 70_ (part derived: derive/e2e_name_collisions.py)",
     "sources": ["evals/results/toolbench_e2e_scores.json",
                 "evals/results/toolbench_e2e_scores_partial.json",
                 "evals/results/toolbench_e2e_scores_cap128_superseded.json", f"{D}/e2e_name_collisions.json"],
     "extract": [("e2e_text", {"part": "july"}), ("flatten", {"path": f"{D}/e2e_name_collisions.json"})]},
    {"id": "XE2Eb", "label": "E2E text (L1038-1050) and the Table 10 caption, numbers over Table 10 as printed",
     "status": "b",
     "what": "prompt size (82,298 cl100k, 88.3k Mistral-Nemo), ungoverned exact 0.53 to 0.67, 80% (70 to 87%) of the "
             "distance closed, the gate increment 0.07 to 0.15, drift at most 0.009",
     "script": "70_ (e2e-checks, wp4), 50_, collect.py",
     "sources": ["results/v042/e2e_checks/e2e_prompt_tokens.json", "results/v042/wp4/wp4_token_efficiency.json"]
                + [f"{E2E}/{r}.scores.json" for r in ("bear_bm25_gov", "bm25_no_gov", "bear_bge-m3_gov")],
     "extract": [("prompt_size", {}), ("e2e_text", {"part": "table10"})]},
    {"id": "T11", "label": "tab:e2e-react (Table 11)", "status": "a",
     "what": "ReAct vs single-turn, Mistral-Nemo", "script": "55_ table11-react",
     "sources": ["results/toolbench_react_metrics.json"],
     "extract": [("flatten", {"path": "results/toolbench_react_metrics.json"})]},
    {"id": "T12", "label": "tab:e2e-scale (Table 12)", "status": "a",
     "what": "monolithic configurations vs governance, Mistral-Nemo and Gemma 4 12B and 31B",
     "script": "55_ table12-*",
     "sources": ["results/toolbench_react_metrics_g4-12b-scaffold-nothink-full.json",
                 "results/toolbench_react_metrics_g4-12b-mono-think-full_partial.json",
                 "results/toolbench_react_metrics_g4-12b-bearsingle-nothink-full_partial.json",
                 "results/toolbench_react_metrics_g4-12b-bear-full_partial.json",
                 "results/toolbench_react_metrics_g4-31b-scaffold-nothink-full.json",
                 "results/toolbench_react_metrics_g4-FULL1100_merged.json"],
     "extract": [("flatten", {"path": p}) for p in [
         "results/toolbench_react_metrics_g4-12b-scaffold-nothink-full.json",
         "results/toolbench_react_metrics_g4-12b-mono-think-full_partial.json",
         "results/toolbench_react_metrics_g4-12b-bearsingle-nothink-full_partial.json",
         "results/toolbench_react_metrics_g4-12b-bear-full_partial.json",
         "results/toolbench_react_metrics_g4-31b-scaffold-nothink-full.json",
         "results/toolbench_react_metrics_g4-FULL1100_merged.json"]]},
    # ---------------------------------------------------------- customer support
    {"id": "T13", "label": "tab:token-efficiency (Table 13) and novel contexts (L1200), App D", "status": "b",
     "what": "tokens vs N, novel-department recall", "script": "10_ (dense042: scalability, baseline_comparison)",
     "sources": [f"{V}/scalability/scalability_results.csv", f"{V}/baseline_comparison/baseline_comparison_results.csv"],
     "extract": [("csv", {"path": f"{V}/scalability/scalability_results.csv"}),
                 ("csv", {"path": f"{V}/baseline_comparison/baseline_comparison_results.csv"}),
                 ("novel_mcnemar", {"path": f"{V}/baseline_comparison/baseline_comparison_results.csv"}),
                 ("latency", {"path": f"{V}/scalability/scalability_results.csv",
                              "columns": ["retrieval_mean_ms", "retrieval_p95_ms"]}),
                 ("latency", {"path": f"{V}/baseline_comparison/baseline_comparison_results.csv",
                              "columns": ["bear_mean_latency_ms", "cpa_mean_latency_ms"]})]},
    {"id": "T14", "label": "tab:semantic-advantage (Table 14)", "status": "b",
     "what": "semantic recall BEAR 1.000 vs CPA 0.000, with McNemar, Cohen's h and the CPA bound",
     "script": "10_ (dense042: baseline_comparison), statistics computed by collect.py",
     "sources": [f"{V}/baseline_comparison/baseline_comparison_results.csv"],
     "extract": [("semantic_stats", {"path": f"{V}/baseline_comparison/baseline_comparison_results.csv"})]},
    # ------------------------------------------------------------------ Pet Sim
    {"id": "T15", "label": "tab:token-compare (Table 15)", "status": "b",
     "what": "Pet Sim tokens per query and savings", "script": "10_ (lex042, dense042)",
     "sources": [f"{V}/gov_ablation_{x}/governance_ablation_{x}.json" for x in ("lex", "dense", "q4b")],
     "extract": [("flatten", {"path": f"{V}/gov_ablation_{x}/governance_ablation_{x}.json", "under": "token_efficiency"})
                 for x in ("lex", "dense", "q4b")]},
    {"id": "T16", "label": "tab:governance-ablation (Table 16)", "status": "b",
     "what": "panels a, b, c (F1 by level and query set, ITR in panel c)", "script": "10_ (lex042, dense042)",
     "sources": [f"{V}/gov_ablation_{x}/governance_ablation_{x}.json" for x in ("lex", "dense", "q4b")],
     "extract": [("flatten", {"path": f"{V}/gov_ablation_{x}/governance_ablation_{x}.json"}) for x in ("lex", "dense", "q4b")]},
    {"id": "T16lat", "label": "tab:governance-ablation (Table 16), ms/query column", "status": "a",
     "what": "latency as measured for the previous version (the caption says so). No committed file holds it",
     "script": "none (gap)", "sources": [], "extract": []},
    {"id": "T17", "label": "tab:decomposed-ablation (Table 17), upper rows", "status": "b",
     "what": "leave-one-out F1 per backend, ITR row 0.182", "script": "10_ (dense042, manddense042, lex042)",
     "sources": [f"{V}/decomposed_dense/governance_decomposed_{b}.json" for b in ("bge", "bge-m3", "qwen3")]
                + [f"{V}/decomposed_q4b/governance_decomposed_qwen3-4b.json", f"{V}/decomposed_bm25/governance_decomposed_bm25.json"],
     "extract": [("flatten", {"path": p, "under": "rows"}) for p in
                 [f"{V}/decomposed_dense/governance_decomposed_{b}.json" for b in ("bge", "bge-m3", "qwen3")]
                 + [f"{V}/decomposed_q4b/governance_decomposed_qwen3-4b.json", f"{V}/decomposed_bm25/governance_decomposed_bm25.json"]]},
    {"id": "T17b", "label": "tab:decomposed-ablation bottom rows, mandatory-coverage test (WP2)", "status": "b",
     "what": "246 queries, 738 pairs, arms A to C, seven backends", "script": "15_ (stores), 20_, 30_, 40_ (v042-rerun mandatory)",
     "sources": ["results/mandatory_coverage_v042.json", "results/mandatory_coverage_v042_output.txt"],
     "extract": [("text", {"path": "results/mandatory_coverage_v042_output.txt"})]},
    {"id": "T18", "label": "tab:invariants (Table 18) and nesting rate", "status": "b",
     "what": "violations on 2,000 random corpora, four backends, and nesting above the pool", "script": "15_ (wp256-v042)",
     "sources": ["results/invariants_v042.json", "results/invariants_v042_output.txt",
                 "results/invariants_v042_pool_sensitivity.json"],
     "extract": [("text", {"path": "results/invariants_v042_output.txt"}),
                 ("flatten", {"path": "results/invariants_v042_pool_sensitivity.json"})]},
    {"id": "XBB", "label": "Budget binding paragraph (L1575)", "status": "b",
     "what": "rate at which the admissible set exceeds k", "script": "15_ (wp256-v042, wp256-v042-bge)",
     "sources": ["results/budget_binding_v042_output.txt", "results/budget_binding_v042_bge_output.txt"],
     "extract": [("text", {"path": "results/budget_binding_v042_output.txt"}),
                 ("text", {"path": "results/budget_binding_v042_bge_output.txt"})]},
    {"id": "T19", "label": "tab:baselines (Table 19) and maintained CPA (L1610)", "status": "b",
     "what": "LlamaIndex metadata filters vs BEAR (BGE, Nemotron), maintained CPA", "script": "15_ (wp5-bge-cpa), 30_ (wp5)",
     "sources": [f"results/metadata_filter_baseline_{c}_{e}_v042.json" for c in ("toolbench", "petsim")
                 for e in ("bge", "nemotron")] + ["results/cpa_maintained_v042.json"],
     "extract": [("text", {"path": f"results/metadata_filter_baseline_{c}_{e}_v042_output.txt"})
                 for c in ("toolbench", "petsim") for e in ("bge", "nemotron")]
                + [("text", {"path": "results/cpa_maintained_v042_output.txt"})]},
    {"id": "T20", "label": "tab:robustness (Table 20)", "status": "b",
     "what": "tag noise and crossovers, over-restriction vs leakage, leakage and injection, giveaways",
     "script": "15_, 20_, 30_, 40_",
     "sources": ["results/tag_noise_v042_output.txt", "results/tag_noise_nemotron_v042_output.txt",
                 "results/tag_noise_qwen3-0.6b_output.txt", "results/tag_noise_overrestriction_v042.json",
                 "results/leakage_threat_v042_output.txt", "results/leakage_threat_bge-m3_output.txt",
                 "results/leakage_threat_qwen_output.txt", "results/query_giveaways_v042_output.txt",
                 "results/query_giveaways_qwen3-0.6b_output.txt", "results/bm25_v042_check_default_output.txt"],
     "extract": [("text", {"path": p}) for p in [
         "results/tag_noise_v042_output.txt", "results/tag_noise_nemotron_v042_output.txt",
         "results/tag_noise_qwen3-0.6b_output.txt", "results/leakage_threat_v042_output.txt",
         "results/leakage_threat_bge-m3_output.txt", "results/leakage_threat_qwen_output.txt",
         "results/query_giveaways_v042_output.txt", "results/query_giveaways_qwen3-0.6b_output.txt",
         "results/bm25_v042_check_default_output.txt"]]
                + [("flatten", {"path": "results/tag_noise_overrestriction_v042.json"})]},
    {"id": "T21", "label": "tab:tokens-recall (Table 21) and WP4 text", "status": "b",
     "what": "k and tokens to reach recall 0.80, 0.90, 0.95, seven backends, two benchmarks",
     "script": "10_, 20_, 30_ (lists), 70_ (wp4)",
     "sources": ["results/v042/wp4/summary.md", "results/v042/wp4/wp4_token_efficiency.json"],
     "extract": [("text", {"path": "results/v042/wp4/summary.md"})]},
    {"id": "XH", "label": "Sec 4.12 Hermes (WP7 stage 1 and 2)", "status": "b",
     "what": "execution-level results (the manuscript holds the design, results pending)",
     "script": "60_hermes.sh",
     "sources": ["hermes/results/stage1/tables.md", "hermes/results/stage2/tables.md"],
     "extract": [("text", {"path": "hermes/results/stage1/tables.md"}), ("text", {"path": "hermes/results/stage2/tables.md"})]},
    {"id": "XAUTH", "label": "Authorship ablation (WP6)", "status": "b",
     "what": "not yet designed: tags regenerated by a second model family. Not in the manuscript, no script",
     "script": "none (not yet designed)", "sources": [], "extract": []},
    # --------------------------------------------------------------- discussion
    {"id": "X53", "label": "Sec 5.3 ToolBench-IR (L1823-1829)", "status": "b",
     "what": "ToolBench-IR 0.847 alone, 0.842 governed, none of the 2,629 gold APIs gated out",
     "script": "10_ (dense042: toolllm_both), 70_ (part derived: evals/diag_gate_coverage.py --out)",
     "sources": [f"{V}/toolllm_both/toolbench_toolllm_fixed.json", f"{D}/gate_coverage.json"],
     "extract": [("flatten", {"path": f"{V}/toolllm_both/toolbench_toolllm_fixed.json"}),
                 ("flatten", {"path": f"{D}/gate_coverage.json"})]},
    {"id": "T23", "label": "tab:transfer (Table 23)", "status": "b",
     "what": "ToolBench-IR in and out of domain, and the off-the-shelf rows from the ungated rows of Tables 6 "
             "and 8 (not the dict hardcoded in eval_backend_transfer.py)",
     "script": "10_ (dense042: transfer_toolbench, transfer_metatool), collect.py",
     "sources": [f"{V}/transfer_toolbench/backend_transfer_toolbench_toolbench_ir_bert_based_uncased.json",
                 f"{V}/transfer_metatool/backend_transfer_metatool_toolbench_ir_bert_based_uncased.json"]
                + sorted(set(tb_sources("ToolBench") + tb_sources("MetaTool"))),
     "extract": [("transfer_table", {})]},
    {"id": "T24", "label": "tab:reranker (Table 24)", "status": "b",
     "what": "cross-encoder reranker and LlamaIndex rows, ToolBench and Pet Sim",
     "script": "10_ (dense042: reranker_*, framework_*)",
     "sources": [f"{V}/reranker_toolbench/reranker_composition_toolbench.json",
                 f"{V}/reranker_petsim/reranker_composition_petsim.json",
                 f"{V}/framework_toolbench/framework_baseline_toolbench.json",
                 f"{V}/framework_petsim/framework_baseline_petsim.json"],
     "extract": [("flatten", {"path": p}) for p in [
         f"{V}/reranker_toolbench/reranker_composition_toolbench.json", f"{V}/reranker_petsim/reranker_composition_petsim.json",
         f"{V}/framework_toolbench/framework_baseline_toolbench.json", f"{V}/framework_petsim/framework_baseline_petsim.json"]]},
    {"id": "X54", "label": "Sec 5.4 MetaTool discussion, mand-only rows", "status": "b",
     "what": "mand-only Recall@5 on six backends (BGE, BGE-M3, Qwen3-0.6B, Qwen3-4B, BM25, hash)",
     "script": "10_ (mandonly042, lex042, dense042), 20_ (mandonly: Qwen3-4B)",
     "sources": [tb("tb_bgem3_mand"), tb("tb_qwen06_mand"), tb("tb_qwen4b_mand")],
     "extract": [("mand_only", {})]},
    {"id": "X55", "label": "Sec 5.5 '199 tools in under three minutes'", "status": "a",
     "what": "tag-generation time. No committed log holds it", "script": "none (gap)", "sources": [], "extract": []},
    {"id": "X57", "label": "Sec 5.7 scope vs similarity, Conclusion items 1 to 6", "status": "b",
     "what": "ranges over T14, T16, T17, T06 to T09", "script": "as those items", "sources": [], "extract": []},
    # ---------------------------------------------------------------- appendices
    {"id": "AA", "label": "Appendix A, tag generation", "status": "a",
     "what": "MetaTool tool and query tags (Anthropic API, June and July 2026)", "script": "55_ tags-api",
     "sources": ["evals/data/external_benchmarks/metatool/plugin_tags.json",
                 "evals/data/external_benchmarks/metatool/query_tags_top5.json"], "extract": []},
    {"id": "T25", "label": "tab:retrieval (Table 25)", "status": "b",
     "what": "Full BEAR, Pure Similarity, Priority-Heavy, for hash and BGE. Parsed from the step logs (the script "
             "writes no JSON)",
     "script": "10_ (lex042: retrieval_hash, dense042: retrieval_semantic), collect.py",
     "sources": [f"{VL}/retrieval_hash.log", f"{VL}/retrieval_semantic.log"],
     "extract": [("retrieval_log", {"path": f"{VL}/retrieval_hash.log", "label": "hash"}),
                 ("retrieval_log", {"path": f"{VL}/retrieval_semantic.log", "label": "BGE"})]},
    {"id": "T26", "label": "tab:tool-scaling (Table 26) and tab:token-savings (Table 27)", "status": "b",
     "what": "tool scaling and token savings. Parsed from the step log (the script writes no JSON)",
     "script": "10_ (dense042: tool_scaling), collect.py",
     "sources": [f"{VL}/tool_scaling.log"],
     "extract": [("tool_scaling_log", {"path": f"{VL}/tool_scaling.log"})]},
    {"id": "AE", "label": "Appendix E, ITR configuration", "status": "static",
     "what": "ITR settings (instruction-tool-retrieval 0.1.1). Values in T16 and T17", "script": "none",
     "sources": [], "extract": []},
    {"id": "T28", "label": "tab:alpha-sweep (Table 28)", "status": "b",
     "what": "F1 vs alpha, five backends", "script": "10_ (dense042, lex042: alpha_sweep_*)",
     "sources": [f"{V}/alpha_sweep_dense/alpha_sweep_{b}.json" for b in ("bge", "bge-m3", "qwen3")]
                + [f"{V}/alpha_sweep_q4b/alpha_sweep_qwen3-4b.json", f"{V}/alpha_sweep_bm25/alpha_sweep_bm25.json"],
     "extract": [("flatten", {"path": p, "under": "rows"}) for p in
                 [f"{V}/alpha_sweep_dense/alpha_sweep_{b}.json" for b in ("bge", "bge-m3", "qwen3")]
                 + [f"{V}/alpha_sweep_q4b/alpha_sweep_qwen3-4b.json", f"{V}/alpha_sweep_bm25/alpha_sweep_bm25.json"]]},
]


def required_files(status: str = "b") -> list[str]:
    """Every source file of the items with this status."""
    out: list[str] = []
    for it in ITEMS:
        if it["status"] == status:
            out += [p for p in it["sources"] if p not in out]
    return out
