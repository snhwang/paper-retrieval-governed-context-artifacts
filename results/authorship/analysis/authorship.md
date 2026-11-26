# Authorship ablation: Sonnet 4.6 against the second tagger

Second tagger's files: `/home/snhwang/tist-repro/authorship/tags`. Runs: `/home/snhwang/tist-repro/wp0/stage/v042`.

## Agreement

- **tool_tags**: n_both 199, n_sonnet 199, n_regen 199, exact_set_agreement 0.568 [0.497, 0.638], jaccard 0.790 [0.754, 0.825], first_tag_agreement 0.879 [0.834, 0.925], first_tag_kappa 0.868
- **query_tags_top5**: n_both 21041, n_sonnet 21041, n_regen 21041, first_tag_agreement 0.859 [0.854, 0.863], jaccard 0.704 [0.702, 0.706]
- **toolbench_top1**: n_both 1100, vocabulary_size 47, accuracy_vs_gold_sonnet 0.465 [0.435, 0.495], oov_sonnet 6, accuracy_vs_gold_regen 0.424 [0.395, 0.453], oov_regen 10, tagger_agreement 0.770 [0.745, 0.795]
- **toolbench_multi**: n_both 1100, vocabulary_size 47, contains_gold_primary_sonnet 0.804 [0.780, 0.826], mean_set_size_sonnet 3.815, contains_gold_primary_regen 0.640 [0.611, 0.668], mean_set_size_regen 2.145, jaccard_between_taggers 0.530 [0.517, 0.544]
- **toolbench_top5**: n_both 1100, vocabulary_size 47, contains_gold_primary_sonnet 0.848 [0.826, 0.869], mean_set_size_sonnet 4.999, contains_gold_primary_regen 0.808 [0.785, 0.831], mean_set_size_regen 4.923, jaccard_between_taggers 0.602 [0.590, 0.614]
- tool_tags_kappa_mean: 0.851
- query_tags_kappa_mean: 0.748
- toolbench_top1_kappa: 0.758
- toolbench_multi_kappa_per_category_mean: 0.680
- toolbench_top5_kappa_per_category_mean: 0.728

## Retrieval under each tagger

| Backend | Condition | Metric | Governed, Sonnet | Governed, second | Second minus Sonnet [95% CI], p | Effect, Sonnet | Effect, second | Effect difference [95% CI], p |
|---|---|---|---|---|---|---|---|---|
| BGE | MetaTool+Tags | recall@5 | 0.981 [0.979, 0.983] | 0.984 [0.983, 0.986] | +0.003 [+0.002, +0.005], p 0.0001 | +0.258 (d 0.59) | +0.262 (d 0.60) | +0.004 [+0.002, +0.007], p 0.0001 |
| BGE | MetaTool+Tags | ndcg@5 | 0.903 [0.900, 0.906] | 0.898 [0.895, 0.901] | -0.005 [-0.007, -0.003], p 0.0001 | +0.298 (d 0.82) | +0.293 (d 0.82) | -0.004 [-0.007, -0.002], p 0.0001 |
| BGE | MetaTool+QueryTags-top5 | recall@5 | 0.668 [0.661, 0.674] | 0.626 [0.620, 0.633] | -0.041 [-0.047, -0.035], p 0.0001 | -0.056 (d -0.12) | -0.096 (d -0.18) | -0.040 [-0.046, -0.034], p 0.0001 |
| BGE | MetaTool+QueryTags-top5 | ndcg@5 | 0.563 [0.558, 0.569] | 0.542 [0.535, 0.548] | -0.022 [-0.027, -0.017], p 0.0001 | -0.042 (d -0.11) | -0.063 (d -0.15) | -0.021 [-0.026, -0.016], p 0.0001 |
| BGE-M3 | MetaTool+Tags | recall@5 | 0.972 [0.970, 0.975] | 0.982 [0.981, 0.984] | +0.010 [+0.008, +0.012], p 0.0001 | +0.249 (d 0.58) | +0.255 (d 0.59) | +0.007 [+0.005, +0.009], p 0.0001 |
| BGE-M3 | MetaTool+Tags | ndcg@5 | 0.889 [0.886, 0.892] | 0.899 [0.896, 0.902] | +0.009 [+0.008, +0.011], p 0.0001 | +0.276 (d 0.77) | +0.284 (d 0.78) | +0.008 [+0.006, +0.010], p 0.0001 |
| BGE-M3 | MetaTool+QueryTags-top5 | recall@5 | 0.707 [0.701, 0.713] | 0.651 [0.644, 0.657] | -0.056 [-0.062, -0.050], p 0.0001 | -0.017 (d -0.03) | -0.076 (d -0.14) | -0.059 [-0.065, -0.053], p 0.0001 |
| BGE-M3 | MetaTool+QueryTags-top5 | ndcg@5 | 0.624 [0.619, 0.630] | 0.574 [0.567, 0.580] | -0.051 [-0.056, -0.046], p 0.0001 | +0.011 (d 0.03) | -0.042 (d -0.09) | -0.053 [-0.058, -0.047], p 0.0001 |
| Qwen3-0.6B | MetaTool+Tags | recall@5 | 0.976 [0.974, 0.978] | 0.990 [0.988, 0.991] | +0.013 [+0.011, +0.015], p 0.0001 | +0.107 (d 0.34) | +0.119 (d 0.37) | +0.013 [+0.011, +0.015], p 0.0001 |
| Qwen3-0.6B | MetaTool+Tags | ndcg@5 | 0.914 [0.911, 0.917] | 0.929 [0.927, 0.931] | +0.015 [+0.013, +0.017], p 0.0001 | +0.142 (d 0.52) | +0.157 (d 0.55) | +0.015 [+0.013, +0.017], p 0.0001 |
| Qwen3-0.6B | MetaTool+QueryTags-top5 | recall@5 | 0.735 [0.729, 0.741] | 0.667 [0.661, 0.674] | -0.068 [-0.074, -0.062], p 0.0001 | -0.134 (d -0.31) | -0.203 (d -0.42) | -0.069 [-0.074, -0.063], p 0.0001 |
| Qwen3-0.6B | MetaTool+QueryTags-top5 | ndcg@5 | 0.673 [0.668, 0.679] | 0.614 [0.608, 0.620] | -0.059 [-0.065, -0.054], p 0.0001 | -0.099 (d -0.26) | -0.158 (d -0.36) | -0.059 [-0.065, -0.054], p 0.0001 |
| Qwen3-4B | MetaTool+Tags | recall@5 | 0.987 [0.985, 0.988] | 0.994 [0.994, 0.995] | +0.008 [+0.007, +0.009], p 0.0001 | +0.085 (d 0.31) | +0.093 (d 0.32) | +0.008 [+0.007, +0.010], p 0.0001 |
| Qwen3-4B | MetaTool+Tags | ndcg@5 | 0.927 [0.925, 0.930] | 0.942 [0.940, 0.944] | +0.015 [+0.013, +0.016], p 0.0001 | +0.112 (d 0.45) | +0.127 (d 0.48) | +0.015 [+0.013, +0.017], p 0.0001 |
| Qwen3-4B | MetaTool+QueryTags-top5 | recall@5 | 0.749 [0.743, 0.755] | 0.673 [0.667, 0.679] | -0.077 [-0.082, -0.071], p 0.0001 | -0.152 (d -0.35) | -0.229 (d -0.48) | -0.076 [-0.082, -0.070], p 0.0001 |
| Qwen3-4B | MetaTool+QueryTags-top5 | ndcg@5 | 0.699 [0.693, 0.705] | 0.630 [0.624, 0.636] | -0.069 [-0.074, -0.064], p 0.0001 | -0.116 (d -0.30) | -0.185 (d -0.42) | -0.069 [-0.074, -0.063], p 0.0001 |
| BM25 | MetaTool+Tags | recall@5 | 0.911 [0.907, 0.915] | 0.936 [0.932, 0.939] | +0.025 [+0.022, +0.028], p 0.0001 | +0.509 (d 1.02) | +0.534 (d 1.08) | +0.024 [+0.021, +0.028], p 0.0001 |
| BM25 | MetaTool+Tags | ndcg@5 | 0.773 [0.769, 0.777] | 0.794 [0.790, 0.798] | +0.021 [+0.018, +0.023], p 0.0001 | +0.434 (d 1.12) | +0.454 (d 1.18) | +0.020 [+0.018, +0.023], p 0.0001 |
| BM25 | MetaTool+QueryTags-top5 | recall@5 | 0.504 [0.497, 0.511] | 0.514 [0.507, 0.521] | +0.010 [+0.003, +0.016], p 0.0038 | +0.102 (d 0.21) | +0.112 (d 0.19) | +0.010 [+0.003, +0.016], p 0.0044 |
| BM25 | MetaTool+QueryTags-top5 | ndcg@5 | 0.412 [0.406, 0.418] | 0.421 [0.415, 0.427] | +0.009 [+0.003, +0.014], p 0.0008 | +0.073 (d 0.19) | +0.081 (d 0.18) | +0.008 [+0.003, +0.013], p 0.0018 |
| Hash | MetaTool+Tags | recall@5 | 0.736 [0.730, 0.741] | 0.812 [0.807, 0.818] | +0.077 [+0.072, +0.082], p 0.0001 | +0.664 (d 1.41) | +0.741 (d 1.70) | +0.077 [+0.072, +0.082], p 0.0001 |
| Hash | MetaTool+Tags | ndcg@5 | 0.530 [0.525, 0.535] | 0.599 [0.594, 0.604] | +0.068 [+0.065, +0.072], p 0.0001 | +0.485 (d 1.30) | +0.554 (d 1.54) | +0.068 [+0.065, +0.072], p 0.0001 |
| Hash | MetaTool+QueryTags-top5 | recall@5 | 0.290 [0.284, 0.296] | 0.373 [0.366, 0.379] | +0.083 [+0.076, +0.089], p 0.0001 | +0.219 (d 0.48) | +0.302 (d 0.60) | +0.083 [+0.076, +0.090], p 0.0001 |
| Hash | MetaTool+QueryTags-top5 | ndcg@5 | 0.187 [0.182, 0.191] | 0.248 [0.243, 0.253] | +0.061 [+0.057, +0.066], p 0.0001 | +0.141 (d 0.47) | +0.203 (d 0.58) | +0.061 [+0.057, +0.066], p 0.0001 |
| Nemotron | MetaTool+Tags | recall@5 | 0.986 [0.984, 0.987] | 0.987 [0.985, 0.988] | +0.001 [-0.001, +0.002], p 0.29 | +0.182 (d 0.47) | +0.187 (d 0.48) | +0.005 [+0.002, +0.007], p 0.0001 |
| Nemotron | MetaTool+Tags | ndcg@5 | 0.931 [0.929, 0.934] | 0.930 [0.928, 0.932] | -0.001 [-0.003, +0.000], p 0.12 | +0.242 (d 0.69) | +0.246 (d 0.70) | +0.004 [+0.002, +0.006], p 0.0008 |
| Nemotron | MetaTool+QueryTags-top5 | recall@5 | 0.703 [0.697, 0.709] | 0.648 [0.642, 0.655] | -0.055 [-0.061, -0.049], p 0.0001 | -0.101 (d -0.21) | -0.152 (d -0.29) | -0.051 [-0.057, -0.045], p 0.0001 |
| Nemotron | MetaTool+QueryTags-top5 | ndcg@5 | 0.612 [0.606, 0.618] | 0.575 [0.569, 0.581] | -0.037 [-0.043, -0.032], p 0.0001 | -0.078 (d -0.19) | -0.110 (d -0.24) | -0.032 [-0.038, -0.027], p 0.0001 |

## ToolBench inferred categories (Table 7, BGE)

| Condition | Arm | Recall@5 [95% CI] | NDCG@5 [95% CI] |
|---|---|---|---|
| ToolBench toolbench_top1 | oracle | 0.688 [0.668, 0.709] | 0.651 [0.631, 0.670] |
| ToolBench toolbench_top1 | sonnet | 0.336 [0.311, 0.360] | 0.322 [0.298, 0.345] |
| ToolBench toolbench_top1 | regen | 0.314 [0.290, 0.339] | 0.298 [0.275, 0.322] |
| ToolBench toolbench_top1 | no_gov | 0.574 [0.552, 0.596] | 0.545 [0.524, 0.566] |
| ToolBench toolbench_top1 | regen_vs_sonnet (recall) | -0.022 [-0.039, -0.005], p 0.011, d -0.08 | |
| ToolBench toolbench_top1 | sonnet_vs_no_gov (recall) | -0.238 [-0.264, -0.213], p 0.0001, d -0.55 | |
| ToolBench toolbench_top1 | regen_vs_no_gov (recall) | -0.260 [-0.286, -0.235], p 0.0001, d -0.60 | |
| ToolBench toolbench_multi | oracle | 0.688 [0.668, 0.709] | 0.651 [0.631, 0.670] |
| ToolBench toolbench_multi | sonnet | 0.483 [0.459, 0.507] | 0.458 [0.436, 0.481] |
| ToolBench toolbench_multi | regen | 0.403 [0.379, 0.428] | 0.385 [0.361, 0.408] |
| ToolBench toolbench_multi | no_gov | 0.574 [0.552, 0.596] | 0.545 [0.524, 0.566] |
| ToolBench toolbench_multi | regen_vs_sonnet (recall) | -0.079 [-0.098, -0.061], p 0.0001, d -0.26 | |
| ToolBench toolbench_multi | sonnet_vs_no_gov (recall) | -0.092 [-0.110, -0.073], p 0.0001, d -0.29 | |
| ToolBench toolbench_multi | regen_vs_no_gov (recall) | -0.171 [-0.193, -0.148], p 0.0001, d -0.45 | |
| ToolBench toolbench_top5 | oracle | 0.688 [0.668, 0.709] | 0.651 [0.631, 0.670] |
| ToolBench toolbench_top5 | sonnet | 0.502 [0.478, 0.526] | 0.473 [0.451, 0.496] |
| ToolBench toolbench_top5 | regen | 0.484 [0.460, 0.508] | 0.457 [0.435, 0.479] |
| ToolBench toolbench_top5 | no_gov | 0.574 [0.552, 0.596] | 0.545 [0.524, 0.566] |
| ToolBench toolbench_top5 | regen_vs_sonnet (recall) | -0.018 [-0.032, -0.004], p 0.011, d -0.08 | |
| ToolBench toolbench_top5 | sonnet_vs_no_gov (recall) | -0.072 [-0.090, -0.056], p 0.0001, d -0.25 | |
| ToolBench toolbench_top5 | regen_vs_no_gov (recall) | -0.090 [-0.109, -0.072], p 0.0001, d -0.29 | |
