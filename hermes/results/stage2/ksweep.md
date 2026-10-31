# C-cut k sweep (offline, stage-1 records)

BM25 replays: catalog digest mismatches 0, offered-set mismatches 0.

## bm25, narrow_query first_plus_message

Needed-tool groups 1047 (operator cells, first turn), called samples 3036, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 27. With required 1.0 and called >= 0.99: 30.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.580 | 0.323 | 0.267 |
| 5 | 0.836 | 0.453 | 0.349 |
| 8 | 0.931 | 0.590 | 0.432 |
| 10 | 0.948 | 0.698 | 0.564 |
| 12 | 0.974 | 0.763 | 0.659 |
| 15 | 0.974 | 0.825 | 0.747 |
| 20 | 0.974 | 0.871 | 0.805 |
| 25 | 0.974 | 0.924 | 0.856 |
| 30 | 1.000 | 0.998 | 0.996 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.923 / 0.645 | 0.949 / 0.804 | 0.974 / 0.830 | 0.974 / 0.854 | 0.974 / 0.884 |
| 100 | 0.923 / 0.569 | 0.949 / 0.667 | 0.974 / 0.741 | 0.974 / 0.812 | 0.974 / 0.861 |
| 300 | 0.948 / 0.561 | 0.948 / 0.630 | 0.974 / 0.723 | 0.974 / 0.810 | 0.974 / 0.867 |

## bm25, narrow_query message

Needed-tool groups 1047 (operator cells, first turn), called samples 3036, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 27. With required 1.0 and called >= 0.99: 30.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.580 | 0.324 | 0.266 |
| 5 | 0.836 | 0.450 | 0.347 |
| 8 | 0.931 | 0.586 | 0.427 |
| 10 | 0.948 | 0.695 | 0.563 |
| 12 | 0.974 | 0.760 | 0.657 |
| 15 | 0.974 | 0.821 | 0.745 |
| 20 | 0.974 | 0.869 | 0.804 |
| 25 | 0.974 | 0.924 | 0.856 |
| 30 | 1.000 | 0.998 | 0.996 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.923 / 0.645 | 0.949 / 0.804 | 0.974 / 0.830 | 0.974 / 0.854 | 0.974 / 0.884 |
| 100 | 0.923 / 0.565 | 0.949 / 0.663 | 0.974 / 0.738 | 0.974 / 0.805 | 0.974 / 0.859 |
| 300 | 0.948 / 0.552 | 0.948 / 0.624 | 0.974 / 0.717 | 0.974 / 0.807 | 0.974 / 0.864 |

## nemotron, narrow_query first_plus_message

Needed-tool groups 1047 (operator cells, first turn), called samples 2970, cells 1184.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 30. With required 1.0 and called >= 0.99: 34.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.415 | 0.222 | 0.183 |
| 5 | 0.538 | 0.296 | 0.193 |
| 8 | 0.737 | 0.439 | 0.297 |
| 10 | 0.863 | 0.548 | 0.410 |
| 12 | 0.900 | 0.616 | 0.479 |
| 15 | 0.953 | 0.727 | 0.603 |
| 20 | 0.983 | 0.853 | 0.773 |
| 25 | 1.000 | 0.907 | 0.845 |
| 30 | 1.000 | 0.960 | 0.922 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.751 / 0.538 | 0.871 / 0.716 | 0.900 / 0.762 | 0.963 / 0.811 | 1.000 / 0.877 |
| 100 | 0.729 / 0.393 | 0.860 / 0.467 | 0.897 / 0.548 | 0.949 / 0.691 | 0.974 / 0.842 |
| 300 | 0.731 / 0.390 | 0.858 / 0.470 | 0.902 / 0.546 | 0.948 / 0.683 | 0.974 / 0.842 |

## nemotron, narrow_query message

Needed-tool groups 1047 (operator cells, first turn), called samples 3036, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 30. With required 1.0 and called >= 0.99: 34.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.415 | 0.226 | 0.178 |
| 5 | 0.538 | 0.299 | 0.188 |
| 8 | 0.737 | 0.441 | 0.290 |
| 10 | 0.863 | 0.549 | 0.403 |
| 12 | 0.900 | 0.617 | 0.470 |
| 15 | 0.953 | 0.728 | 0.592 |
| 20 | 0.983 | 0.856 | 0.776 |
| 25 | 1.000 | 0.908 | 0.847 |
| 30 | 1.000 | 0.960 | 0.920 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.751 / 0.541 | 0.871 / 0.718 | 0.900 / 0.764 | 0.963 / 0.813 | 1.000 / 0.878 |
| 100 | 0.729 / 0.397 | 0.860 / 0.470 | 0.897 / 0.550 | 0.949 / 0.693 | 0.974 / 0.845 |
| 300 | 0.731 / 0.393 | 0.858 / 0.472 | 0.902 / 0.548 | 0.948 / 0.685 | 0.974 / 0.846 |

