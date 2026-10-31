Status counts: changed 86, changed, outside CI 48, identical 435, missing 24, same at 3 dp 33

#### Table 3

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.771 [0.753, 0.789] | 0.771 [0.753, 0.789] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.738 [0.720, 0.755] | 0.738 [0.720, 0.755] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.694 [0.673, 0.715] | 0.694 [0.673, 0.715] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.662 [0.642, 0.682] | 0.662 [0.642, 0.682] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.756 [0.738, 0.775] | 0.754 [0.735, 0.772] | -0.0024 | changed (65 q) | 0.754 |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.709 [0.691, 0.727] | 0.706 [0.688, 0.724] | -0.0025 | changed (65 q) | 0.706 |  |
| Qwen3-4B (no gov) | recall@5 | 0.681 [0.660, 0.702] | 0.681 [0.660, 0.703] | +0.0005 | same at 3 dp (57 q) | 0.681 |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.640 [0.620, 0.660] | 0.640 [0.620, 0.660] | -0.0004 | same at 3 dp (57 q) | 0.640 |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.711 [0.690, 0.732] | 0.711 [0.690, 0.732] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.668 [0.648, 0.688] | 0.668 [0.648, 0.688] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | recall@5 | 0.601 [0.578, 0.623] | 0.601 [0.578, 0.623] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | ndcg@5 | 0.570 [0.549, 0.591] | 0.570 [0.549, 0.591] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | recall@5 | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | ndcg@5 | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | recall@5 | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | ndcg@5 | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (gov) | recall@5 | 0.612 [0.590, 0.634] | 0.612 [0.590, 0.634] | -0.0003 | same at 3 dp (7 q) | reproduces | all, tie_order |
| BEAR+BM25 (gov) | ndcg@5 | 0.584 [0.563, 0.605] | 0.584 [0.563, 0.605] | +0.0004 | same at 3 dp (7 q) | reproduces | all, tie_order |
| BM25 (no gov) | recall@5 | 0.468 [0.445, 0.491] | 0.468 [0.445, 0.491] | -0.0005 | same at 3 dp (7 q) | reproduces | all |
| BM25 (no gov) | ndcg@5 | 0.447 [0.425, 0.469] | 0.447 [0.425, 0.469] | -0.0003 | same at 3 dp (7 q) | reproduces | all |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | recall@5 | 0.151 [0.134, 0.167] | 0.151 [0.134, 0.167] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | ndcg@5 | 0.118 [0.104, 0.131] | 0.118 [0.104, 0.131] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | recall@5 | 0.016 [0.011, 0.022] | 0.016 [0.011, 0.022] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | ndcg@5 | 0.013 [0.009, 0.018] | 0.013 [0.009, 0.018] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Nemotron (gov) | recall@5 | n/a | 0.762 [0.742, 0.781] |  | missing |  |  |
| BEAR+Nemotron (gov) | ndcg@5 | n/a | 0.722 [0.703, 0.740] |  | missing |  |  |
| Nemotron (no gov) | recall@5 | n/a | 0.668 [0.647, 0.690] |  | missing |  |  |
| Nemotron (no gov) | ndcg@5 | n/a | 0.631 [0.610, 0.651] |  | missing |  |  |

#### Table 5

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.869 [0.865, 0.874] | 0.869 [0.865, 0.874] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.775 [0.770, 0.780] | 0.775 [0.770, 0.780] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.871 [0.866, 0.875] | 0.871 [0.866, 0.875] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.774 [0.770, 0.779] | 0.774 [0.770, 0.779] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.869 [0.865, 0.874] | 0.869 [0.865, 0.874] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.775 [0.770, 0.780] | 0.775 [0.770, 0.780] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.905 [0.901, 0.908] | 0.905 [0.901, 0.908] | -0.0001 | same at 3 dp (187 q) | 0.905 |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.821 [0.817, 0.825] | 0.821 [0.817, 0.825] | -0.0001 | same at 3 dp (187 q) | 0.821 |  |
| Qwen3-4B (no gov) | recall@5 | 0.906 [0.902, 0.909] | 0.905 [0.901, 0.909] | -0.0002 | changed (192 q) | 0.905 |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.821 [0.817, 0.825] | 0.821 [0.816, 0.825] | -0.0001 | same at 3 dp (192 q) | 0.821 |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.905 [0.901, 0.908] | n/a |  | missing |  |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.821 [0.817, 0.825] | n/a |  | missing |  |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.737 [0.731, 0.743] | 0.737 [0.731, 0.743] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.622 [0.617, 0.628] | 0.622 [0.617, 0.628] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | recall@5 | 0.728 [0.722, 0.734] | 0.728 [0.722, 0.734] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | ndcg@5 | 0.614 [0.608, 0.619] | 0.614 [0.608, 0.619] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.737 [0.731, 0.743] | 0.737 [0.731, 0.743] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.622 [0.617, 0.628] | 0.622 [0.617, 0.628] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | recall@5 | 0.721 [0.715, 0.727] | 0.721 [0.715, 0.727] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | ndcg@5 | 0.601 [0.595, 0.606] | 0.601 [0.595, 0.606] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | 0.723 [0.717, 0.729] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | ndcg@5 | 0.603 [0.598, 0.609] | 0.603 [0.598, 0.609] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | recall@5 | 0.721 [0.715, 0.727] | 0.721 [0.715, 0.727] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.601 [0.595, 0.606] | 0.601 [0.595, 0.606] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (gov) | recall@5 | 0.400 [0.393, 0.406] | 0.400 [0.393, 0.406] | -0.0000 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+BM25 (gov) | ndcg@5 | 0.337 [0.331, 0.343] | 0.337 [0.331, 0.343] | -0.0001 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BM25 (no gov) | recall@5 | 0.404 [0.397, 0.410] | 0.404 [0.397, 0.410] | -0.0000 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BM25 (no gov) | ndcg@5 | 0.341 [0.335, 0.347] | 0.341 [0.335, 0.347] | -0.0001 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+BM25 (mand-only) | recall@5 | 0.400 [0.393, 0.406] | 0.400 [0.393, 0.406] | -0.0000 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.337 [0.331, 0.343] | 0.337 [0.331, 0.343] | -0.0001 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+Hash (gov) | recall@5 | 0.076 [0.073, 0.080] | 0.076 [0.073, 0.080] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | ndcg@5 | 0.048 [0.046, 0.051] | 0.048 [0.046, 0.051] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | recall@5 | 0.078 [0.074, 0.081] | 0.078 [0.074, 0.081] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | ndcg@5 | 0.050 [0.047, 0.052] | 0.050 [0.047, 0.052] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | recall@5 | 0.076 [0.073, 0.080] | 0.076 [0.073, 0.080] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | ndcg@5 | 0.048 [0.046, 0.051] | 0.048 [0.046, 0.051] | +0.0000 | identical | reproduces |  |
| BEAR+Nemotron (gov) | recall@5 | n/a | 0.745 [0.739, 0.751] |  | missing |  |  |
| BEAR+Nemotron (gov) | ndcg@5 | n/a | 0.651 [0.645, 0.656] |  | missing |  |  |
| Nemotron (no gov) | recall@5 | n/a | 0.815 [0.809, 0.820] |  | missing |  |  |
| Nemotron (no gov) | ndcg@5 | n/a | 0.699 [0.694, 0.704] |  | missing |  |  |

#### Table 6 +Tags

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.976 [0.974, 0.978] | 0.976 [0.974, 0.978] | +0.0000 | identical (47 q) | reproduces |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.914 [0.911, 0.917] | 0.914 [0.911, 0.917] | +0.0000 | same at 3 dp (47 q) | 0.914 |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.870 [0.865, 0.874] | 0.870 [0.865, 0.874] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.772 [0.768, 0.777] | 0.772 [0.768, 0.777] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.986 [0.985, 0.988] | 0.987 [0.985, 0.988] | +0.0004 | changed (143 q) | 0.987 |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.928 [0.925, 0.930] | 0.928 [0.925, 0.930] | -0.0001 | same at 3 dp (143 q) | 0.928 |  |
| Qwen3-4B (no gov) | recall@5 | 0.902 [0.898, 0.906] | 0.902 [0.898, 0.906] | -0.0003 | same at 3 dp (212 q) | 0.902 |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.816 [0.812, 0.820] | 0.815 [0.811, 0.819] | -0.0006 | changed (212 q) | 0.815 |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.972 [0.970, 0.975] | 0.972 [0.970, 0.975] | -0.0000 | same at 3 dp (23 q) | 0.972 |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.889 [0.886, 0.892] | 0.889 [0.886, 0.892] | -0.0000 | same at 3 dp (23 q) | 0.889 |  |
| BGE-M3 (no gov) | recall@5 | 0.724 [0.718, 0.730] | 0.724 [0.718, 0.730] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | ndcg@5 | 0.613 [0.608, 0.619] | 0.613 [0.608, 0.619] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | recall@5 | 0.981 [0.980, 0.983] | 0.981 [0.979, 0.983] | -0.0000 | same at 3 dp (47 q) | 0.981 |  |
| BEAR+BGE (gov) | ndcg@5 | 0.903 [0.900, 0.906] | 0.903 [0.900, 0.906] | -0.0001 | same at 3 dp (47 q) | 0.903 |  |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | 0.723 [0.717, 0.729] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | ndcg@5 | 0.605 [0.600, 0.611] | 0.605 [0.600, 0.611] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (gov) | recall@5 | 0.911 [0.907, 0.915] | 0.911 [0.907, 0.915] | -0.0001 | same at 3 dp (18 q) | reproduces | all, tie_order |
| BEAR+BM25 (gov) | ndcg@5 | 0.773 [0.769, 0.777] | 0.773 [0.769, 0.777] | -0.0001 | same at 3 dp (18 q) | reproduces | all, tie_order |
| BM25 (no gov) | recall@5 | 0.402 [0.395, 0.409] | 0.402 [0.395, 0.409] | -0.0000 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BM25 (no gov) | ndcg@5 | 0.339 [0.333, 0.345] | 0.339 [0.333, 0.345] | -0.0001 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | recall@5 | 0.736 [0.730, 0.742] | 0.736 [0.730, 0.741] | -0.0004 | same at 3 dp (121 q) | 0.736 | none (all: not restored) |
| BEAR+Hash (gov) | ndcg@5 | 0.531 [0.526, 0.536] | 0.530 [0.525, 0.535] | -0.0005 | changed (121 q) | 0.530 | none (all: not restored) |
| Hash (no gov) | recall@5 | 0.071 [0.068, 0.075] | 0.071 [0.068, 0.075] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | ndcg@5 | 0.045 [0.043, 0.048] | 0.045 [0.043, 0.048] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Nemotron (gov) | recall@5 | n/a | 0.986 [0.984, 0.987] |  | missing |  |  |
| BEAR+Nemotron (gov) | ndcg@5 | n/a | 0.931 [0.929, 0.934] |  | missing |  |  |
| Nemotron (no gov) | recall@5 | n/a | 0.804 [0.799, 0.809] |  | missing |  |  |
| Nemotron (no gov) | ndcg@5 | n/a | 0.690 [0.684, 0.695] |  | missing |  |  |

#### Table 6 +QueryTags

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| BEAR+Qwen3-0.6B (gov) | recall@5 | 0.735 [0.729, 0.741] | 0.735 [0.729, 0.741] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (gov) | ndcg@5 | 0.673 [0.668, 0.679] | 0.673 [0.668, 0.679] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | recall@5 | 0.870 [0.865, 0.874] | 0.870 [0.865, 0.874] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B (no gov) | ndcg@5 | 0.772 [0.768, 0.777] | 0.772 [0.768, 0.777] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-0.6B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Qwen3-4B (gov) | recall@5 | 0.749 [0.744, 0.755] | 0.749 [0.743, 0.755] | -0.0001 | same at 3 dp (78 q) | 0.749 |  |
| BEAR+Qwen3-4B (gov) | ndcg@5 | 0.699 [0.693, 0.705] | 0.699 [0.693, 0.705] | -0.0001 | same at 3 dp (78 q) | 0.699 |  |
| Qwen3-4B (no gov) | recall@5 | 0.902 [0.898, 0.906] | 0.902 [0.898, 0.906] | -0.0003 | same at 3 dp (212 q) | 0.902 |  |
| Qwen3-4B (no gov) | ndcg@5 | 0.816 [0.811, 0.820] | 0.815 [0.811, 0.820] | -0.0006 | changed (212 q) | 0.815 |  |
| BEAR+Qwen3-4B (mand-only) | recall@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+Qwen3-4B (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | n/a |  | missing |  |  |
| BEAR+BGE-M3 (gov) | recall@5 | 0.707 [0.701, 0.713] | 0.707 [0.701, 0.713] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (gov) | ndcg@5 | 0.624 [0.619, 0.630] | 0.624 [0.619, 0.630] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | recall@5 | 0.724 [0.718, 0.730] | 0.724 [0.718, 0.730] | +0.0000 | identical | reproduces |  |
| BGE-M3 (no gov) | ndcg@5 | 0.613 [0.608, 0.619] | 0.613 [0.608, 0.619] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE-M3 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | recall@5 | 0.668 [0.661, 0.674] | 0.668 [0.661, 0.674] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (gov) | ndcg@5 | 0.563 [0.558, 0.569] | 0.563 [0.558, 0.569] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | recall@5 | 0.723 [0.717, 0.729] | 0.723 [0.717, 0.729] | +0.0000 | identical | reproduces |  |
| BGE (no gov) | ndcg@5 | 0.605 [0.599, 0.611] | 0.605 [0.599, 0.611] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BGE (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (gov) | recall@5 | 0.504 [0.497, 0.511] | 0.504 [0.497, 0.511] | +0.0001 | same at 3 dp (2 q) | reproduces | all, tie_order |
| BEAR+BM25 (gov) | ndcg@5 | 0.411 [0.406, 0.417] | 0.412 [0.406, 0.418] | +0.0000 | changed (2 q) | reproduces | all, tie_order |
| BM25 (no gov) | recall@5 | 0.402 [0.396, 0.409] | 0.402 [0.396, 0.409] | -0.0000 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BM25 (no gov) | ndcg@5 | 0.339 [0.333, 0.345] | 0.339 [0.333, 0.345] | -0.0001 | same at 3 dp (6 q) | reproduces | all, tie_order |
| BEAR+BM25 (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+BM25 (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | recall@5 | 0.290 [0.284, 0.296] | 0.290 [0.284, 0.296] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (gov) | ndcg@5 | 0.187 [0.182, 0.191] | 0.187 [0.182, 0.191] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | recall@5 | 0.071 [0.068, 0.075] | 0.071 [0.068, 0.075] | +0.0000 | identical | reproduces |  |
| Hash (no gov) | ndcg@5 | 0.045 [0.043, 0.048] | 0.045 [0.043, 0.048] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | recall@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Hash (mand-only) | ndcg@5 | 0.000 [0.000, 0.000] | 0.000 [0.000, 0.000] | +0.0000 | identical | reproduces |  |
| BEAR+Nemotron (gov) | recall@5 | n/a | 0.703 [0.697, 0.709] |  | missing |  |  |
| BEAR+Nemotron (gov) | ndcg@5 | n/a | 0.612 [0.606, 0.618] |  | missing |  |  |
| Nemotron (no gov) | recall@5 | n/a | 0.804 [0.799, 0.809] |  | missing |  |  |
| Nemotron (no gov) | ndcg@5 | n/a | 0.690 [0.684, 0.695] |  | missing |  |  |

#### tab:governance-ablation (a)

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| BGE-base | strict_f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces | none (all: not restored) |
| BGE-base | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical | reproduces |  |
| BGE-base | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| BGE-base | notag_f1 | 0.701 [0.684, 0.718] | 0.653 [0.642, 0.662] | -0.0482 | changed, outside CI | reproduces | all, ungated_pool |
| BGE-base | complex_f1 | 0.664 [0.642, 0.684] | 0.672 [0.656, 0.688] | +0.0082 | changed | reproduces | none (all: not restored) |
| Qwen3-0.6B | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| Qwen3-0.6B | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Qwen3-0.6B | notag_f1 | 0.715 [0.696, 0.736] | 0.653 [0.642, 0.662] | -0.0623 | changed, outside CI | reproduces |  |
| Qwen3-0.6B | complex_f1 | 0.662 [0.640, 0.682] | 0.672 [0.656, 0.688] | +0.0103 | changed | reproduces |  |
| Qwen3-4B | strict_f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces |  |
| Qwen3-4B | relaxed_f1 | 0.790 [0.763, 0.817] | 0.790 [0.763, 0.817] | +0.0000 | identical | reproduces |  |
| Qwen3-4B | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Qwen3-4B | notag_f1 | 0.743 [0.718, 0.767] | 0.653 [0.642, 0.662] | -0.0894 | changed, outside CI | reproduces |  |
| Qwen3-4B | complex_f1 | 0.664 [0.642, 0.684] | 0.674 [0.658, 0.690] | +0.0102 | changed | reproduces |  |
| BGE-M3 | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| BGE-M3 | relaxed_f1 | 0.790 [0.763, 0.817] | 0.790 [0.763, 0.817] | +0.0000 | identical | reproduces |  |
| BGE-M3 | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| BGE-M3 | notag_f1 | 0.789 [0.764, 0.813] | 0.653 [0.642, 0.662] | -0.1354 | changed, outside CI | reproduces |  |
| BGE-M3 | complex_f1 | 0.662 [0.640, 0.682] | 0.670 [0.652, 0.687] | +0.0081 | changed | reproduces |  |
| Hash | strict_f1 | 0.841 [0.806, 0.873] | 0.845 [0.813, 0.875] | +0.0042 | changed | reproduces | none (all: not restored) |
| Hash | relaxed_f1 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical | reproduces |  |
| Hash | para_f1 | 0.886 [0.865, 0.907] | 0.886 [0.865, 0.907] | +0.0000 | identical | reproduces |  |
| Hash | notag_f1 | 0.837 [0.813, 0.862] | 0.837 [0.813, 0.862] | +0.0000 | identical | reproduces |  |
| Hash | complex_f1 | 0.891 [0.860, 0.921] | 0.896 [0.866, 0.923] | +0.0042 | changed | reproduces | none (all: not restored) |
| BM25 | strict_f1 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| BM25 | relaxed_f1 | 0.922 [0.906, 0.938] | 0.922 [0.906, 0.938] | +0.0000 | identical | reproduces |  |
| BM25 | para_f1 | 0.890 [0.867, 0.912] | 0.890 [0.867, 0.912] | +0.0000 | identical | reproduces |  |
| BM25 | notag_f1 | 0.718 [0.692, 0.745] | 0.718 [0.692, 0.745] | +0.0000 | identical | reproduces |  |
| BM25 | complex_f1 | 0.856 [0.820, 0.890] | 0.866 [0.836, 0.895] | +0.0103 | changed | reproduces | none (all: not restored) |
| ITR-hybrid | strict_f1 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| ITR-hybrid | relaxed_f1 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical | reproduces |  |
| ITR-hybrid | para_f1 | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| ITR-hybrid | notag_f1 | 0.664 [0.650, 0.677] | 0.653 [0.642, 0.662] | -0.0105 | changed | reproduces |  |
| ITR-hybrid | complex_f1 | 0.655 [0.636, 0.673] | 0.672 [0.656, 0.688] | +0.0166 | changed | reproduces |  |
| ITR-standalone | strict_f1 | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| ITR-standalone | relaxed_f1 | 0.320 [0.274, 0.369] | 0.320 [0.274, 0.369] | +0.0000 | identical | reproduces |  |
| ITR-standalone | para_f1 | 0.058 [0.039, 0.078] | 0.058 [0.039, 0.078] | +0.0000 | identical | reproduces |  |
| ITR-standalone | notag_f1 | 0.153 [0.130, 0.178] | 0.153 [0.130, 0.178] | +0.0000 | identical | reproduces |  |
| ITR-standalone | complex_f1 | 0.161 [0.132, 0.190] | 0.161 [0.132, 0.190] | +0.0000 | identical | reproduces |  |
| Random-k | strict_f1 | 0.116 [0.114, 0.118] | 0.116 [0.114, 0.118] | +0.0000 | identical | reproduces |  |
| Random-k | relaxed_f1 | 0.140 [0.140, 0.134] | 0.140 [0.140, 0.134] | +0.0000 | identical | reproduces |  |
| Random-k | para_f1 | 0.101 [0.101, 0.099] | 0.101 [0.101, 0.099] | +0.0000 | identical | reproduces |  |
| Random-k | notag_f1 | 0.097 [0.097, 0.095] | 0.097 [0.097, 0.095] | +0.0000 | identical | reproduces |  |
| Random-k | complex_f1 | 0.114 [0.114, 0.111] | 0.114 [0.114, 0.111] | +0.0000 | identical | reproduces |  |

#### tab:governance-ablation

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| Full governance / BM25 | Standard | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| Full governance / Hash | Standard | 0.841 [0.806, 0.873] | 0.845 [0.813, 0.875] | +0.0042 | changed | reproduces | none (all: not restored) |
| Full governance / BGE-base | Standard | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces | none (all: not restored) |
| Full governance / BGE-M3 | Standard | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| Full governance / Qwen3-0.6B | Standard | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| Full governance / Qwen3-4B | Standard | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces |  |
| Full governance / ITR | Standard | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Full governance / Random-k | Standard | 0.116 [0.114, 0.119] | 0.116 [0.114, 0.119] | +0.0000 | identical | reproduces |  |
| Full governance / BM25 | Paraphrase | 0.890 [0.867, 0.912] | 0.890 [0.867, 0.912] | +0.0000 | identical | reproduces |  |
| Full governance / Hash | Paraphrase | 0.886 [0.865, 0.907] | 0.886 [0.865, 0.907] | +0.0000 | identical | reproduces |  |
| Full governance / BGE-base | Paraphrase | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Full governance / BGE-M3 | Paraphrase | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Full governance / Qwen3-0.6B | Paraphrase | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Full governance / Qwen3-4B | Paraphrase | 0.637 [0.627, 0.648] | 0.637 [0.627, 0.648] | +0.0000 | identical | reproduces |  |
| Full governance / ITR | Paraphrase | 0.058 [0.039, 0.078] | 0.058 [0.039, 0.078] | +0.0000 | identical | reproduces |  |
| Full governance / Random-k | Paraphrase | 0.102 [0.100, 0.104] | 0.102 [0.100, 0.104] | +0.0000 | identical | reproduces |  |
| Full governance / BM25 | No-tag | 0.718 [0.692, 0.745] | 0.718 [0.692, 0.745] | +0.0000 | identical | reproduces |  |
| Full governance / Hash | No-tag | 0.837 [0.813, 0.862] | 0.837 [0.813, 0.862] | +0.0000 | identical | reproduces |  |
| Full governance / BGE-base | No-tag | 0.701 [0.684, 0.718] | 0.653 [0.642, 0.662] | -0.0482 | changed, outside CI | reproduces | all, ungated_pool |
| Full governance / BGE-M3 | No-tag | 0.789 [0.764, 0.813] | 0.653 [0.642, 0.662] | -0.1354 | changed, outside CI | reproduces |  |
| Full governance / Qwen3-0.6B | No-tag | 0.715 [0.696, 0.736] | 0.653 [0.642, 0.662] | -0.0623 | changed, outside CI | reproduces |  |
| Full governance / Qwen3-4B | No-tag | 0.743 [0.718, 0.767] | 0.653 [0.642, 0.662] | -0.0894 | changed, outside CI | reproduces |  |
| Full governance / ITR | No-tag | 0.153 [0.130, 0.178] | 0.153 [0.130, 0.178] | +0.0000 | identical | reproduces |  |
| Full governance / Random-k | No-tag | 0.097 [0.095, 0.098] | 0.097 [0.095, 0.098] | +0.0000 | identical | reproduces |  |
| Full governance / BM25 | Complex | 0.856 [0.820, 0.890] | 0.866 [0.836, 0.895] | +0.0103 | changed | reproduces | none (all: not restored) |
| Full governance / Hash | Complex | 0.891 [0.860, 0.921] | 0.896 [0.866, 0.923] | +0.0042 | changed | reproduces | none (all: not restored) |
| Full governance / BGE-base | Complex | 0.664 [0.642, 0.684] | 0.672 [0.656, 0.688] | +0.0082 | changed | reproduces | none (all: not restored) |
| Full governance / BGE-M3 | Complex | 0.662 [0.640, 0.682] | 0.670 [0.652, 0.687] | +0.0081 | changed | reproduces |  |
| Full governance / Qwen3-0.6B | Complex | 0.662 [0.640, 0.682] | 0.672 [0.656, 0.688] | +0.0103 | changed | reproduces |  |
| Full governance / Qwen3-4B | Complex | 0.664 [0.642, 0.684] | 0.674 [0.658, 0.690] | +0.0102 | changed | reproduces |  |
| Full governance / ITR | Complex | 0.161 [0.132, 0.190] | 0.161 [0.132, 0.190] | +0.0000 | identical | reproduces |  |
| Full governance / Random-k | Complex | 0.115 [0.111, 0.118] | 0.115 [0.111, 0.118] | +0.0000 | identical | reproduces |  |
| Mandatory only / BM25 | Standard | 0.478 [0.451, 0.504] | 0.550 [0.535, 0.564] | +0.0716 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / Hash | Standard | 0.431 [0.402, 0.459] | 0.518 [0.499, 0.537] | +0.0874 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / BGE-base | Standard | 0.522 [0.501, 0.541] | 0.522 [0.501, 0.541] | +0.0000 | identical | reproduces |  |
| Mandatory only / BGE-M3 | Standard | 0.538 [0.521, 0.555] | 0.538 [0.521, 0.555] | +0.0000 | identical | reproduces |  |
| Mandatory only / Qwen3-0.6B | Standard | 0.518 [0.495, 0.540] | 0.540 [0.520, 0.559] | +0.0217 | changed | reproduces |  |
| Mandatory only / Qwen3-4B | Standard | 0.540 [0.518, 0.561] | 0.577 [0.557, 0.596] | +0.0374 | changed, outside CI | reproduces |  |
| Mandatory only / ITR | Standard | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Mandatory only / Random-k | Standard | 0.116 [0.114, 0.119] | 0.116 [0.114, 0.119] | +0.0000 | identical | reproduces |  |
| Mandatory only / BM25 | Paraphrase | 0.384 [0.350, 0.418] | 0.467 [0.451, 0.485] | +0.0827 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / Hash | Paraphrase | 0.416 [0.388, 0.444] | 0.481 [0.463, 0.499] | +0.0649 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / BGE-base | Paraphrase | 0.439 [0.424, 0.454] | 0.446 [0.433, 0.460] | +0.0070 | changed | reproduces | none (all: not restored) |
| Mandatory only / BGE-M3 | Paraphrase | 0.462 [0.446, 0.480] | 0.462 [0.446, 0.480] | +0.0000 | identical | reproduces |  |
| Mandatory only / Qwen3-0.6B | Paraphrase | 0.418 [0.400, 0.435] | 0.457 [0.443, 0.473] | +0.0398 | changed, outside CI | reproduces |  |
| Mandatory only / Qwen3-4B | Paraphrase | 0.458 [0.436, 0.480] | 0.502 [0.484, 0.520] | +0.0441 | changed, outside CI | reproduces |  |
| Mandatory only / ITR | Paraphrase | 0.058 [0.039, 0.078] | 0.058 [0.039, 0.078] | +0.0000 | identical | reproduces |  |
| Mandatory only / Random-k | Paraphrase | 0.102 [0.100, 0.104] | 0.102 [0.100, 0.104] | +0.0000 | identical | reproduces |  |
| Mandatory only / BM25 | No-tag | 0.378 [0.342, 0.413] | 0.479 [0.461, 0.498] | +0.1013 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / Hash | No-tag | 0.447 [0.423, 0.473] | 0.469 [0.452, 0.489] | +0.0216 | changed | reproduces | none (all: not restored) |
| Mandatory only / BGE-base | No-tag | 0.451 [0.439, 0.464] | 0.451 [0.439, 0.464] | +0.0000 | identical | reproduces |  |
| Mandatory only / BGE-M3 | No-tag | 0.432 [0.430, 0.435] | 0.432 [0.430, 0.435] | +0.0000 | identical | reproduces |  |
| Mandatory only / Qwen3-0.6B | No-tag | 0.451 [0.434, 0.467] | 0.456 [0.443, 0.470] | +0.0053 | changed | reproduces |  |
| Mandatory only / Qwen3-4B | No-tag | 0.440 [0.429, 0.452] | 0.443 [0.434, 0.454] | +0.0026 | changed | reproduces |  |
| Mandatory only / ITR | No-tag | 0.153 [0.130, 0.178] | 0.153 [0.130, 0.178] | +0.0000 | identical | reproduces |  |
| Mandatory only / Random-k | No-tag | 0.097 [0.095, 0.098] | 0.097 [0.095, 0.098] | +0.0000 | identical | reproduces |  |
| Mandatory only / BM25 | Complex | 0.480 [0.447, 0.512] | 0.557 [0.538, 0.576] | +0.0767 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / Hash | Complex | 0.405 [0.378, 0.432] | 0.477 [0.457, 0.499] | +0.0716 | changed, outside CI | reproduces | none (all: not restored) |
| Mandatory only / BGE-base | Complex | 0.508 [0.489, 0.528] | 0.508 [0.489, 0.528] | +0.0000 | identical | reproduces |  |
| Mandatory only / BGE-M3 | Complex | 0.528 [0.510, 0.546] | 0.528 [0.510, 0.546] | +0.0000 | identical | reproduces |  |
| Mandatory only / Qwen3-0.6B | Complex | 0.490 [0.457, 0.522] | 0.539 [0.517, 0.562] | +0.0492 | changed, outside CI | reproduces |  |
| Mandatory only / Qwen3-4B | Complex | 0.539 [0.516, 0.561] | 0.572 [0.552, 0.592] | +0.0330 | changed, outside CI | reproduces |  |
| Mandatory only / ITR | Complex | 0.161 [0.132, 0.190] | 0.161 [0.132, 0.190] | +0.0000 | identical | reproduces |  |
| Mandatory only / Random-k | Complex | 0.115 [0.111, 0.118] | 0.115 [0.111, 0.118] | +0.0000 | identical | reproduces |  |
| No governance / BM25 | Standard | 0.249 [0.219, 0.282] | 0.249 [0.219, 0.282] | +0.0000 | identical | reproduces |  |
| No governance / Hash | Standard | 0.304 [0.277, 0.332] | 0.304 [0.277, 0.332] | +0.0000 | identical | reproduces |  |
| No governance / BGE-base | Standard | 0.155 [0.134, 0.178] | 0.155 [0.134, 0.178] | +0.0000 | identical | reproduces |  |
| No governance / BGE-M3 | Standard | 0.160 [0.141, 0.178] | 0.160 [0.141, 0.178] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-0.6B | Standard | 0.209 [0.189, 0.229] | 0.209 [0.189, 0.229] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-4B | Standard | 0.230 [0.206, 0.254] | 0.230 [0.206, 0.254] | +0.0000 | identical | reproduces |  |
| No governance / ITR | Standard | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| No governance / Random-k | Standard | 0.116 [0.114, 0.119] | 0.116 [0.114, 0.119] | +0.0000 | identical | reproduces |  |
| No governance / BM25 | Paraphrase | 0.117 [0.088, 0.146] | 0.117 [0.088, 0.146] | +0.0000 | identical | reproduces |  |
| No governance / Hash | Paraphrase | 0.254 [0.225, 0.284] | 0.254 [0.225, 0.284] | +0.0000 | identical | reproduces |  |
| No governance / BGE-base | Paraphrase | 0.073 [0.049, 0.097] | 0.073 [0.049, 0.097] | +0.0000 | identical | reproduces |  |
| No governance / BGE-M3 | Paraphrase | 0.082 [0.065, 0.099] | 0.082 [0.065, 0.099] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-0.6B | Paraphrase | 0.103 [0.080, 0.127] | 0.103 [0.080, 0.127] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-4B | Paraphrase | 0.127 [0.101, 0.155] | 0.127 [0.101, 0.155] | +0.0000 | identical | reproduces |  |
| No governance / ITR | Paraphrase | 0.058 [0.039, 0.078] | 0.058 [0.039, 0.078] | +0.0000 | identical | reproduces |  |
| No governance / Random-k | Paraphrase | 0.102 [0.100, 0.104] | 0.102 [0.100, 0.104] | +0.0000 | identical | reproduces |  |
| No governance / BM25 | No-tag | 0.201 [0.158, 0.244] | 0.201 [0.158, 0.244] | +0.0000 | identical | reproduces |  |
| No governance / Hash | No-tag | 0.289 [0.250, 0.330] | 0.289 [0.250, 0.330] | +0.0000 | identical | reproduces |  |
| No governance / BGE-base | No-tag | 0.105 [0.075, 0.137] | 0.105 [0.075, 0.137] | +0.0000 | identical | reproduces |  |
| No governance / BGE-M3 | No-tag | 0.025 [0.008, 0.048] | 0.025 [0.008, 0.048] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-0.6B | No-tag | 0.132 [0.096, 0.170] | 0.132 [0.096, 0.170] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-4B | No-tag | 0.116 [0.085, 0.149] | 0.116 [0.085, 0.149] | +0.0000 | identical | reproduces |  |
| No governance / ITR | No-tag | 0.153 [0.130, 0.178] | 0.153 [0.130, 0.178] | +0.0000 | identical | reproduces |  |
| No governance / Random-k | No-tag | 0.097 [0.095, 0.098] | 0.097 [0.095, 0.098] | +0.0000 | identical | reproduces |  |
| No governance / BM25 | Complex | 0.232 [0.201, 0.265] | 0.232 [0.201, 0.265] | +0.0000 | identical | reproduces |  |
| No governance / Hash | Complex | 0.318 [0.283, 0.352] | 0.318 [0.283, 0.352] | +0.0000 | identical | reproduces |  |
| No governance / BGE-base | Complex | 0.144 [0.119, 0.171] | 0.144 [0.119, 0.171] | +0.0000 | identical | reproduces |  |
| No governance / BGE-M3 | Complex | 0.148 [0.127, 0.170] | 0.148 [0.127, 0.170] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-0.6B | Complex | 0.226 [0.200, 0.252] | 0.226 [0.200, 0.252] | +0.0000 | identical | reproduces |  |
| No governance / Qwen3-4B | Complex | 0.232 [0.205, 0.259] | 0.232 [0.205, 0.259] | +0.0000 | identical | reproduces |  |
| No governance / ITR | Complex | 0.161 [0.132, 0.190] | 0.161 [0.132, 0.190] | +0.0000 | identical | reproduces |  |
| No governance / Random-k | Complex | 0.115 [0.111, 0.118] | 0.115 [0.111, 0.118] | +0.0000 | identical | reproduces |  |

#### tab:token-compare

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| Monolithic | tokens/query | 5029.000 | 5029.000 | +0.0000 | identical | reproduces |  |
| Role prompting | tokens/query | 46.000 | 46.000 | +0.0000 | identical | reproduces |  |
| BEAR + BM25 | tokens/query | 600.950 | 593.900 | -7.0500 | changed | reproduces |  |
| BEAR + Hash | tokens/query | 630.717 | 629.350 | -1.3667 | changed | reproduces |  |
| BEAR + BGE-base | tokens/query | 839.783 | 837.467 | -2.3167 | changed | reproduces |  |
| BEAR + BGE-M3 | tokens/query | 844.667 | 837.850 | -6.8167 | changed | reproduces |  |
| BEAR + Qwen3-0.6B | tokens/query | 842.700 | 836.900 | -5.8000 | changed | reproduces |  |
| BEAR + Qwen3-4B | tokens/query | 843.733 | 837.567 | -6.1667 | changed | reproduces |  |
| ITR | tokens/query | 846.333 | 846.333 | +0.0000 | identical | reproduces |  |
| Random-k | tokens/query | 867.616 | 867.616 | +0.0000 | identical | reproduces |  |

#### tab:decomposed-ablation

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| Full governance | bge | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces | none (all: not restored) |
| - required_tags | bge | 0.522 [0.501, 0.541] | 0.522 [0.501, 0.541] | +0.0000 | identical | reproduces |  |
| - priority weighting | bge | 0.563 [0.521, 0.602] | 0.657 [0.641, 0.671] | +0.0939 | changed, outside CI | reproduces | none (all: not restored) |
| - conflict resolution | bge | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces | none (all: not restored) |
| - mandatory injection | bge | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| No governance | bge | 0.162 [0.149, 0.177] | 0.162 [0.149, 0.177] | +0.0000 | identical | reproduces |  |
| ITR library (off-the-shelf) | bge | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Full governance | bge-m3 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| - required_tags | bge-m3 | 0.538 [0.521, 0.555] | 0.538 [0.521, 0.555] | +0.0000 | identical | reproduces |  |
| - priority weighting | bge-m3 | 0.569 [0.532, 0.604] | 0.665 [0.653, 0.678] | +0.0967 | changed, outside CI | reproduces |  |
| - conflict resolution | bge-m3 | 0.655 [0.636, 0.673] | 0.668 [0.654, 0.681] | +0.0125 | changed | reproduces |  |
| - mandatory injection | bge-m3 | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| No governance | bge-m3 | 0.175 [0.161, 0.190] | 0.175 [0.161, 0.190] | +0.0000 | identical | reproduces |  |
| ITR library (off-the-shelf) | bge-m3 | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Full governance | qwen3 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| - required_tags | qwen3 | 0.518 [0.495, 0.540] | 0.540 [0.520, 0.559] | +0.0217 | changed | reproduces |  |
| - priority weighting | qwen3 | 0.580 [0.547, 0.612] | 0.665 [0.653, 0.678] | +0.0858 | changed, outside CI | reproduces |  |
| - conflict resolution | qwen3 | 0.655 [0.636, 0.673] | 0.668 [0.654, 0.681] | +0.0125 | changed | reproduces |  |
| - mandatory injection | qwen3 | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| No governance | qwen3 | 0.197 [0.180, 0.215] | 0.197 [0.180, 0.215] | +0.0000 | identical | reproduces |  |
| ITR library (off-the-shelf) | qwen3 | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Full governance | qwen3-4b | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces |  |
| - required_tags | qwen3-4b | 0.540 [0.518, 0.561] | 0.577 [0.557, 0.596] | +0.0374 | changed, outside CI | reproduces |  |
| - priority weighting | qwen3-4b | 0.599 [0.569, 0.627] | 0.668 [0.655, 0.680] | +0.0682 | changed, outside CI | reproduces |  |
| - conflict resolution | qwen3-4b | 0.655 [0.636, 0.673] | 0.670 [0.657, 0.682] | +0.0146 | changed | reproduces |  |
| - mandatory injection | qwen3-4b | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| No governance | qwen3-4b | 0.221 [0.206, 0.237] | 0.221 [0.206, 0.237] | +0.0000 | identical | reproduces |  |
| ITR library (off-the-shelf) | qwen3-4b | 0.182 [0.162, 0.203] | 0.182 [0.162, 0.203] | +0.0000 | identical | reproduces |  |
| Full governance | bm25 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| - required_tags | bm25 | 0.478 [0.451, 0.504] | 0.550 [0.535, 0.564] | +0.0716 | changed, outside CI | reproduces | none (all: not restored) |
| - priority weighting | bm25 | 0.865 [0.824, 0.902] | 0.879 [0.847, 0.910] | +0.0146 | changed | reproduces | none (all: not restored) |
| - conflict resolution | bm25 | 0.859 [0.818, 0.896] | 0.869 [0.835, 0.901] | +0.0104 | changed | reproduces | none (all: not restored) |
| - mandatory injection | bm25 | 0.865 [0.824, 0.902] | 0.865 [0.824, 0.902] | +0.0000 | identical | reproduces |  |
| No governance | bm25 | 0.204 [0.186, 0.224] | 0.204 [0.186, 0.224] | +0.0000 | identical | reproduces |  |
| ITR library (off-the-shelf) | bm25 | 0.211 [0.186, 0.237] | 0.211 [0.186, 0.237] | +0.0000 | identical | reproduces |  |

#### tab:alpha-sweep

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| alpha=0.00 | bge | 0.563 [0.521, 0.602] | 0.657 [0.641, 0.671] | +0.0939 | changed, outside CI | reproduces | none (all: not restored) |
| alpha=0.10 | bge | 0.589 [0.555, 0.620] | 0.665 [0.652, 0.679] | +0.0768 | changed, outside CI | reproduces | none (all: not restored) |
| alpha=0.20 | bge | 0.624 [0.603, 0.645] | 0.668 [0.655, 0.680] | +0.0431 | changed, outside CI | reproduces | none (all: not restored) |
| alpha=0.30 | bge | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces | none (all: not restored) |
| alpha=0.50 | bge | 0.649 [0.629, 0.667] | 0.659 [0.643, 0.674] | +0.0104 | changed | reproduces | none (all: not restored) |
| alpha=0.70 | bge | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| alpha=0.90 | bge | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| alpha=1.00 | bge | 0.649 [0.629, 0.667] | 0.647 [0.628, 0.665] | -0.0021 | changed | reproduces | all, tie_order |
| alpha=0.00 | bge-m3 | 0.569 [0.532, 0.604] | 0.665 [0.653, 0.678] | +0.0967 | changed, outside CI | reproduces |  |
| alpha=0.10 | bge-m3 | 0.586 [0.554, 0.617] | 0.668 [0.655, 0.680] | +0.0817 | changed, outside CI | reproduces |  |
| alpha=0.20 | bge-m3 | 0.631 [0.610, 0.651] | 0.668 [0.655, 0.680] | +0.0367 | changed, outside CI | reproduces |  |
| alpha=0.30 | bge-m3 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| alpha=0.50 | bge-m3 | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| alpha=0.70 | bge-m3 | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| alpha=0.90 | bge-m3 | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| alpha=1.00 | bge-m3 | 0.649 [0.629, 0.667] | 0.647 [0.628, 0.665] | -0.0021 | changed | reproduces |  |
| alpha=0.00 | qwen3 | 0.580 [0.547, 0.612] | 0.665 [0.653, 0.678] | +0.0858 | changed, outside CI | reproduces |  |
| alpha=0.10 | qwen3 | 0.612 [0.585, 0.637] | 0.668 [0.655, 0.680] | +0.0554 | changed, outside CI | reproduces |  |
| alpha=0.20 | qwen3 | 0.644 [0.625, 0.663] | 0.668 [0.655, 0.680] | +0.0233 | changed, outside CI | reproduces |  |
| alpha=0.30 | qwen3 | 0.653 [0.634, 0.671] | 0.665 [0.652, 0.679] | +0.0125 | changed | reproduces |  |
| alpha=0.50 | qwen3 | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| alpha=0.70 | qwen3 | 0.653 [0.634, 0.671] | 0.653 [0.634, 0.671] | +0.0000 | identical | reproduces |  |
| alpha=0.90 | qwen3 | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| alpha=1.00 | qwen3 | 0.649 [0.629, 0.667] | 0.647 [0.628, 0.665] | -0.0021 | changed | reproduces |  |
| alpha=0.00 | qwen3-4b | 0.599 [0.569, 0.627] | 0.668 [0.655, 0.680] | +0.0682 | changed, outside CI | reproduces |  |
| alpha=0.10 | qwen3-4b | 0.614 [0.588, 0.639] | 0.668 [0.655, 0.680] | +0.0535 | changed, outside CI | reproduces |  |
| alpha=0.20 | qwen3-4b | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces |  |
| alpha=0.30 | qwen3-4b | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed | reproduces |  |
| alpha=0.50 | qwen3-4b | 0.653 [0.634, 0.671] | 0.657 [0.640, 0.674] | +0.0042 | changed | reproduces |  |
| alpha=0.70 | qwen3-4b | 0.843 [0.810, 0.874] | 0.649 [0.629, 0.667] | -0.1939 | changed, outside CI | 0.649 |  |
| alpha=0.90 | qwen3-4b | 0.830 [0.791, 0.867] | 0.649 [0.629, 0.667] | -0.1814 | changed, outside CI | 0.649 |  |
| alpha=1.00 | qwen3-4b | 0.830 [0.791, 0.867] | 0.647 [0.628, 0.665] | -0.1835 | changed, outside CI | 0.649 |  |
| alpha=0.00 | bm25 | 0.865 [0.824, 0.902] | 0.879 [0.847, 0.910] | +0.0146 | changed | reproduces | none (all: not restored) |
| alpha=0.10 | bm25 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| alpha=0.20 | bm25 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| alpha=0.30 | bm25 | 0.865 [0.824, 0.902] | 0.875 [0.840, 0.908] | +0.0104 | changed | reproduces | none (all: not restored) |
| alpha=0.50 | bm25 | 0.865 [0.824, 0.902] | 0.865 [0.824, 0.902] | +0.0000 | identical | reproduces |  |
| alpha=0.70 | bm25 | 0.865 [0.824, 0.902] | 0.865 [0.824, 0.902] | +0.0000 | identical | reproduces |  |
| alpha=0.90 | bm25 | 0.865 [0.824, 0.902] | 0.865 [0.824, 0.902] | +0.0000 | identical | reproduces |  |
| alpha=1.00 | bm25 | 0.865 [0.824, 0.902] | 0.865 [0.824, 0.902] | +0.0000 | identical | reproduces |  |

#### tab:retrieval

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| Full BEAR (Hash) | Strict F1@10 | 0.841 [0.806, 0.873] | 0.845 [0.813, 0.875] | +0.0040 | changed | reproduces | none (all: not restored) |
| Full BEAR (Hash) | Strict R@10 | 0.972 [0.950, 0.992] | 0.978 [0.958, 0.992] | +0.0060 | changed | reproduces | none (all: not restored) |
| Full BEAR (Hash) | Relaxed F1@10 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical | reproduces |  |
| Full BEAR (Hash) | Relaxed R@10 | 0.890 [0.861, 0.917] | 0.890 [0.861, 0.917] | +0.0000 | identical | reproduces |  |
| Pure Similarity (Hash) | Strict F1@10 | 0.481 [0.430, 0.532] | 0.707 [0.683, 0.729] | +0.2260 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (Hash) | Strict R@10 | 0.377 [0.329, 0.425] | 0.607 [0.587, 0.628] | +0.2300 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (Hash) | Relaxed F1@10 | 0.404 [0.353, 0.456] | 0.594 [0.562, 0.625] | +0.1900 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (Hash) | Relaxed R@10 | 0.300 [0.254, 0.346] | 0.469 [0.435, 0.504] | +0.1690 | changed, outside CI | reproduces | all, ungated_pool |
| Priority-Heavy (Hash) | Strict F1@10 | 0.843 [0.810, 0.874] | 0.843 [0.810, 0.874] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (Hash) | Strict R@10 | 0.975 [0.956, 0.992] | 0.975 [0.956, 0.992] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (Hash) | Relaxed F1@10 | 0.889 [0.871, 0.906] | 0.889 [0.871, 0.906] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (Hash) | Relaxed R@10 | 0.890 [0.861, 0.917] | 0.890 [0.861, 0.917] | +0.0000 | identical | reproduces |  |
| Full BEAR (BGE) | Strict F1@10 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0150 | changed | reproduces | none (all: not restored) |
| Full BEAR (BGE) | Strict R@10 | 0.958 [0.928, 0.983] | 0.978 [0.964, 0.992] | +0.0200 | changed | reproduces | none (all: not restored) |
| Full BEAR (BGE) | Relaxed F1@10 | 0.792 [0.764, 0.820] | 0.792 [0.764, 0.820] | +0.0000 | identical | reproduces |  |
| Full BEAR (BGE) | Relaxed R@10 | 0.963 [0.944, 0.980] | 0.963 [0.944, 0.980] | +0.0000 | identical | reproduces |  |
| Pure Similarity (BGE) | Strict F1@10 | 0.155 [0.111, 0.202] | 0.496 [0.480, 0.513] | +0.3410 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (BGE) | Strict R@10 | 0.123 [0.087, 0.160] | 0.642 [0.618, 0.668] | +0.5190 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (BGE) | Relaxed F1@10 | 0.214 [0.166, 0.262] | 0.514 [0.483, 0.544] | +0.3000 | changed, outside CI | reproduces | all, ungated_pool |
| Pure Similarity (BGE) | Relaxed R@10 | 0.157 [0.121, 0.195] | 0.578 [0.533, 0.621] | +0.4210 | changed, outside CI | reproduces | all, ungated_pool |
| Priority-Heavy (BGE) | Strict F1@10 | 0.649 [0.629, 0.667] | 0.649 [0.629, 0.667] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (BGE) | Strict R@10 | 0.953 [0.922, 0.981] | 0.953 [0.922, 0.981] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (BGE) | Relaxed F1@10 | 0.788 [0.759, 0.816] | 0.788 [0.759, 0.816] | +0.0000 | identical | reproduces |  |
| Priority-Heavy (BGE) | Relaxed R@10 | 0.958 [0.938, 0.977] | 0.958 [0.938, 0.977] | +0.0000 | identical | reproduces |  |

#### Table 4

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| top-1: oracle | recall@5 | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical |  |  |
| top-1: oracle | ndcg@5 | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical |  |  |
| top-1: oracle | f1@5 | 0.422 [0.409, 0.434] | 0.422 [0.409, 0.434] | +0.0000 | identical |  |  |
| top-1: inferred | recall@5 | 0.336 [0.311, 0.360] | 0.336 [0.311, 0.360] | +0.0000 | identical |  |  |
| top-1: inferred | ndcg@5 | 0.322 [0.298, 0.345] | 0.322 [0.298, 0.345] | +0.0000 | identical |  |  |
| top-1: inferred | f1@5 | 0.206 [0.191, 0.221] | 0.206 [0.191, 0.221] | +0.0000 | identical |  |  |
| top-1: no_governance | recall@5 | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical |  |  |
| top-1: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical |  |  |
| top-1: no_governance | f1@5 | 0.351 [0.338, 0.365] | 0.351 [0.338, 0.365] | +0.0000 | identical |  |  |
| multi: oracle | recall@5 | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical |  |  |
| multi: oracle | ndcg@5 | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical |  |  |
| multi: oracle | f1@5 | 0.422 [0.409, 0.434] | 0.422 [0.409, 0.434] | +0.0000 | identical |  |  |
| multi: inferred_multi | recall@5 | 0.483 [0.459, 0.507] | 0.483 [0.459, 0.507] | +0.0000 | identical |  |  |
| multi: inferred_multi | ndcg@5 | 0.458 [0.436, 0.481] | 0.458 [0.436, 0.481] | +0.0000 | identical |  |  |
| multi: inferred_multi | f1@5 | 0.296 [0.281, 0.311] | 0.296 [0.281, 0.311] | +0.0000 | identical |  |  |
| multi: no_governance | recall@5 | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical |  |  |
| multi: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical |  |  |
| multi: no_governance | f1@5 | 0.351 [0.338, 0.365] | 0.351 [0.338, 0.365] | +0.0000 | identical |  |  |
| top-5: oracle | recall@5 | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical |  |  |
| top-5: oracle | ndcg@5 | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical |  |  |
| top-5: oracle | f1@5 | 0.422 [0.409, 0.434] | 0.422 [0.409, 0.434] | +0.0000 | identical |  |  |
| top-5: inferred_top5 | recall@5 | 0.502 [0.478, 0.526] | 0.502 [0.478, 0.526] | +0.0000 | identical |  |  |
| top-5: inferred_top5 | ndcg@5 | 0.473 [0.451, 0.496] | 0.473 [0.451, 0.496] | +0.0000 | identical |  |  |
| top-5: inferred_top5 | f1@5 | 0.306 [0.292, 0.321] | 0.306 [0.292, 0.321] | +0.0000 | identical |  |  |
| top-5: no_governance | recall@5 | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical |  |  |
| top-5: no_governance | ndcg@5 | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical |  |  |
| top-5: no_governance | f1@5 | 0.351 [0.338, 0.365] | 0.351 [0.338, 0.365] | +0.0000 | identical |  |  |

#### tab:token-efficiency

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| N=10 | bear_mean_tokens | 952.000 | 952.000 | +0.0000 | identical | reproduces |  |
| N=10 | cpa_mean_tokens | 952.000 | 952.000 | +0.0000 | identical | reproduces |  |
| N=10 | static_tokens | 1454.000 | 1454.000 | +0.0000 | identical | reproduces |  |
| N=10 | bear_token_ratio | 0.655 | 0.655 | +0.0000 | identical | reproduces |  |
| N=25 | bear_mean_tokens | 996.000 | 996.000 | +0.0000 | identical | reproduces |  |
| N=25 | cpa_mean_tokens | 952.000 | 952.000 | +0.0000 | identical | reproduces |  |
| N=25 | static_tokens | 2609.000 | 2609.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_token_ratio | 0.382 | 0.382 | +0.0000 | identical | reproduces |  |
| N=50 | bear_mean_tokens | 985.000 | 985.000 | +0.0000 | identical | reproduces |  |
| N=50 | cpa_mean_tokens | 950.000 | 950.000 | +0.0000 | identical | reproduces |  |
| N=50 | static_tokens | 4344.000 | 4344.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_token_ratio | 0.227 | 0.227 | +0.0000 | identical | reproduces |  |
| N=100 | bear_mean_tokens | 995.000 | 995.000 | +0.0000 | identical | reproduces |  |
| N=100 | cpa_mean_tokens | 952.000 | 952.000 | +0.0000 | identical | reproduces |  |
| N=100 | static_tokens | 8021.000 | 8021.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_token_ratio | 0.124 | 0.124 | +0.0000 | identical | reproduces |  |
| N=200 | bear_mean_tokens | 967.000 | 967.000 | +0.0000 | identical | reproduces |  |
| N=200 | cpa_mean_tokens | 946.000 | 946.000 | +0.0000 | identical | reproduces |  |
| N=200 | static_tokens | 14696.000 | 14696.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_token_ratio | 0.066 | 0.066 | +0.0000 | identical | reproduces |  |
| N=500 | bear_mean_tokens | 953.000 | 953.000 | +0.0000 | identical | reproduces |  |
| N=500 | cpa_mean_tokens | 944.000 | 944.000 | +0.0000 | identical | reproduces |  |
| N=500 | static_tokens | 34721.000 | 34721.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_token_ratio | 0.027 | 0.027 | +0.0000 | identical | reproduces |  |

#### novel departments (text)

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| N=10 | bear_novel_recall | 0.944 | 0.944 | +0.0000 | identical | reproduces |  |
| N=10 | cpa_novel_recall | 0.888 | 0.888 | +0.0000 | identical | reproduces |  |
| N=25 | bear_novel_recall | 0.956 | 0.956 | +0.0000 | identical | reproduces |  |
| N=25 | cpa_novel_recall | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |
| N=50 | bear_novel_recall | 0.956 | 0.956 | +0.0000 | identical | reproduces |  |
| N=50 | cpa_novel_recall | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |
| N=100 | bear_novel_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | cpa_novel_recall | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |
| N=200 | bear_novel_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | cpa_novel_recall | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |
| N=500 | bear_novel_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | cpa_novel_recall | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |

#### tab:semantic-advantage

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| N=10 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=10 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=25 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=50 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_semantic_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | cpa_semantic_recall | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |

#### standard queries (text)

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| N=10 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=10 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=10 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=10 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=10 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=25 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=50 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=100 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=200 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_persona_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_dept_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_safety_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_global_recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| N=500 | bear_scope_violations | 0.000 | 0.000 | +0.0000 | identical | reproduces |  |

#### tab:tool-scaling

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| 5 | precision | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 5 | recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 5 | no_leaks | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 10 | precision | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 10 | recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 10 | no_leaks | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 25 | precision | 0.900 | 0.900 | +0.0000 | identical | reproduces |  |
| 25 | recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 25 | no_leaks | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 50 | precision | 0.912 | 0.912 | +0.0000 | identical | reproduces |  |
| 50 | recall | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |
| 50 | no_leaks | 1.000 | 1.000 | +0.0000 | identical | reproduces |  |

#### tab:token-savings

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| Predator attack | tools | 4.000 | 4.000 | +0.0000 | identical | reproduces |  |
| Predator attack | tokens | 214.000 | 214.000 | +0.0000 | identical | reproduces |  |
| Predator attack | savings% | 93.000 | 93.000 | +0.0000 | identical | reproduces |  |
| Social encounter | tools | 7.000 | 7.000 | +0.0000 | identical | reproduces |  |
| Social encounter | tokens | 450.000 | 450.000 | +0.0000 | identical | reproduces |  |
| Social encounter | savings% | 85.000 | 85.000 | +0.0000 | identical | reproduces |  |
| Hungry near food | tools | 3.000 | 3.000 | +0.0000 | identical | reproduces |  |
| Hungry near food | tokens | 172.000 | 172.000 | +0.0000 | identical | reproduces |  |
| Hungry near food | savings% | 94.000 | 94.000 | +0.0000 | identical | reproduces |  |
| Building with materials | tools | 3.000 | 3.000 | +0.0000 | identical | reproduces |  |
| Building with materials | tokens | 164.000 | 164.000 | +0.0000 | identical | reproduces |  |
| Building with materials | savings% | 94.000 | 94.000 | +0.0000 | identical | reproduces |  |
| Combat encounter | tools | 6.000 | 6.000 | +0.0000 | identical | reproduces |  |
| Combat encounter | tokens | 346.000 | 346.000 | +0.0000 | identical | reproduces |  |
| Combat encounter | savings% | 88.000 | 88.000 | +0.0000 | identical | reproduces |  |
| Near water | tools | 3.000 | 3.000 | +0.0000 | identical | reproduces |  |
| Near water | tokens | 155.000 | 155.000 | +0.0000 | identical | reproduces |  |
| Near water | savings% | 95.000 | 95.000 | +0.0000 | identical | reproduces |  |
| Item management | tools | 5.000 | 5.000 | +0.0000 | identical | reproduces |  |
| Item management | tokens | 288.000 | 288.000 | +0.0000 | identical | reproduces |  |
| Item management | savings% | 90.000 | 90.000 | +0.0000 | identical | reproduces |  |
| Territory dispute | tools | 10.000 | 10.000 | +0.0000 | identical | reproduces |  |
| Territory dispute | tokens | 629.000 | 629.000 | +0.0000 | identical | reproduces |  |
| Territory dispute | savings% | 79.000 | 79.000 | +0.0000 | identical | reproduces |  |
| All-tools baseline | tokens | 2928.000 | 2928.000 | +0.0000 | identical | reproduces |  |
| Average | savings% | 90.000 | 90.000 | +0.0000 | identical | reproduces |  |

#### tab:reranker

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| toolbench: Bi-encoder, no governance | recall | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical |  |  |
| toolbench: Bi-encoder, no governance | f1 | 0.351 [0.338, 0.365] | 0.351 [0.338, 0.365] | +0.0000 | identical |  |  |
| toolbench: Bi-encoder, no governance | ndcg | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical |  |  |
| toolbench: Bi-encoder + cross-encoder reranker | recall | 0.647 [0.625, 0.669] | 0.647 [0.625, 0.669] | +0.0000 | identical |  |  |
| toolbench: Bi-encoder + cross-encoder reranker | f1 | 0.397 [0.384, 0.411] | 0.397 [0.384, 0.411] | +0.0000 | identical |  |  |
| toolbench: Bi-encoder + cross-encoder reranker | ndcg | 0.617 [0.595, 0.637] | 0.617 [0.595, 0.637] | +0.0000 | identical |  |  |
| toolbench: BEAR governed | recall | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical |  |  |
| toolbench: BEAR governed | f1 | 0.422 [0.409, 0.434] | 0.422 [0.409, 0.434] | +0.0000 | identical |  |  |
| toolbench: BEAR governed | ndcg | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical |  |  |
| toolbench: BEAR governed + cross-encoder reranker | recall | 0.742 [0.722, 0.761] | 0.742 [0.722, 0.761] | +0.0000 | identical |  |  |
| toolbench: BEAR governed + cross-encoder reranker | f1 | 0.458 [0.445, 0.470] | 0.458 [0.445, 0.470] | +0.0000 | identical |  |  |
| toolbench: BEAR governed + cross-encoder reranker | ndcg | 0.708 [0.688, 0.727] | 0.708 [0.688, 0.727] | +0.0000 | identical |  |  |
| toolbench: LlamaIndex retriever (released package) | recall | 0.590 [0.568, 0.611] | 0.590 [0.568, 0.611] | +0.0000 | identical |  |  |
| toolbench: LlamaIndex retriever (released package) | f1 | 0.361 [0.348, 0.374] | 0.361 [0.348, 0.374] | +0.0000 | identical |  |  |
| toolbench: LlamaIndex retriever (released package) | ndcg | 0.560 [0.539, 0.580] | 0.560 [0.539, 0.580] | +0.0000 | identical |  |  |
| toolbench: BEAR, no governance (published baseline) | recall | 0.574 [0.552, 0.596] | 0.574 [0.552, 0.596] | +0.0000 | identical |  |  |
| toolbench: BEAR, no governance (published baseline) | f1 | 0.351 [0.338, 0.365] | 0.351 [0.338, 0.365] | +0.0000 | identical |  |  |
| toolbench: BEAR, no governance (published baseline) | ndcg | 0.545 [0.524, 0.566] | 0.545 [0.524, 0.566] | +0.0000 | identical |  |  |
| toolbench: BEAR governed (published row) | recall | 0.688 [0.668, 0.709] | 0.688 [0.668, 0.709] | +0.0000 | identical |  |  |
| toolbench: BEAR governed (published row) | f1 | 0.422 [0.409, 0.434] | 0.422 [0.409, 0.434] | +0.0000 | identical |  |  |
| toolbench: BEAR governed (published row) | ndcg | 0.651 [0.631, 0.670] | 0.651 [0.631, 0.670] | +0.0000 | identical |  |  |
| petsim: Bi-encoder, no governance | recall | 0.247 [0.227, 0.269] | 0.247 [0.227, 0.269] | +0.0000 | identical |  |  |
| petsim: Bi-encoder, no governance | f1 | 0.168 [0.152, 0.186] | 0.168 [0.152, 0.186] | +0.0000 | identical |  |  |
| petsim: Bi-encoder, no governance | ndcg | 0.347 [0.320, 0.371] | 0.347 [0.320, 0.371] | +0.0000 | identical |  |  |
| petsim: Bi-encoder + cross-encoder reranker | recall | 0.322 [0.293, 0.354] | 0.322 [0.293, 0.354] | +0.0000 | identical |  |  |
| petsim: Bi-encoder + cross-encoder reranker | f1 | 0.219 [0.198, 0.242] | 0.219 [0.198, 0.242] | +0.0000 | identical |  |  |
| petsim: Bi-encoder + cross-encoder reranker | ndcg | 0.375 [0.344, 0.406] | 0.375 [0.344, 0.406] | +0.0000 | identical |  |  |
| petsim: BEAR governed | recall | 0.958 [0.928, 0.983] | 0.978 [0.964, 0.992] | +0.0194 | changed |  |  |
| petsim: BEAR governed | f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed |  |  |
| petsim: BEAR governed | ndcg | 0.905 [0.870, 0.937] | 0.916 [0.888, 0.943] | +0.0111 | changed |  |  |
| petsim: BEAR governed + cross-encoder reranker | recall | 0.867 [0.815, 0.914] | 0.867 [0.815, 0.914] | +0.0000 | identical |  |  |
| petsim: BEAR governed + cross-encoder reranker | f1 | 0.589 [0.555, 0.620] | 0.589 [0.555, 0.620] | +0.0000 | identical |  |  |
| petsim: BEAR governed + cross-encoder reranker | ndcg | 0.750 [0.708, 0.789] | 0.750 [0.708, 0.789] | +0.0000 | identical |  |  |
| petsim: LlamaIndex retriever (released package) | recall | 0.247 [0.227, 0.267] | 0.247 [0.227, 0.267] | +0.0000 | identical |  |  |
| petsim: LlamaIndex retriever (released package) | f1 | 0.168 [0.153, 0.184] | 0.168 [0.153, 0.184] | +0.0000 | identical |  |  |
| petsim: LlamaIndex retriever (released package) | ndcg | 0.309 [0.279, 0.338] | 0.309 [0.279, 0.338] | +0.0000 | identical |  |  |
| petsim: BEAR, no governance (published baseline) | recall | 0.247 [0.227, 0.269] | 0.247 [0.227, 0.269] | +0.0000 | identical |  |  |
| petsim: BEAR, no governance (published baseline) | f1 | 0.168 [0.152, 0.186] | 0.168 [0.152, 0.186] | +0.0000 | identical |  |  |
| petsim: BEAR, no governance (published baseline) | ndcg | 0.347 [0.320, 0.371] | 0.347 [0.320, 0.371] | +0.0000 | identical |  |  |
| petsim: BEAR governed (published row) | recall | 0.958 [0.928, 0.983] | 0.978 [0.964, 0.992] | +0.0194 | changed |  |  |
| petsim: BEAR governed (published row) | f1 | 0.653 [0.634, 0.671] | 0.668 [0.655, 0.680] | +0.0146 | changed |  |  |
| petsim: BEAR governed (published row) | ndcg | 0.905 [0.870, 0.937] | 0.916 [0.888, 0.943] | +0.0111 | changed |  |  |

#### tab:reranker contrasts

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| toolbench: bear_vs_bi | recall | 0.114 [0.099, 0.130] | 0.114 [0.099, 0.130] | +0.0000 | identical |  |  |
| toolbench: bi_rr_vs_bi | recall | 0.073 [0.056, 0.090] | 0.073 [0.056, 0.090] | +0.0000 | identical |  |  |
| toolbench: bear_vs_bi_rr | recall | 0.041 [0.022, 0.060] | 0.041 [0.022, 0.060] | +0.0000 | identical |  |  |
| toolbench: bear_rr_vs_bear | recall | 0.054 [0.037, 0.069] | 0.054 [0.037, 0.069] | +0.0000 | identical |  |  |
| toolbench: bear_rr_vs_bi_rr | recall | 0.095 [0.081, 0.108] | 0.095 [0.081, 0.108] | +0.0000 | identical |  |  |
| toolbench: bear_nogov_vs_llamaindex | recall | -0.015 [-0.027, -0.004] | -0.015 [-0.027, -0.004] | +0.0000 | identical |  |  |
| toolbench: bear_gov_vs_llamaindex | recall | 0.099 [0.083, 0.115] | 0.099 [0.083, 0.115] | +0.0000 | identical |  |  |
| petsim: bear_vs_bi | f1 | 0.485 [0.457, 0.510] | 0.499 [0.480, 0.517] | +0.0146 | changed |  |  |
| petsim: bi_rr_vs_bi | f1 | 0.051 [0.031, 0.073] | 0.051 [0.031, 0.073] | +0.0000 | identical |  |  |
| petsim: bear_vs_bi_rr | f1 | 0.434 [0.406, 0.460] | 0.448 [0.426, 0.470] | +0.0146 | changed |  |  |
| petsim: bear_rr_vs_bear | f1 | -0.064 [-0.088, -0.043] | -0.079 [-0.109, -0.051] | -0.0146 | changed |  |  |
| petsim: bear_rr_vs_bi_rr | f1 | 0.369 [0.327, 0.409] | 0.369 [0.327, 0.409] | +0.0000 | identical |  |  |
| petsim: bear_vs_bi__f1_relaxed | f1_relaxed | 0.484 [0.444, 0.521] | 0.484 [0.444, 0.521] | +0.0000 | identical |  |  |
| petsim: bi_rr_vs_bi__f1_relaxed | f1_relaxed | 0.031 [0.004, 0.057] | 0.031 [0.004, 0.057] | +0.0000 | identical |  |  |
| petsim: bear_vs_bi_rr__f1_relaxed | f1_relaxed | 0.453 [0.421, 0.485] | 0.453 [0.421, 0.485] | +0.0000 | identical |  |  |
| petsim: bear_rr_vs_bear__f1_relaxed | f1_relaxed | -0.052 [-0.071, -0.034] | -0.052 [-0.071, -0.034] | +0.0000 | identical |  |  |
| petsim: bear_rr_vs_bi_rr__f1_relaxed | f1_relaxed | 0.401 [0.360, 0.443] | 0.401 [0.360, 0.443] | +0.0000 | identical |  |  |
| petsim: bear_nogov_vs_llamaindex | f1 | 0.000 [-0.011, 0.013] | 0.000 [-0.011, 0.013] | +0.0000 | identical |  |  |
| petsim: bear_gov_vs_llamaindex | f1 | 0.485 [0.458, 0.511] | 0.499 [0.481, 0.518] | +0.0146 | changed |  |  |
| petsim: bear_nogov_vs_llamaindex__f1_relaxed | f1_relaxed | 0.007 [-0.005, 0.019] | 0.007 [-0.005, 0.019] | +0.0000 | identical |  |  |
| petsim: bear_gov_vs_llamaindex__f1_relaxed | f1_relaxed | 0.490 [0.451, 0.528] | 0.490 [0.451, 0.528] | +0.0000 | identical |  |  |

#### tab:transfer

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| ToolBench-IR on toolbench | recall@5 | 0.847 [0.832, 0.862] | 0.847 [0.832, 0.862] | +0.0000 | identical |  |  |
| ToolBench-IR on toolbench | ndcg@5 | 0.793 [0.778, 0.808] | 0.793 [0.778, 0.808] | +0.0000 | identical |  |  |
| ToolBench-IR on toolbench | f1@5 | 0.528 [0.517, 0.538] | 0.528 [0.517, 0.538] | +0.0000 | identical |  |  |
| ToolBench-IR on metatool | recall@5 | 0.648 [0.642, 0.655] | 0.648 [0.642, 0.655] | +0.0000 | identical |  |  |
| ToolBench-IR on metatool | ndcg@5 | 0.553 [0.547, 0.559] | 0.553 [0.547, 0.559] | +0.0000 | identical |  |  |
| ToolBench-IR on metatool | f1@5 | 0.219 [0.217, 0.221] | 0.219 [0.217, 0.221] | +0.0000 | identical |  |  |

#### ToolBench-IR + governance (Sec. 6.3 text)

| Row | Column | 0.1.10 | 0.4.2 | Δ | Status | 0.1.10 control | Restored by |
|---|---|---|---|---|---|---|---|
| ToolBench-IR alone (no governance) | recall@5 | 0.847 [0.832, 0.862] | 0.847 [0.832, 0.862] | +0.0000 | identical |  |  |
| ToolBench-IR alone (no governance) | ndcg@5 | 0.793 [0.778, 0.808] | 0.793 [0.778, 0.808] | +0.0000 | identical |  |  |
| BEAR governance + ToolBench-IR (oracle categories) | recall@5 | 0.842 [0.826, 0.858] | 0.842 [0.826, 0.858] | +0.0000 | identical |  |  |
| BEAR governance + ToolBench-IR (oracle categories) | ndcg@5 | 0.789 [0.773, 0.805] | 0.789 [0.773, 0.805] | +0.0000 | identical |  |  |