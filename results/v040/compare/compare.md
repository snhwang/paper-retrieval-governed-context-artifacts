Status counts: changed 26, changed, outside CI 12, identical 100, missing 487, same at 3 dp 4

#### Table 3 (tab:toolbench-results)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.771 [0.753, 0.789] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.738 [0.720, 0.755] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.694 [0.673, 0.715] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.662 [0.642, 0.682] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.756 [0.738, 0.775] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.709 [0.691, 0.727] | n/a |  | missing |  |
| Qwen3-4B (no gov) | recall@5 | 0.681 [0.660, 0.702] | n/a |  | missing |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.640 [0.620, 0.660] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.711 [0.690, 0.732] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.668 [0.648, 0.688] | n/a |  | missing |  |
| BGE-M3 (no gov) | recall@5 | 0.601 [0.578, 0.623] | n/a |  | missing |  |
| BGE-M3 (no gov) | ndcg@5 | 0.570 [0.549, 0.591] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (gov) | recall@5 | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| BEAR+BGE (gov) | ndcg@5 | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| BGE (no gov) | recall@5 | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| BGE (no gov) | ndcg@5 | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BM25 (gov) | recall@5 | 0.612 [0.590, 0.634] | 0.612 [0.590, 0.634] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (gov) | ndcg@5 | 0.584 [0.563, 0.605] | 0.584 [0.563, 0.605] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | recall@5 | 0.468 [0.445, 0.491] | 0.468 [0.445, 0.491] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | ndcg@5 | 0.447 [0.425, 0.469] | 0.447 [0.425, 0.469] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+Hash (gov) | recall@5 | 0.151 [0.134, 0.167] | 0.151 [0.134, 0.167] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (gov) | ndcg@5 | 0.118 [0.104, 0.131] | 0.118 [0.104, 0.131] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | recall@5 | 0.016 [0.011, 0.022] | 0.016 [0.011, 0.022] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | ndcg@5 | 0.013 [0.009, 0.018] | 0.013 [0.009, 0.018] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |

#### Table 5 (tab:metatool-results)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.869 [0.865, 0.874] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.775 [0.770, 0.780] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.871 [0.866, 0.875] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.774 [0.770, 0.779] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.869 [0.865, 0.874] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.775 [0.770, 0.780] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.905 [0.901, 0.908] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.821 [0.817, 0.825] | n/a |  | missing |  |
| Qwen3-4B (no gov) | recall@5 | 0.906 [0.902, 0.909] | n/a |  | missing |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.821 [0.817, 0.825] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.905 [0.901, 0.908] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.821 [0.817, 0.825] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.737 [0.731, 0.743] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.622 [0.617, 0.628] | n/a |  | missing |  |
| BGE-M3 (no gov) | recall@5 | 0.728 [0.722, 0.734] | n/a |  | missing |  |
| BGE-M3 (no gov) | ndcg@5 | 0.614 [0.608, 0.619] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.737 [0.731, 0.743] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.622 [0.617, 0.628] | n/a |  | missing |  |
| BEAR+BGE (gov) | recall@5 | 0.721 [0.715, 0.727] | 0.721 [0.715, 0.727] | +0.0000 | identical | 0 queries differ; step tb_bge |
| BEAR+BGE (gov) | ndcg@5 | 0.601 [0.595, 0.606] | 0.601 [0.595, 0.606] | +0.0000 | identical | 0 queries differ; step tb_bge |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | n/a |  | missing |  |
| BGE (no gov) | ndcg@5 | 0.603 [0.598, 0.609] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | recall@5 | 0.721 [0.715, 0.727] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.601 [0.595, 0.606] | n/a |  | missing |  |
| BEAR+BM25 (gov) | recall@5 | 0.400 [0.393, 0.406] | 0.400 [0.393, 0.406] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (gov) | ndcg@5 | 0.337 [0.331, 0.343] | 0.337 [0.331, 0.343] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | recall@5 | 0.404 [0.397, 0.410] | 0.404 [0.397, 0.410] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | ndcg@5 | 0.341 [0.335, 0.347] | 0.341 [0.335, 0.347] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | recall@5 | 0.400 [0.393, 0.406] | 0.400 [0.393, 0.406] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.337 [0.331, 0.343] | 0.337 [0.331, 0.343] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+Hash (gov) | recall@5 | 0.076 [0.073, 0.080] | 0.076 [0.073, 0.080] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (gov) | ndcg@5 | 0.048 [0.046, 0.051] | 0.048 [0.046, 0.051] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | recall@5 | 0.078 [0.074, 0.081] | 0.078 [0.074, 0.081] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | ndcg@5 | 0.050 [0.047, 0.052] | 0.050 [0.047, 0.052] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | recall@5 | 0.076 [0.073, 0.080] | 0.076 [0.073, 0.080] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | ndcg@5 | 0.048 [0.046, 0.051] | 0.048 [0.046, 0.051] | +0.0000 | identical | 0 queries differ; step tb_hash |

#### Table 6 (tab:metatool-tags-results) +Tags

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.976 [0.974, 0.978] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.914 [0.911, 0.917] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.870 [0.865, 0.874] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.772 [0.768, 0.777] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.986 [0.985, 0.988] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.928 [0.925, 0.930] | n/a |  | missing |  |
| Qwen3-4B (no gov) | recall@5 | 0.902 [0.898, 0.906] | n/a |  | missing |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.816 [0.812, 0.820] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.972 [0.970, 0.975] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.889 [0.886, 0.892] | n/a |  | missing |  |
| BGE-M3 (no gov) | recall@5 | 0.724 [0.718, 0.730] | n/a |  | missing |  |
| BGE-M3 (no gov) | ndcg@5 | 0.613 [0.608, 0.619] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (gov) | recall@5 | 0.981 [0.980, 0.983] | 0.981 [0.979, 0.983] | -0.0001 | same at 3 dp | 30 queries differ; step tb_bge |
| BEAR+BGE (gov) | ndcg@5 | 0.903 [0.900, 0.906] | 0.903 [0.900, 0.906] | -0.0001 | same at 3 dp | 30 queries differ; step tb_bge |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | n/a |  | missing |  |
| BGE (no gov) | ndcg@5 | 0.605 [0.600, 0.611] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BM25 (gov) | recall@5 | 0.911 [0.907, 0.915] | 0.911 [0.907, 0.915] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (gov) | ndcg@5 | 0.773 [0.769, 0.777] | 0.773 [0.769, 0.777] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | recall@5 | 0.402 [0.395, 0.409] | 0.402 [0.395, 0.409] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | ndcg@5 | 0.339 [0.333, 0.345] | 0.339 [0.333, 0.345] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+Hash (gov) | recall@5 | 0.736 [0.730, 0.742] | 0.736 [0.730, 0.742] | +0.0000 | same at 3 dp | 63 queries differ; step tb_hash |
| BEAR+Hash (gov) | ndcg@5 | 0.531 [0.526, 0.536] | 0.531 [0.526, 0.536] | -0.0001 | same at 3 dp | 63 queries differ; step tb_hash |
| Hash (no gov) | recall@5 | 0.071 [0.068, 0.075] | 0.071 [0.068, 0.075] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | ndcg@5 | 0.045 [0.043, 0.048] | 0.045 [0.043, 0.048] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |

#### Table 6 (tab:metatool-tags-results) +QueryTags

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.735 [0.729, 0.741] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.673 [0.668, 0.679] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.870 [0.865, 0.874] | n/a |  | missing |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.772 [0.768, 0.777] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.749 [0.744, 0.755] | n/a |  | missing |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.699 [0.693, 0.705] | n/a |  | missing |  |
| Qwen3-4B (no gov) | recall@5 | 0.902 [0.898, 0.906] | n/a |  | missing |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.816 [0.811, 0.820] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.707 [0.701, 0.713] | n/a |  | missing |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.624 [0.619, 0.630] | n/a |  | missing |  |
| BGE-M3 (no gov) | recall@5 | 0.724 [0.718, 0.730] | n/a |  | missing |  |
| BGE-M3 (no gov) | ndcg@5 | 0.613 [0.608, 0.619] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (gov) | recall@5 | 0.668 [0.661, 0.674] | 0.668 [0.661, 0.674] | +0.0000 | identical | 0 queries differ; step tb_bge |
| BEAR+BGE (gov) | ndcg@5 | 0.563 [0.558, 0.569] | 0.563 [0.558, 0.569] | +0.0000 | identical | 0 queries differ; step tb_bge |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | n/a |  | missing |  |
| BGE (no gov) | ndcg@5 | 0.605 [0.599, 0.611] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |
| BEAR+BM25 (gov) | recall@5 | 0.504 [0.497, 0.511] | 0.504 [0.497, 0.511] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (gov) | ndcg@5 | 0.411 [0.406, 0.417] | 0.411 [0.406, 0.417] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | recall@5 | 0.402 [0.396, 0.409] | 0.402 [0.396, 0.409] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BM25 (no gov) | ndcg@5 | 0.339 [0.333, 0.345] | 0.339 [0.333, 0.345] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_bm25 |
| BEAR+Hash (gov) | recall@5 | 0.290 [0.284, 0.296] | 0.290 [0.284, 0.296] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (gov) | ndcg@5 | 0.187 [0.182, 0.191] | 0.187 [0.182, 0.191] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | recall@5 | 0.071 [0.068, 0.075] | 0.071 [0.068, 0.075] | +0.0000 | identical | 0 queries differ; step tb_hash |
| Hash (no gov) | ndcg@5 | 0.045 [0.043, 0.048] | 0.045 [0.043, 0.048] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | 0 queries differ; step tb_hash |

#### Table 4 (tab:toolbench-inferred)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| top-1: oracle | recall@5 | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| top-1: oracle | ndcg@5 | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| top-1: oracle | f1@5 | 0.422 [0.409, 0.434] | n/a |  | missing |  |
| top-1: inferred | recall@5 | 0.336 [0.311, 0.360] | n/a |  | missing |  |
| top-1: inferred | ndcg@5 | 0.322 [0.298, 0.345] | n/a |  | missing |  |
| top-1: inferred | f1@5 | 0.206 [0.191, 0.221] | n/a |  | missing |  |
| top-1: no_governance | recall@5 | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| top-1: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| top-1: no_governance | f1@5 | 0.351 [0.338, 0.365] | n/a |  | missing |  |
| multi: oracle | recall@5 | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| multi: oracle | ndcg@5 | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| multi: oracle | f1@5 | 0.422 [0.409, 0.434] | n/a |  | missing |  |
| multi: inferred_multi | recall@5 | 0.483 [0.459, 0.507] | n/a |  | missing |  |
| multi: inferred_multi | ndcg@5 | 0.458 [0.436, 0.481] | n/a |  | missing |  |
| multi: inferred_multi | f1@5 | 0.296 [0.281, 0.311] | n/a |  | missing |  |
| multi: no_governance | recall@5 | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| multi: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| multi: no_governance | f1@5 | 0.351 [0.338, 0.365] | n/a |  | missing |  |
| top-5: oracle | recall@5 | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| top-5: oracle | ndcg@5 | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| top-5: oracle | f1@5 | 0.422 [0.409, 0.434] | n/a |  | missing |  |
| top-5: inferred_top5 | recall@5 | 0.502 [0.478, 0.526] | n/a |  | missing |  |
| top-5: inferred_top5 | ndcg@5 | 0.473 [0.451, 0.496] | n/a |  | missing |  |
| top-5: inferred_top5 | f1@5 | 0.306 [0.292, 0.321] | n/a |  | missing |  |
| top-5: no_governance | recall@5 | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| top-5: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| top-5: no_governance | f1@5 | 0.351 [0.338, 0.365] | n/a |  | missing |  |

#### tab:retrieval

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| Full BEAR (Hash) | Strict F1@10 | 0.841 [0.806, 0.873] | 0.845 [0.813, 0.875] | +0.0040 | changed |  |
| Full BEAR (Hash) | Strict R@10 | 0.972 [0.950, 0.992] | 0.978 [0.958, 0.992] | +0.0060 | changed |  |
| Full BEAR (Hash) | Relaxed F1@10 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical |  |
| Full BEAR (Hash) | Relaxed R@10 | 0.890 [0.861, 0.917] | 0.890 [0.861, 0.917] | +0.0000 | identical |  |
| Pure Similarity (Hash) | Strict F1@10 | 0.481 [0.430, 0.532] | 0.707 [0.683, 0.729] | +0.2260 | changed, outside CI |  |
| Pure Similarity (Hash) | Strict R@10 | 0.377 [0.329, 0.425] | 0.607 [0.587, 0.628] | +0.2300 | changed, outside CI |  |
| Pure Similarity (Hash) | Relaxed F1@10 | 0.404 [0.353, 0.456] | 0.594 [0.562, 0.625] | +0.1900 | changed, outside CI |  |
| Pure Similarity (Hash) | Relaxed R@10 | 0.300 [0.254, 0.346] | 0.469 [0.435, 0.504] | +0.1690 | changed, outside CI |  |
| Priority-Heavy (Hash) | Strict F1@10 | 0.843 [0.810, 0.874] | 0.843 [0.810, 0.874] | +0.0000 | identical |  |
| Priority-Heavy (Hash) | Strict R@10 | 0.975 [0.956, 0.992] | 0.975 [0.956, 0.992] | +0.0000 | identical |  |
| Priority-Heavy (Hash) | Relaxed F1@10 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical |  |
| Priority-Heavy (Hash) | Relaxed R@10 | 0.890 [0.861, 0.917] | 0.890 [0.861, 0.917] | +0.0000 | identical |  |
| Full BEAR (BGE) | Strict F1@10 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0150 | changed |  |
| Full BEAR (BGE) | Strict R@10 | 0.958 [0.928, 0.983] | 0.978 [0.964, 0.992] | +0.0200 | changed |  |
| Full BEAR (BGE) | Relaxed F1@10 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical |  |
| Full BEAR (BGE) | Relaxed R@10 | 0.963 [0.944, 0.980] | 0.963 [0.944, 0.980] | +0.0000 | identical |  |
| Pure Similarity (BGE) | Strict F1@10 | 0.155 [0.111, 0.202] | 0.496 [0.480, 0.513] | +0.3410 | changed, outside CI |  |
| Pure Similarity (BGE) | Strict R@10 | 0.123 [0.087, 0.160] | 0.642 [0.618, 0.668] | +0.5190 | changed, outside CI |  |
| Pure Similarity (BGE) | Relaxed F1@10 | 0.214 [0.166, 0.262] | 0.514 [0.483, 0.544] | +0.3000 | changed, outside CI |  |
| Pure Similarity (BGE) | Relaxed R@10 | 0.157 [0.121, 0.195] | 0.578 [0.533, 0.621] | +0.4210 | changed, outside CI |  |
| Priority-Heavy (BGE) | Strict F1@10 | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical |  |
| Priority-Heavy (BGE) | Strict R@10 | 0.953 [0.922, 0.981] | 0.953 [0.922, 0.981] | +0.0000 | identical |  |
| Priority-Heavy (BGE) | Relaxed F1@10 | 0.788 [0.759, 0.816] | 0.788 [0.759, 0.816] | +0.0000 | identical |  |
| Priority-Heavy (BGE) | Relaxed R@10 | 0.958 [0.938, 0.977] | 0.958 [0.938, 0.977] | +0.0000 | identical |  |

#### tab:governance-ablation

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| Full governance / BM25 | Standard | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| Full governance / Hash | Standard | 0.841 [0.806, 0.873] | n/a |  | missing |  |
| Full governance / BGE-base | Standard | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| Full governance / BGE-M3 | Standard | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| Full governance / Qwen3-0.6B | Standard | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| Full governance / Qwen3-4B | Standard | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| Full governance / ITR | Standard | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Full governance / Random-k | Standard | 0.116 [0.114, 0.119] | n/a |  | missing |  |
| Full governance / BM25 | Paraphrase | 0.890 [0.867, 0.912] | n/a |  | missing |  |
| Full governance / Hash | Paraphrase | 0.886 [0.865, 0.907] | n/a |  | missing |  |
| Full governance / BGE-base | Paraphrase | 0.637 [0.627, 0.648] | n/a |  | missing |  |
| Full governance / BGE-M3 | Paraphrase | 0.637 [0.627, 0.648] | n/a |  | missing |  |
| Full governance / Qwen3-0.6B | Paraphrase | 0.637 [0.627, 0.648] | n/a |  | missing |  |
| Full governance / Qwen3-4B | Paraphrase | 0.637 [0.627, 0.648] | n/a |  | missing |  |
| Full governance / ITR | Paraphrase | 0.058 [0.039, 0.078] | n/a |  | missing |  |
| Full governance / Random-k | Paraphrase | 0.102 [0.100, 0.104] | n/a |  | missing |  |
| Full governance / BM25 | No-tag | 0.718 [0.692, 0.745] | n/a |  | missing |  |
| Full governance / Hash | No-tag | 0.837 [0.813, 0.862] | n/a |  | missing |  |
| Full governance / BGE-base | No-tag | 0.701 [0.684, 0.718] | n/a |  | missing |  |
| Full governance / BGE-M3 | No-tag | 0.789 [0.764, 0.813] | n/a |  | missing |  |
| Full governance / Qwen3-0.6B | No-tag | 0.715 [0.696, 0.736] | n/a |  | missing |  |
| Full governance / Qwen3-4B | No-tag | 0.743 [0.718, 0.767] | n/a |  | missing |  |
| Full governance / ITR | No-tag | 0.153 [0.130, 0.178] | n/a |  | missing |  |
| Full governance / Random-k | No-tag | 0.097 [0.095, 0.098] | n/a |  | missing |  |
| Full governance / BM25 | Complex | 0.856 [0.820, 0.890] | n/a |  | missing |  |
| Full governance / Hash | Complex | 0.891 [0.860, 0.921] | n/a |  | missing |  |
| Full governance / BGE-base | Complex | 0.664 [0.642, 0.684] | n/a |  | missing |  |
| Full governance / BGE-M3 | Complex | 0.662 [0.640, 0.682] | n/a |  | missing |  |
| Full governance / Qwen3-0.6B | Complex | 0.662 [0.640, 0.682] | n/a |  | missing |  |
| Full governance / Qwen3-4B | Complex | 0.664 [0.642, 0.684] | n/a |  | missing |  |
| Full governance / ITR | Complex | 0.161 [0.132, 0.190] | n/a |  | missing |  |
| Full governance / Random-k | Complex | 0.115 [0.111, 0.118] | n/a |  | missing |  |
| Mandatory only / BM25 | Standard | 0.478 [0.451, 0.504] | n/a |  | missing |  |
| Mandatory only / Hash | Standard | 0.431 [0.402, 0.459] | n/a |  | missing |  |
| Mandatory only / BGE-base | Standard | 0.522 [0.501, 0.541] | n/a |  | missing |  |
| Mandatory only / BGE-M3 | Standard | 0.538 [0.521, 0.555] | n/a |  | missing |  |
| Mandatory only / Qwen3-0.6B | Standard | 0.518 [0.495, 0.540] | n/a |  | missing |  |
| Mandatory only / Qwen3-4B | Standard | 0.540 [0.518, 0.561] | n/a |  | missing |  |
| Mandatory only / ITR | Standard | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Mandatory only / Random-k | Standard | 0.116 [0.114, 0.119] | n/a |  | missing |  |
| Mandatory only / BM25 | Paraphrase | 0.384 [0.350, 0.418] | n/a |  | missing |  |
| Mandatory only / Hash | Paraphrase | 0.416 [0.388, 0.444] | n/a |  | missing |  |
| Mandatory only / BGE-base | Paraphrase | 0.439 [0.424, 0.454] | n/a |  | missing |  |
| Mandatory only / BGE-M3 | Paraphrase | 0.462 [0.446, 0.480] | n/a |  | missing |  |
| Mandatory only / Qwen3-0.6B | Paraphrase | 0.418 [0.400, 0.435] | n/a |  | missing |  |
| Mandatory only / Qwen3-4B | Paraphrase | 0.458 [0.436, 0.480] | n/a |  | missing |  |
| Mandatory only / ITR | Paraphrase | 0.058 [0.039, 0.078] | n/a |  | missing |  |
| Mandatory only / Random-k | Paraphrase | 0.102 [0.100, 0.104] | n/a |  | missing |  |
| Mandatory only / BM25 | No-tag | 0.378 [0.342, 0.413] | n/a |  | missing |  |
| Mandatory only / Hash | No-tag | 0.447 [0.423, 0.473] | n/a |  | missing |  |
| Mandatory only / BGE-base | No-tag | 0.451 [0.439, 0.464] | n/a |  | missing |  |
| Mandatory only / BGE-M3 | No-tag | 0.432 [0.430, 0.435] | n/a |  | missing |  |
| Mandatory only / Qwen3-0.6B | No-tag | 0.451 [0.434, 0.467] | n/a |  | missing |  |
| Mandatory only / Qwen3-4B | No-tag | 0.440 [0.429, 0.452] | n/a |  | missing |  |
| Mandatory only / ITR | No-tag | 0.153 [0.130, 0.178] | n/a |  | missing |  |
| Mandatory only / Random-k | No-tag | 0.097 [0.095, 0.098] | n/a |  | missing |  |
| Mandatory only / BM25 | Complex | 0.480 [0.447, 0.512] | n/a |  | missing |  |
| Mandatory only / Hash | Complex | 0.405 [0.378, 0.432] | n/a |  | missing |  |
| Mandatory only / BGE-base | Complex | 0.508 [0.489, 0.528] | n/a |  | missing |  |
| Mandatory only / BGE-M3 | Complex | 0.528 [0.510, 0.546] | n/a |  | missing |  |
| Mandatory only / Qwen3-0.6B | Complex | 0.490 [0.457, 0.522] | n/a |  | missing |  |
| Mandatory only / Qwen3-4B | Complex | 0.539 [0.516, 0.561] | n/a |  | missing |  |
| Mandatory only / ITR | Complex | 0.161 [0.132, 0.190] | n/a |  | missing |  |
| Mandatory only / Random-k | Complex | 0.115 [0.111, 0.118] | n/a |  | missing |  |
| No governance / BM25 | Standard | 0.249 [0.219, 0.282] | n/a |  | missing |  |
| No governance / Hash | Standard | 0.304 [0.277, 0.332] | n/a |  | missing |  |
| No governance / BGE-base | Standard | 0.155 [0.134, 0.178] | n/a |  | missing |  |
| No governance / BGE-M3 | Standard | 0.160 [0.141, 0.178] | n/a |  | missing |  |
| No governance / Qwen3-0.6B | Standard | 0.209 [0.189, 0.229] | n/a |  | missing |  |
| No governance / Qwen3-4B | Standard | 0.230 [0.206, 0.254] | n/a |  | missing |  |
| No governance / ITR | Standard | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| No governance / Random-k | Standard | 0.116 [0.114, 0.119] | n/a |  | missing |  |
| No governance / BM25 | Paraphrase | 0.117 [0.088, 0.146] | n/a |  | missing |  |
| No governance / Hash | Paraphrase | 0.254 [0.225, 0.284] | n/a |  | missing |  |
| No governance / BGE-base | Paraphrase | 0.073 [0.049, 0.097] | n/a |  | missing |  |
| No governance / BGE-M3 | Paraphrase | 0.082 [0.065, 0.099] | n/a |  | missing |  |
| No governance / Qwen3-0.6B | Paraphrase | 0.103 [0.080, 0.127] | n/a |  | missing |  |
| No governance / Qwen3-4B | Paraphrase | 0.127 [0.101, 0.155] | n/a |  | missing |  |
| No governance / ITR | Paraphrase | 0.058 [0.039, 0.078] | n/a |  | missing |  |
| No governance / Random-k | Paraphrase | 0.102 [0.100, 0.104] | n/a |  | missing |  |
| No governance / BM25 | No-tag | 0.201 [0.158, 0.244] | n/a |  | missing |  |
| No governance / Hash | No-tag | 0.289 [0.250, 0.330] | n/a |  | missing |  |
| No governance / BGE-base | No-tag | 0.105 [0.075, 0.137] | n/a |  | missing |  |
| No governance / BGE-M3 | No-tag | 0.025 [0.008, 0.048] | n/a |  | missing |  |
| No governance / Qwen3-0.6B | No-tag | 0.132 [0.096, 0.170] | n/a |  | missing |  |
| No governance / Qwen3-4B | No-tag | 0.116 [0.085, 0.149] | n/a |  | missing |  |
| No governance / ITR | No-tag | 0.153 [0.130, 0.178] | n/a |  | missing |  |
| No governance / Random-k | No-tag | 0.097 [0.095, 0.098] | n/a |  | missing |  |
| No governance / BM25 | Complex | 0.232 [0.201, 0.265] | n/a |  | missing |  |
| No governance / Hash | Complex | 0.318 [0.283, 0.352] | n/a |  | missing |  |
| No governance / BGE-base | Complex | 0.144 [0.119, 0.171] | n/a |  | missing |  |
| No governance / BGE-M3 | Complex | 0.148 [0.127, 0.170] | n/a |  | missing |  |
| No governance / Qwen3-0.6B | Complex | 0.226 [0.200, 0.252] | n/a |  | missing |  |
| No governance / Qwen3-4B | Complex | 0.232 [0.205, 0.259] | n/a |  | missing |  |
| No governance / ITR | Complex | 0.161 [0.132, 0.190] | n/a |  | missing |  |
| No governance / Random-k | Complex | 0.115 [0.111, 0.118] | n/a |  | missing |  |

#### tab:token-compare

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| Monolithic | tokens/query | 5029.0 | n/a |  | missing |  |
| Monolithic | instructions | 58.0 | n/a |  | missing |  |
| Role prompting | tokens/query | 46.0 | n/a |  | missing |  |
| Role prompting | instructions | 0.0 | n/a |  | missing |  |
| BEAR + BM25 | tokens/query | 601.0 | n/a |  | missing |  |
| BEAR + BM25 | instructions | 6.5 | n/a |  | missing |  |
| BEAR + Hash | tokens/query | 630.7 | n/a |  | missing |  |
| BEAR + Hash | instructions | 7.0 | n/a |  | missing |  |
| BEAR + BGE-base | tokens/query | 839.8 | n/a |  | missing |  |
| BEAR + BGE-base | instructions | 9.8 | n/a |  | missing |  |
| BEAR + BGE-M3 | tokens/query | 844.7 | n/a |  | missing |  |
| BEAR + BGE-M3 | instructions | 9.8 | n/a |  | missing |  |
| BEAR + Qwen3-0.6B | tokens/query | 842.7 | n/a |  | missing |  |
| BEAR + Qwen3-0.6B | instructions | 9.8 | n/a |  | missing |  |
| BEAR + Qwen3-4B | tokens/query | 843.7 | n/a |  | missing |  |
| BEAR + Qwen3-4B | instructions | 9.8 | n/a |  | missing |  |
| ITR | tokens/query | 846.3 | n/a |  | missing |  |
| ITR | instructions | 10.0 | n/a |  | missing |  |
| Random-k | tokens/query | 867.6 | n/a |  | missing |  |
| Random-k | instructions | 10.0 | n/a |  | missing |  |

#### tab:governance-ablation (a) via backend_comparison

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| BGE-base | strict_f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed |  |
| BGE-base | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical |  |
| BGE-base | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical |  |
| BGE-base | notag_f1 | 0.701 [0.684, 0.718] | 0.653 [0.642, 0.662] | -0.0482 | changed, outside CI |  |
| BGE-base | complex_f1 | 0.664 [0.642, 0.684] | 0.672 [0.656, 0.688] | +0.0082 | changed |  |
| BGE-base | avg_query_ms | 4.770 | 0.470 | -4.3000 | changed |  |
| Qwen3-0.6B | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed |  |
| Qwen3-0.6B | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical |  |
| Qwen3-0.6B | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical |  |
| Qwen3-0.6B | notag_f1 | 0.715 [0.696, 0.736] | 0.653 [0.642, 0.662] | -0.0623 | changed, outside CI |  |
| Qwen3-0.6B | complex_f1 | 0.662 [0.640, 0.682] | 0.672 [0.656, 0.688] | +0.0103 | changed |  |
| Qwen3-0.6B | avg_query_ms | 20.940 | 6525.370 | +6504.4300 | changed |  |
| Qwen3-4B | strict_f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed |  |
| Qwen3-4B | relaxed_f1 | 0.790 [0.763, 0.817] | 0.790 [0.763, 0.817] | +0.0000 | identical |  |
| Qwen3-4B | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical |  |
| Qwen3-4B | notag_f1 | 0.743 [0.718, 0.767] | 0.653 [0.642, 0.662] | -0.0894 | changed, outside CI |  |
| Qwen3-4B | complex_f1 | 0.664 [0.642, 0.684] | 0.674 [0.658, 0.690] | +0.0102 | changed |  |
| Qwen3-4B | avg_query_ms | 33.950 | 6437.690 | +6403.7400 | changed |  |
| BGE-M3 | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed |  |
| BGE-M3 | relaxed_f1 | 0.790 [0.763, 0.817] | 0.790 [0.763, 0.817] | +0.0000 | identical |  |
| BGE-M3 | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical |  |
| BGE-M3 | notag_f1 | 0.789 [0.764, 0.813] | 0.653 [0.642, 0.662] | -0.1354 | changed, outside CI |  |
| BGE-M3 | complex_f1 | 0.662 [0.640, 0.682] | 0.670 [0.652, 0.687] | +0.0081 | changed |  |
| BGE-M3 | avg_query_ms | 8.670 | 179.420 | +170.7500 | changed |  |
| Hash | strict_f1 | 0.841 [0.806, 0.873] | 0.845 [0.813, 0.875] | +0.0042 | changed |  |
| Hash | relaxed_f1 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical |  |
| Hash | para_f1 | 0.886 [0.865, 0.907] | 0.886 [0.865, 0.907] | +0.0000 | identical |  |
| Hash | notag_f1 | 0.837 [0.813, 0.862] | 0.837 [0.813, 0.862] | +0.0000 | identical |  |
| Hash | complex_f1 | 0.891 [0.860, 0.921] | 0.896 [0.866, 0.923] | +0.0042 | changed |  |
| Hash | avg_query_ms | 0.310 | 0.360 | +0.0500 | changed |  |
| BM25 | strict_f1 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed |  |
| BM25 | relaxed_f1 | 0.922 [0.906, 0.938] | 0.922 [0.906, 0.938] | +0.0000 | identical |  |
| BM25 | para_f1 | 0.890 [0.867, 0.912] | 0.890 [0.867, 0.912] | +0.0000 | identical |  |
| BM25 | notag_f1 | 0.718 [0.692, 0.745] | 0.718 [0.692, 0.745] | +0.0000 | identical |  |
| BM25 | complex_f1 | 0.856 [0.820, 0.890] | 0.866 [0.836, 0.895] | +0.0103 | changed |  |
| BM25 | avg_query_ms | 0.180 | 0.360 | +0.1800 | changed |  |
| ITR-hybrid | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed |  |
| ITR-hybrid | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical |  |
| ITR-hybrid | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical |  |
| ITR-hybrid | notag_f1 | 0.664 [0.650, 0.677] | 0.653 [0.642, 0.662] | -0.0105 | changed |  |
| ITR-hybrid | complex_f1 | 0.655 [0.636, 0.673] | 0.672 [0.656, 0.688] | +0.0166 | changed |  |
| ITR-hybrid | avg_query_ms | 10.720 | 158.040 | +147.3200 | changed |  |
| ITR-standalone | strict_f1 | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical |  |
| ITR-standalone | relaxed_f1 | 0.320 [0.274, 0.369] | 0.320 [0.274, 0.369] | +0.0000 | identical |  |
| ITR-standalone | para_f1 | 0.058 [0.039, 0.078] | 0.058 [0.039, 0.078] | +0.0000 | identical |  |
| ITR-standalone | notag_f1 | 0.153 [0.130, 0.178] | 0.153 [0.130, 0.178] | +0.0000 | identical |  |
| ITR-standalone | complex_f1 | 0.161 [0.132, 0.190] | 0.161 [0.132, 0.190] | +0.0000 | identical |  |
| ITR-standalone | avg_query_ms | 0.000 | 0.000 | +0.0000 | identical |  |
| Random-k | strict_f1 | 0.116 [0.114, 0.118] | 0.116 [0.114, 0.118] | +0.0000 | identical |  |
| Random-k | relaxed_f1 | 0.140 [0.140, 0.134] | 0.140 [0.140, 0.134] | +0.0000 | identical |  |
| Random-k | para_f1 | 0.101 [0.101, 0.099] | 0.101 [0.101, 0.099] | +0.0000 | identical |  |
| Random-k | notag_f1 | 0.097 [0.097, 0.095] | 0.097 [0.097, 0.095] | +0.0000 | identical |  |
| Random-k | complex_f1 | 0.114 [0.114, 0.111] | 0.114 [0.114, 0.111] | +0.0000 | identical |  |
| Random-k | avg_query_ms | 0.000 | 0.000 | +0.0000 | identical |  |

#### tab:decomposed-ablation

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| Full governance | bge | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| - required_tags | bge | 0.522 [0.501, 0.541] | n/a |  | missing |  |
| - priority weighting | bge | 0.563 [0.521, 0.602] | n/a |  | missing |  |
| - conflict resolution | bge | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| - mandatory injection | bge | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| No governance | bge | 0.162 [0.149, 0.177] | n/a |  | missing |  |
| ITR library (off-the-shelf) | bge | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Full governance | bge-m3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| - required_tags | bge-m3 | 0.538 [0.521, 0.555] | n/a |  | missing |  |
| - priority weighting | bge-m3 | 0.569 [0.532, 0.604] | n/a |  | missing |  |
| - conflict resolution | bge-m3 | 0.655 [0.636, 0.673] | n/a |  | missing |  |
| - mandatory injection | bge-m3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| No governance | bge-m3 | 0.175 [0.161, 0.190] | n/a |  | missing |  |
| ITR library (off-the-shelf) | bge-m3 | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Full governance | qwen3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| - required_tags | qwen3 | 0.518 [0.495, 0.540] | n/a |  | missing |  |
| - priority weighting | qwen3 | 0.580 [0.547, 0.612] | n/a |  | missing |  |
| - conflict resolution | qwen3 | 0.655 [0.636, 0.673] | n/a |  | missing |  |
| - mandatory injection | qwen3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| No governance | qwen3 | 0.197 [0.180, 0.215] | n/a |  | missing |  |
| ITR library (off-the-shelf) | qwen3 | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Full governance | qwen3-4b | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| - required_tags | qwen3-4b | 0.540 [0.518, 0.561] | n/a |  | missing |  |
| - priority weighting | qwen3-4b | 0.599 [0.569, 0.627] | n/a |  | missing |  |
| - conflict resolution | qwen3-4b | 0.655 [0.636, 0.673] | n/a |  | missing |  |
| - mandatory injection | qwen3-4b | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| No governance | qwen3-4b | 0.221 [0.206, 0.237] | n/a |  | missing |  |
| ITR library (off-the-shelf) | qwen3-4b | 0.182 [0.162, 0.203] | n/a |  | missing |  |
| Full governance | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| - required_tags | bm25 | 0.478 [0.451, 0.504] | n/a |  | missing |  |
| - priority weighting | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| - conflict resolution | bm25 | 0.859 [0.818, 0.896] | n/a |  | missing |  |
| - mandatory injection | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| No governance | bm25 | 0.204 [0.186, 0.224] | n/a |  | missing |  |
| ITR library (off-the-shelf) | bm25 | 0.211 [0.186, 0.237] | n/a |  | missing |  |

#### tab:alpha-sweep

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| alpha=0.00 | bge | 0.563 [0.521, 0.602] | n/a |  | missing |  |
| alpha=0.10 | bge | 0.589 [0.555, 0.620] | n/a |  | missing |  |
| alpha=0.20 | bge | 0.624 [0.603, 0.645] | n/a |  | missing |  |
| alpha=0.30 | bge | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.50 | bge | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.70 | bge | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.90 | bge | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=1.00 | bge | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.00 | bge-m3 | 0.569 [0.532, 0.604] | n/a |  | missing |  |
| alpha=0.10 | bge-m3 | 0.586 [0.554, 0.617] | n/a |  | missing |  |
| alpha=0.20 | bge-m3 | 0.631 [0.610, 0.651] | n/a |  | missing |  |
| alpha=0.30 | bge-m3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.50 | bge-m3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.70 | bge-m3 | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.90 | bge-m3 | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=1.00 | bge-m3 | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.00 | qwen3 | 0.580 [0.547, 0.612] | n/a |  | missing |  |
| alpha=0.10 | qwen3 | 0.612 [0.585, 0.637] | n/a |  | missing |  |
| alpha=0.20 | qwen3 | 0.644 [0.625, 0.663] | n/a |  | missing |  |
| alpha=0.30 | qwen3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.50 | qwen3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.70 | qwen3 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.90 | qwen3 | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=1.00 | qwen3 | 0.649 [0.629, 0.667] | n/a |  | missing |  |
| alpha=0.00 | qwen3-4b | 0.599 [0.569, 0.627] | n/a |  | missing |  |
| alpha=0.10 | qwen3-4b | 0.614 [0.588, 0.639] | n/a |  | missing |  |
| alpha=0.20 | qwen3-4b | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.30 | qwen3-4b | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.50 | qwen3-4b | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| alpha=0.70 | qwen3-4b | 0.843 [0.810, 0.874] | n/a |  | missing |  |
| alpha=0.90 | qwen3-4b | 0.830 [0.791, 0.867] | n/a |  | missing |  |
| alpha=1.00 | qwen3-4b | 0.830 [0.791, 0.867] | n/a |  | missing |  |
| alpha=0.00 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.10 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.20 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.30 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.50 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.70 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=0.90 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |
| alpha=1.00 | bm25 | 0.865 [0.824, 0.902] | n/a |  | missing |  |

#### tab:tool-scaling

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| 5 | precision | 1.000 | n/a |  | missing |  |
| 5 | recall | 1.000 | n/a |  | missing |  |
| 5 | no_leaks | 1.000 | n/a |  | missing |  |
| 10 | precision | 1.000 | n/a |  | missing |  |
| 10 | recall | 1.000 | n/a |  | missing |  |
| 10 | no_leaks | 1.000 | n/a |  | missing |  |
| 25 | precision | 0.900 | n/a |  | missing |  |
| 25 | recall | 1.000 | n/a |  | missing |  |
| 25 | no_leaks | 1.000 | n/a |  | missing |  |
| 50 | precision | 0.912 | n/a |  | missing |  |
| 50 | recall | 1.000 | n/a |  | missing |  |
| 50 | no_leaks | 1.000 | n/a |  | missing |  |

#### tab:token-savings

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| Predator attack | tools | 4.000 | n/a |  | missing |  |
| Predator attack | tokens | 214.0 | n/a |  | missing |  |
| Predator attack | savings% | 93.000 | n/a |  | missing |  |
| Social encounter | tools | 7.000 | n/a |  | missing |  |
| Social encounter | tokens | 450.0 | n/a |  | missing |  |
| Social encounter | savings% | 85.000 | n/a |  | missing |  |
| Hungry near food | tools | 3.000 | n/a |  | missing |  |
| Hungry near food | tokens | 172.0 | n/a |  | missing |  |
| Hungry near food | savings% | 94.000 | n/a |  | missing |  |
| Building with materials | tools | 3.000 | n/a |  | missing |  |
| Building with materials | tokens | 164.0 | n/a |  | missing |  |
| Building with materials | savings% | 94.000 | n/a |  | missing |  |
| Combat encounter | tools | 6.000 | n/a |  | missing |  |
| Combat encounter | tokens | 346.0 | n/a |  | missing |  |
| Combat encounter | savings% | 88.000 | n/a |  | missing |  |
| Near water | tools | 3.000 | n/a |  | missing |  |
| Near water | tokens | 155.0 | n/a |  | missing |  |
| Near water | savings% | 95.000 | n/a |  | missing |  |
| Item management | tools | 5.000 | n/a |  | missing |  |
| Item management | tokens | 288.0 | n/a |  | missing |  |
| Item management | savings% | 90.000 | n/a |  | missing |  |
| Territory dispute | tools | 10.000 | n/a |  | missing |  |
| Territory dispute | tokens | 629.0 | n/a |  | missing |  |
| Territory dispute | savings% | 79.000 | n/a |  | missing |  |
| All-tools baseline | tokens | 2928.0 | n/a |  | missing |  |
| Average | savings% | 90.000 | n/a |  | missing |  |

#### tab:token-efficiency

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| N=10 | bear_mean_tokens | 952.000 | n/a |  | missing |  |
| N=10 | cpa_mean_tokens | 952.000 | n/a |  | missing |  |
| N=10 | static_tokens | 1454.000 | n/a |  | missing |  |
| N=10 | bear_token_ratio | 0.655 | n/a |  | missing |  |
| N=25 | bear_mean_tokens | 996.000 | n/a |  | missing |  |
| N=25 | cpa_mean_tokens | 952.000 | n/a |  | missing |  |
| N=25 | static_tokens | 2609.000 | n/a |  | missing |  |
| N=25 | bear_token_ratio | 0.382 | n/a |  | missing |  |
| N=50 | bear_mean_tokens | 985.000 | n/a |  | missing |  |
| N=50 | cpa_mean_tokens | 950.000 | n/a |  | missing |  |
| N=50 | static_tokens | 4344.000 | n/a |  | missing |  |
| N=50 | bear_token_ratio | 0.227 | n/a |  | missing |  |
| N=100 | bear_mean_tokens | 995.000 | n/a |  | missing |  |
| N=100 | cpa_mean_tokens | 952.000 | n/a |  | missing |  |
| N=100 | static_tokens | 8021.000 | n/a |  | missing |  |
| N=100 | bear_token_ratio | 0.124 | n/a |  | missing |  |
| N=200 | bear_mean_tokens | 967.000 | n/a |  | missing |  |
| N=200 | cpa_mean_tokens | 946.000 | n/a |  | missing |  |
| N=200 | static_tokens | 14696.000 | n/a |  | missing |  |
| N=200 | bear_token_ratio | 0.066 | n/a |  | missing |  |
| N=500 | bear_mean_tokens | 953.000 | n/a |  | missing |  |
| N=500 | cpa_mean_tokens | 944.000 | n/a |  | missing |  |
| N=500 | static_tokens | 34721.000 | n/a |  | missing |  |
| N=500 | bear_token_ratio | 0.027 | n/a |  | missing |  |

#### novel departments (text)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| N=10 | bear_novel_recall | 0.944 | n/a |  | missing |  |
| N=10 | cpa_novel_recall | 0.888 | n/a |  | missing |  |
| N=25 | bear_novel_recall | 0.956 | n/a |  | missing |  |
| N=25 | cpa_novel_recall | 0.912 | n/a |  | missing |  |
| N=50 | bear_novel_recall | 0.956 | n/a |  | missing |  |
| N=50 | cpa_novel_recall | 0.912 | n/a |  | missing |  |
| N=100 | bear_novel_recall | 1.000 | n/a |  | missing |  |
| N=100 | cpa_novel_recall | 0.912 | n/a |  | missing |  |
| N=200 | bear_novel_recall | 1.000 | n/a |  | missing |  |
| N=200 | cpa_novel_recall | 0.912 | n/a |  | missing |  |
| N=500 | bear_novel_recall | 1.000 | n/a |  | missing |  |
| N=500 | cpa_novel_recall | 0.912 | n/a |  | missing |  |

#### tab:semantic-advantage

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| N=10 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=10 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |
| N=25 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=25 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |
| N=50 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=50 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |
| N=100 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=100 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |
| N=200 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=200 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |
| N=500 | bear_semantic_recall | 1.000 | n/a |  | missing |  |
| N=500 | cpa_semantic_recall | 0.000 | n/a |  | missing |  |

#### standard queries (text)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| N=10 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=10 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=10 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=10 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=10 | bear_scope_violations | 0.000 | n/a |  | missing |  |
| N=25 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=25 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=25 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=25 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=25 | bear_scope_violations | 0.000 | n/a |  | missing |  |
| N=50 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=50 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=50 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=50 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=50 | bear_scope_violations | 0.000 | n/a |  | missing |  |
| N=100 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=100 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=100 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=100 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=100 | bear_scope_violations | 0.000 | n/a |  | missing |  |
| N=200 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=200 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=200 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=200 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=200 | bear_scope_violations | 0.000 | n/a |  | missing |  |
| N=500 | bear_persona_recall | 1.000 | n/a |  | missing |  |
| N=500 | bear_dept_recall | 1.000 | n/a |  | missing |  |
| N=500 | bear_safety_recall | 1.000 | n/a |  | missing |  |
| N=500 | bear_global_recall | 1.000 | n/a |  | missing |  |
| N=500 | bear_scope_violations | 0.000 | n/a |  | missing |  |

#### tab:reranker

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| toolbench: Bi-encoder, no governance | recall | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| toolbench: Bi-encoder, no governance | f1 | 0.351 [0.338, 0.365] | n/a |  | missing |  |
| toolbench: Bi-encoder, no governance | ndcg | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| toolbench: Bi-encoder + cross-encoder reranker | recall | 0.647 [0.625, 0.669] | n/a |  | missing |  |
| toolbench: Bi-encoder + cross-encoder reranker | f1 | 0.397 [0.384, 0.411] | n/a |  | missing |  |
| toolbench: Bi-encoder + cross-encoder reranker | ndcg | 0.617 [0.595, 0.637] | n/a |  | missing |  |
| toolbench: BEAR governed | recall | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| toolbench: BEAR governed | f1 | 0.422 [0.409, 0.434] | n/a |  | missing |  |
| toolbench: BEAR governed | ndcg | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| toolbench: BEAR governed + cross-encoder reranker | recall | 0.742 [0.722, 0.761] | n/a |  | missing |  |
| toolbench: BEAR governed + cross-encoder reranker | f1 | 0.458 [0.445, 0.470] | n/a |  | missing |  |
| toolbench: BEAR governed + cross-encoder reranker | ndcg | 0.708 [0.688, 0.727] | n/a |  | missing |  |
| toolbench: LlamaIndex retriever (released package) | recall | 0.590 [0.568, 0.611] | n/a |  | missing |  |
| toolbench: LlamaIndex retriever (released package) | f1 | 0.361 [0.348, 0.374] | n/a |  | missing |  |
| toolbench: LlamaIndex retriever (released package) | ndcg | 0.560 [0.539, 0.580] | n/a |  | missing |  |
| toolbench: BEAR, no governance (published baseline) | recall | 0.574 [0.552, 0.596] | n/a |  | missing |  |
| toolbench: BEAR, no governance (published baseline) | f1 | 0.351 [0.338, 0.365] | n/a |  | missing |  |
| toolbench: BEAR, no governance (published baseline) | ndcg | 0.545 [0.524, 0.566] | n/a |  | missing |  |
| toolbench: BEAR governed (published row) | recall | 0.688 [0.668, 0.709] | n/a |  | missing |  |
| toolbench: BEAR governed (published row) | f1 | 0.422 [0.409, 0.434] | n/a |  | missing |  |
| toolbench: BEAR governed (published row) | ndcg | 0.651 [0.631, 0.670] | n/a |  | missing |  |
| petsim: Bi-encoder, no governance | recall | 0.247 [0.227, 0.269] | n/a |  | missing |  |
| petsim: Bi-encoder, no governance | f1 | 0.168 [0.152, 0.186] | n/a |  | missing |  |
| petsim: Bi-encoder, no governance | ndcg | 0.347 [0.320, 0.371] | n/a |  | missing |  |
| petsim: Bi-encoder + cross-encoder reranker | recall | 0.322 [0.293, 0.354] | n/a |  | missing |  |
| petsim: Bi-encoder + cross-encoder reranker | f1 | 0.219 [0.198, 0.242] | n/a |  | missing |  |
| petsim: Bi-encoder + cross-encoder reranker | ndcg | 0.375 [0.344, 0.406] | n/a |  | missing |  |
| petsim: BEAR governed | recall | 0.958 [0.928, 0.983] | n/a |  | missing |  |
| petsim: BEAR governed | f1 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| petsim: BEAR governed | ndcg | 0.905 [0.870, 0.937] | n/a |  | missing |  |
| petsim: BEAR governed + cross-encoder reranker | recall | 0.867 [0.815, 0.914] | n/a |  | missing |  |
| petsim: BEAR governed + cross-encoder reranker | f1 | 0.589 [0.555, 0.620] | n/a |  | missing |  |
| petsim: BEAR governed + cross-encoder reranker | ndcg | 0.750 [0.708, 0.789] | n/a |  | missing |  |
| petsim: LlamaIndex retriever (released package) | recall | 0.247 [0.227, 0.267] | n/a |  | missing |  |
| petsim: LlamaIndex retriever (released package) | f1 | 0.168 [0.153, 0.184] | n/a |  | missing |  |
| petsim: LlamaIndex retriever (released package) | ndcg | 0.309 [0.279, 0.338] | n/a |  | missing |  |
| petsim: BEAR, no governance (published baseline) | recall | 0.247 [0.227, 0.269] | n/a |  | missing |  |
| petsim: BEAR, no governance (published baseline) | f1 | 0.168 [0.152, 0.186] | n/a |  | missing |  |
| petsim: BEAR, no governance (published baseline) | ndcg | 0.347 [0.320, 0.371] | n/a |  | missing |  |
| petsim: BEAR governed (published row) | recall | 0.958 [0.928, 0.983] | n/a |  | missing |  |
| petsim: BEAR governed (published row) | f1 | 0.653 [0.634, 0.671] | n/a |  | missing |  |
| petsim: BEAR governed (published row) | ndcg | 0.905 [0.870, 0.937] | n/a |  | missing |  |

#### tab:reranker contrasts

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| toolbench: bear_vs_bi | recall | 0.114 [0.099, 0.130] | n/a |  | missing |  |
| toolbench: bi_rr_vs_bi | recall | 0.073 [0.056, 0.090] | n/a |  | missing |  |
| toolbench: bear_vs_bi_rr | recall | 0.041 [0.022, 0.060] | n/a |  | missing |  |
| toolbench: bear_rr_vs_bear | recall | 0.054 [0.037, 0.069] | n/a |  | missing |  |
| toolbench: bear_rr_vs_bi_rr | recall | 0.095 [0.081, 0.108] | n/a |  | missing |  |
| toolbench: bear_nogov_vs_llamaindex | recall | -0.015 [-0.027, -0.004] | n/a |  | missing |  |
| toolbench: bear_gov_vs_llamaindex | recall | 0.099 [0.083, 0.115] | n/a |  | missing |  |
| petsim: bear_vs_bi | f1 | 0.485 [0.457, 0.510] | n/a |  | missing |  |
| petsim: bi_rr_vs_bi | f1 | 0.051 [0.031, 0.073] | n/a |  | missing |  |
| petsim: bear_vs_bi_rr | f1 | 0.434 [0.406, 0.460] | n/a |  | missing |  |
| petsim: bear_rr_vs_bear | f1 | -0.064 [-0.088, -0.043] | n/a |  | missing |  |
| petsim: bear_rr_vs_bi_rr | f1 | 0.369 [0.327, 0.409] | n/a |  | missing |  |
| petsim: bear_vs_bi__f1_relaxed | f1_relaxed | 0.484 [0.444, 0.521] | n/a |  | missing |  |
| petsim: bi_rr_vs_bi__f1_relaxed | f1_relaxed | 0.031 [0.004, 0.057] | n/a |  | missing |  |
| petsim: bear_vs_bi_rr__f1_relaxed | f1_relaxed | 0.453 [0.421, 0.485] | n/a |  | missing |  |
| petsim: bear_rr_vs_bear__f1_relaxed | f1_relaxed | -0.052 [-0.071, -0.034] | n/a |  | missing |  |
| petsim: bear_rr_vs_bi_rr__f1_relaxed | f1_relaxed | 0.401 [0.360, 0.443] | n/a |  | missing |  |
| petsim: bear_nogov_vs_llamaindex | f1 | 0.000 [-0.011, 0.013] | n/a |  | missing |  |
| petsim: bear_gov_vs_llamaindex | f1 | 0.485 [0.458, 0.511] | n/a |  | missing |  |
| petsim: bear_nogov_vs_llamaindex__f1_relaxed | f1_relaxed | 0.007 [-0.005, 0.019] | n/a |  | missing |  |
| petsim: bear_gov_vs_llamaindex__f1_relaxed | f1_relaxed | 0.490 [0.451, 0.528] | n/a |  | missing |  |

#### tab:transfer

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| ToolBench-IR on toolbench | recall@5 | 0.847 [0.832, 0.862] | 0.847 [0.832, 0.862] | +0.0000 | identical |  |
| ToolBench-IR on toolbench | ndcg@5 | 0.793 [0.778, 0.808] | 0.793 [0.778, 0.808] | +0.0000 | identical |  |
| ToolBench-IR on toolbench | f1@5 | 0.528 [0.517, 0.538] | 0.528 [0.517, 0.538] | +0.0000 | identical |  |
| ToolBench-IR on metatool | recall@5 | 0.648 [0.642, 0.655] | 0.648 [0.642, 0.655] | +0.0000 | identical |  |
| ToolBench-IR on metatool | ndcg@5 | 0.553 [0.547, 0.559] | 0.553 [0.547, 0.559] | +0.0000 | identical |  |
| ToolBench-IR on metatool | f1@5 | 0.219 [0.217, 0.221] | 0.219 [0.217, 0.221] | +0.0000 | identical |  |

#### ToolBench-IR + governance (Sec. 6.3 text)

| Row | Column | 0.1.10 (published) | 0.4.0 | Δ | Status | Notes |
|---|---|---|---|---|---|---|
| ToolBench-IR alone (no governance) | recall@5 | 0.847 [0.832, 0.862] | 0.847 [0.832, 0.862] | +0.0000 | identical |  |
| ToolBench-IR alone (no governance) | ndcg@5 | 0.793 [0.778, 0.808] | 0.793 [0.778, 0.808] | +0.0000 | identical |  |
| BEAR governance + ToolBench-IR (oracle categories) | recall@5 | 0.842 [0.826, 0.858] | 0.842 [0.826, 0.858] | +0.0000 | identical |  |
| BEAR governance + ToolBench-IR (oracle categories) | ndcg@5 | 0.789 [0.773, 0.805] | 0.789 [0.773, 0.805] | +0.0000 | identical |  |