| File | Table | Cells compared | Comparator | Result |
|---|---|---|---|---|
| evals/results/metatool_full_eval.json | older MetaTool run | 144 | the file's own hash rows (same benchmark and condition) | none found |
| evals/results/toolbench_e2e_scores.json | Table 7 | 32 | BEAR+Hash (gov) in the file; regenerated 0.1.10 Hash (no gov) list | none found |
| evals/results/toolbench_eval.json | older ToolBench run | 144 | the file's own hash rows (same benchmark and condition) | none found (32 matches of all-zero mand-only arrays set aside) |
| results/alpha_sweep_all.json | tab:alpha-sweep | 5 | the per-backend files (consistency only) | none found |
| results/alpha_sweep_bge-m3.json | tab:alpha-sweep | 8 | 0.1.10 with model loads refused (fallback), same script and backend | none found |
| results/alpha_sweep_bge.json | tab:alpha-sweep | 8 | 0.1.10 with model loads refused (fallback), same script and backend | none found |
| results/alpha_sweep_qwen3-4b.json | tab:alpha-sweep | 8 | 0.1.10 with model loads refused (fallback), same script and backend | FALLBACK: alpha 0.7, 0.9, 1.0 equal hash. Replaced by 0.4.2 (and the 0.1.10 control with the real model) |
| results/alpha_sweep_qwen3.json | tab:alpha-sweep | 8 | 0.1.10 with model loads refused (fallback), same script and backend | none found |
| results/backend_comparison.json | tab:governance-ablation (a) | 60 | the Hash row; the 0.1.10 fallback run of each backend | 1 match, uninformative: ITR-hybrid para_f1 equals its fallback, but every governed dense backend gives the same 0.637 [0.627, 0.648] there; the other 4 ITR-hybrid columns differ from the fallback |
| results/backend_transfer_metatool_toolbench_ir_bert_based_uncased.json | tab:transfer | 3 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/backend_transfer_toolbench_toolbench_ir_bert_based_uncased.json | tab:transfer | 3 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/baseline_comparison_results.csv | tab:token-efficiency, tab:semantic-advantage, novel departments | 66 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/eval_retrieval_semantic_output.txt | tab:retrieval (BGE half) | 24 | eval_retrieval_output.txt (hash); the 0.1.10 fallback run | none found |
| results/eval_tool_scaling_output.txt | tab:tool-scaling, tab:token-savings | 38 | 0.1.10 with model loads refused (fallback), same script | all 38 cells equal the fallback, uninformative: they also equal real BGE on 0.4.2 (gate decides, threshold 0) |
| results/framework_baseline_petsim.json | tab:reranker | 1 | backend_comparison.json Hash (Full governance, k=10) | none found |
| results/framework_baseline_toolbench.json | tab:reranker | 2 | Table 3 hash per-query arrays (same first stage on ToolBench) | none found |
| results/governance_ablation.json | tab:governance-ablation, tab:token-compare | 125 | the Hash cells; the 0.1.10 fallback run | none found |
| results/governance_decomposed.json | tab:decomposed-ablation | 2 | ITR row of the forced-fallback rerun; the per-backend files (consistency only) | stale June BGE run (Full 0.780), not used by the table (0.653 comes from governance_decomposed_bge.json); differs from the fallback (0.841). Not a fallback |
| results/governance_decomposed_all.json | tab:decomposed-ablation | 10 | ITR row of the forced-fallback rerun; the per-backend files (consistency only) | FALLBACK (ITR library): the bm25 entry's ITR row equals ITR's fallback (0.2112); the other entries are consistent with their per-backend files |
| results/governance_decomposed_bge-m3.json | tab:decomposed-ablation | 8 | 0.1.10 with model loads refused (fallback), same script and backend; ITR row of the forced-fallback rerun | none found |
| results/governance_decomposed_bge.json | tab:decomposed-ablation | 8 | 0.1.10 with model loads refused (fallback), same script and backend; ITR row of the forced-fallback rerun | none found |
| results/governance_decomposed_bm25.json | tab:decomposed-ablation | 1 | ITR row of the forced-fallback rerun | FALLBACK (ITR library): the ITR row, 0.2112 [0.1863, 0.2371], equals ITR's own fallback exactly. It replaced the real 0.182 in 2acea02 (Aug 4). The manuscript prints 0.182. This run's dense-lane files give 0.182 |
| results/governance_decomposed_qwen3-4b.json | tab:decomposed-ablation | 8 | 0.1.10 with model loads refused (fallback), same script and backend; ITR row of the forced-fallback rerun | none found |
| results/governance_decomposed_qwen3.json | tab:decomposed-ablation | 8 | 0.1.10 with model loads refused (fallback), same script and backend; ITR row of the forced-fallback rerun | none found |
| results/reranker_composition_petsim.json | tab:reranker | 1 | backend_comparison.json Hash (Full governance, k=10) | none found |
| results/reranker_composition_toolbench.json | tab:reranker | 2 | Table 3 hash per-query arrays (same first stage on ToolBench) | none found |
| results/scalability_results.csv | scalability (text) | 42 | 0.1.10 with model loads refused (fallback), same script | all BEAR columns equal the fallback, uninformative: they also equal real BGE on 0.4.2 (recall 1.0, tokens set by the gate); the published N=10 build took 70 s, a model load |
| results/toolbench_eval_metatool_v0110.json | Tables 5, 6 | 144 | the file's own hash rows (same benchmark and condition) | none found (32 matches of all-zero mand-only arrays set aside) |
| results/toolbench_eval_qtags_top5_v0110.json | Table 6 +QueryTags | 96 | the file's own hash rows (same benchmark and condition) | none found (16 matches of all-zero mand-only arrays set aside) |
| results/toolbench_eval_qtags_top5_v0110_regen.json | Table 6 +QueryTags (regen) | 96 | the file's own hash rows (same benchmark and condition) | none found (16 matches of all-zero mand-only arrays set aside) |
| results/toolbench_eval_v0110.json | Table 3 | 192 | the file's own hash rows (same benchmark and condition) | none found (16 matches of all-zero mand-only arrays set aside) |
| results/toolbench_inferred_metrics.json | Table 4 | 9 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/toolbench_multitag_metrics.json | Table 4 | 9 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/toolbench_react_metrics.json | Table 8 | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_cap128_superseded.json | superseded (cap 128) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-bear-full_partial.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-bearsingle-nothink-full_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-mono-nothink-full_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-mono-think-full_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-scaffold-nothink-full.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-12b-scaffold-thinking-full_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-31b-scaffold-nothink-full.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-31b-scaffold-thinking-full_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-FULL1100_merged.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bear-compl_partial.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bear-s43_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bear-strat_partial.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bearsingle-nothink-compl_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bearsingle-nothink-s43_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-bearsingle-nothink-strat_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-nothink-compl_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-nothink-s43_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-nothink-strat_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-think-compl_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-think-s43_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_g4-mono-think-strat_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_gemma4-31b-bear_partial.json | Table 9 sources (Gemma 4) | 2 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | exploratory partial (Jul 16), not in Table 9. bear_single 0.005 is empty output (max_tokens 100 before the fix), not retrieval: bear_react on the same lists is 0.820 |
| results/toolbench_react_metrics_gemma4-31b-bearsingle_partial.json | Table 9 sources (Gemma 4) | 1 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_gemma4-31b-mono-nothink_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_react_metrics_gemma4-31b-reason_partial.json | Table 9 sources (Gemma 4) | 0 | bound: hash retrieval puts at least one gold API in the prompt for 0.266 of queries (Table 7 BEAR+Hash (gov)), so exact accuracy under hash retrieval is at most 0.266; measured 0.211 with Mistral-Nemo | none found |
| results/toolbench_toolllm_fixed.json | ToolBench-IR + governance (text) | 8 | 0.1.10 with model loads refused (fallback), same script | none found |
| results/toolbench_top5_metrics.json | Table 4 | 9 | 0.1.10 with model loads refused (fallback), same script | none found |

Published result files not compared, and why:
- evals/results/toolbench_e2e_eval.json
- evals/results/toolbench_e2e_results.json
- evals/results/toolbench_e2e_results_cap128_superseded.json
- evals/results/toolbench_e2e_results_partial.json
- evals/results/toolbench_e2e_scores_cap128_superseded.json
- evals/results/toolbench_e2e_scores_partial.json
- results/alpha_sweep_bm25.json
- results/composite_scale_audit.json
- results/g4_complement_indices.json
- results/g4_done_indices.json
- results/mandatory_injection.json
- results/petsim_fix_diagnosis.json
- results/scope_excluded_safety.json
- results/stb_react_4omini.json
- results/stb_react_54mini.json
- results/stb_react_54mini_k20.json
- results/toolbench_inferred_categories.json
- results/toolbench_multitag_categories.json
- results/toolbench_react_debug.json
- results/toolbench_toolllm.json
- results/toolbench_toolllm_hardgate.json
- results/toolbench_top5_categories.json

| Log (published) | Load failures, fallback warnings or tracebacks | Early stop |
|---|---|---|
| results/alpha_sweep_output.txt | none | === Alpha sweep (qwen3-4b) === reached 6/8 |
| results/baseline_comparison_v0110.log | none | none |
| results/composition_demo.txt | none | none |
| results/e2e_gemma-4-12b.log | none | none |
| results/e2e_lmstudio.log | none | none |
| results/e2e_mono_alltools.log | none | none |
| results/e2e_small.log | none | none |
| results/e2e_smoketest_gemma-4-e2b.log | none | none |
| results/e2e_v0110_guided.log | none | none |
| results/e2e_v0110_guided_gemma-4-e2b.log | none | none |
| results/eval_ablation_output.txt | none | none |
| results/eval_ablation_semantic_output.txt | none | none |
| results/eval_baseline_output.txt | none | none |
| results/eval_governance_ablation_output.txt | none | none |
| results/eval_retrieval_backends_output.txt | none | none |
| results/eval_retrieval_output.txt | none | none |
| results/eval_retrieval_semantic_output.txt | none | none |
| results/eval_scalability_output.txt | none | none |
| results/eval_tool_composition_output.txt | none | none |
| results/eval_tool_scaling_output.txt | none | none |
| results/framework_baseline_petsim.log | none | none |
| results/framework_baseline_toolbench.log | none | none |
| results/g4-12b_bear_full.log | none | none |
| results/g4-12b_bearsingle_full.log | none | none |
| results/g4-12b_mono_nothink_full.log | none | none |
| results/g4-12b_mono_think_full.log | none | none |
| results/g4-12b_scaffold_nothink_full.log | none | none |
| results/g4-31b_scaffold_nothink_full.log | none | none |
| results/g4_bear.log | none | none |
| results/g4_bear_compl.log | none | none |
| results/g4_bear_s43.log | none | none |
| results/g4_bear_strat.log | none | none |
| results/g4_bearsingle_compl.log | none | none |
| results/g4_bearsingle_nothink_strat.log | none | none |
| results/g4_bearsingle_s43.log | none | none |
| results/g4_mono_nothink.log | none | none |
| results/g4_mono_nothink_compl.log | none | none |
| results/g4_mono_nothink_s43.log | none | none |
| results/g4_mono_nothink_strat.log | none | none |
| results/g4_mono_think_compl.log | none | none |
| results/g4_mono_think_s43.log | none | none |
| results/g4_mono_think_strat.log | none | none |
| results/governance_decomposed_output.txt | none | none |
| results/grid_g4-12b_author.txt | none | none |
| results/grid_g4-31b_author.txt | none | none |
| results/logs/alpha_v0110.log | line 163: Traceback (most recent call last): [=== Alpha sweep (qwen3-4b) ===] | none |
| results/logs/backends_v0110.log | none | none |
| results/logs/composite_audit_v0110.log | none | none |
| results/logs/decomposed_v0110.log | none | none |
| results/logs/inferred_v0110.log | none | none |
| results/logs/multitag_v0110.log | none | none |
| results/logs/petsim_diag_v0110.log | none | none |
| results/logs/qtags_top5_v0110.log | none | none |
| results/logs/react_diff_v0110.log | none | none |
| results/logs/retrieval_hash_v0110.log | none | none |
| results/logs/retrieval_semantic_v0110.log | none | none |
| results/logs/top5cats_v0110.log | none | none |
| results/logs/transfer_metatool_v0110.log | none | none |
| results/logs/transfer_toolbench_v0110.log | none | none |
| results/metatool_full_eval_20260626_0453.log | none | none |
| results/metatool_query_tags_top5_generation_20260624_0306.log | none | none |
| results/metatool_query_tags_top5_generation_20260624_0309.log | none | none |
| results/metatool_query_tags_top5_generation_20260624_1429.log | none | none |
| results/metatool_query_tags_top5_resume_20260624_1432.log | none | none |
| results/metatool_querytags_top5_eval_20260624_1453.log | none | none |
| results/metatool_querytags_top5_eval_20260624_1614.log | none | none |
| results/reranker_composition_petsim.log | none | none |
| results/reranker_composition_toolbench.log | none | none |
| results/tool_scaling_v0110.log | none | none |
| results/toolbench_e2e_eval_20260623_2142.log | none | none |
| results/toolbench_e2e_v0110.log | none | none |
| results/toolbench_inferred_full_20260624_0027.log | none | none |
| results/toolbench_inferred_output.txt | none | none |
| results/toolbench_multitag_full_20260624_0140.log | none | none |
| results/toolbench_multitag_output.txt | none | none |
| results/toolbench_multitag_smoke_20260624_0112.log | none | none |
| results/toolbench_react_full_20260624_0222.log | line 10: Traceback (most recent call last): [=== ToolBench end-to-end with ReAct-styl] | none |
| results/toolbench_react_full_20260624_0224.log | line 144: Traceback (most recent call last): [--- Tool selection accuracy (1 if predic] | none |
| results/toolbench_react_full_20260624_0230.log | none | none |
| results/toolbench_react_full_20260624_0235.log | none | none |
| results/toolbench_react_full_20260624_0239.log | none | none |
| results/toolbench_react_full_20260624_0243.log | none | none |
| results/toolbench_react_full_20260624_0249.log | none | none |
| results/toolbench_react_full_20260624_0756.log | none | none |
| results/toolbench_react_output.txt | none | none |
| results/toolbench_react_output_g4-bear-compl_partial.txt | none | none |
| results/toolbench_react_output_g4-bear-s43_partial.txt | none | none |
| results/toolbench_react_output_g4-bear-strat_partial.txt | none | none |
| results/toolbench_react_output_g4-bearsingle-nothink-compl_partial.txt | none | none |
| results/toolbench_react_output_g4-bearsingle-nothink-s43_partial.txt | none | none |
| results/toolbench_react_output_g4-bearsingle-nothink-strat_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-nothink-compl_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-nothink-s43_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-nothink-strat_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-think-compl_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-think-s43_partial.txt | none | none |
| results/toolbench_react_output_g4-mono-think-strat_partial.txt | none | none |
| results/toolbench_react_output_gemma4-31b-bear_partial.txt | none | none |
| results/toolbench_react_output_gemma4-31b-mono-nothink_partial.txt | none | none |
| results/toolbench_react_output_gemma4-31b-reason_partial.txt | none | none |
| results/toolbench_top5_full_20260624_0221.log | none | none |
| results/toolbench_top5_output.txt | none | none |

This run's 0.1.10 control logs scanned: 35. With a load failure or fallback: 2.
