# C-cut k sweep (offline, stage-1 records)

BM25 replays: catalog digest mismatches 0, offered-set mismatches 0.

## bm25, narrow_query first_plus_message

Needed-tool groups 1078 (operator cells, first turn), called samples 3114, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **31**. With required >= 0.95: 27. With required 1.0 and called >= 0.99: 31.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.566 | 0.325 | 0.257 |
| 5 | 0.741 | 0.446 | 0.361 |
| 8 | 0.933 | 0.590 | 0.429 |
| 10 | 0.942 | 0.685 | 0.540 |
| 12 | 0.967 | 0.761 | 0.640 |
| 15 | 0.975 | 0.828 | 0.729 |
| 20 | 0.975 | 0.878 | 0.799 |
| 25 | 0.975 | 0.920 | 0.841 |
| 30 | 0.983 | 0.990 | 0.975 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.925 / 0.652 | 0.950 / 0.795 | 0.975 / 0.826 | 0.975 / 0.843 | 0.975 / 0.890 |
| 100 | 0.925 / 0.549 | 0.925 / 0.643 | 0.975 / 0.744 | 0.975 / 0.828 | 0.975 / 0.872 |
| 300 | 0.950 / 0.571 | 0.950 / 0.623 | 0.950 / 0.717 | 0.975 / 0.813 | 0.975 / 0.871 |

## bm25, narrow_query message

Needed-tool groups 1078 (operator cells, first turn), called samples 3114, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **31**. With required >= 0.95: 27. With required 1.0 and called >= 0.99: 31.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.566 | 0.324 | 0.253 |
| 5 | 0.741 | 0.443 | 0.358 |
| 8 | 0.933 | 0.587 | 0.428 |
| 10 | 0.942 | 0.683 | 0.540 |
| 12 | 0.967 | 0.759 | 0.639 |
| 15 | 0.975 | 0.827 | 0.728 |
| 20 | 0.975 | 0.878 | 0.800 |
| 25 | 0.975 | 0.920 | 0.841 |
| 30 | 0.983 | 0.989 | 0.974 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.925 / 0.651 | 0.950 / 0.794 | 0.975 / 0.825 | 0.975 / 0.844 | 0.975 / 0.891 |
| 100 | 0.925 / 0.547 | 0.925 / 0.642 | 0.975 / 0.743 | 0.975 / 0.827 | 0.975 / 0.872 |
| 300 | 0.950 / 0.566 | 0.950 / 0.619 | 0.950 / 0.713 | 0.975 / 0.811 | 0.975 / 0.870 |

## nemotron, narrow_query first_plus_message

Needed-tool groups 1078 (operator cells, first turn), called samples 3032, cells 1174.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 30. With required 1.0 and called >= 0.99: 35.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.433 | 0.228 | 0.182 |
| 5 | 0.550 | 0.303 | 0.196 |
| 8 | 0.741 | 0.439 | 0.296 |
| 10 | 0.863 | 0.561 | 0.406 |
| 12 | 0.895 | 0.624 | 0.471 |
| 15 | 0.950 | 0.731 | 0.580 |
| 20 | 0.974 | 0.859 | 0.760 |
| 25 | 1.000 | 0.910 | 0.840 |
| 30 | 1.000 | 0.951 | 0.893 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.736 / 0.532 | 0.878 / 0.718 | 0.911 / 0.761 | 0.950 / 0.805 | 0.975 / 0.869 |
| 100 | 0.740 / 0.392 | 0.846 / 0.488 | 0.880 / 0.557 | 0.950 / 0.692 | 0.972 / 0.854 |
| 300 | 0.747 / 0.398 | 0.864 / 0.488 | 0.894 / 0.563 | 0.950 / 0.699 | 0.975 / 0.856 |

## nemotron, narrow_query message

Needed-tool groups 1078 (operator cells, first turn), called samples 3114, cells 1239.
Smallest k covering >= 0.99 of needed groups and >= 0.95 of called tools: **30**. With required >= 0.95: 30. With required 1.0 and called >= 0.99: 35.

| k | Needed groups covered | Called tools covered | Cells with every called tool |
| --- | --- | --- | --- |
| 3 | 0.433 | 0.233 | 0.177 |
| 5 | 0.550 | 0.307 | 0.192 |
| 8 | 0.741 | 0.442 | 0.291 |
| 10 | 0.863 | 0.564 | 0.404 |
| 12 | 0.895 | 0.627 | 0.468 |
| 15 | 0.950 | 0.733 | 0.575 |
| 20 | 0.974 | 0.862 | 0.759 |
| 25 | 1.000 | 0.912 | 0.840 |
| 30 | 1.000 | 0.952 | 0.893 |
| 35 | 1.000 | 1.000 | 1.000 |

| Decoys | k=8 needed / called | k=10 | k=12 | k=15 | k=20 |
| --- | --- | --- | --- | --- | --- |
| 0 | 0.736 / 0.537 | 0.878 / 0.723 | 0.911 / 0.766 | 0.950 / 0.811 | 0.975 / 0.872 |
| 100 | 0.740 / 0.394 | 0.846 / 0.489 | 0.880 / 0.560 | 0.950 / 0.692 | 0.972 / 0.856 |
| 300 | 0.747 / 0.399 | 0.864 / 0.488 | 0.894 / 0.562 | 0.950 / 0.701 | 0.975 / 0.857 |

