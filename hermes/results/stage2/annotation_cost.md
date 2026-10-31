# Annotation cost per request (offline, stage-1 C-gate and D selections)

Tokens BEAR's annotation adds to each request at session scope, by level. 4 characters a token (BEAR's `text_tokens`). Annotations off add 0.

| Role | Decoys | none | counts | names10 | names |
| --- | --- | --- | --- | --- | --- |
| operator | 0 | 499 | 499 | 499 | 499 |
| operator | 100 | 716 | 736 | 885 | 2078 |
| operator | 300 | 716 | 736 | 891 | 5098 |
| guest | 0 | 170 | 189 | 292 | 340 |
| guest | 100 | 387 | 407 | 555 | 1911 |
| guest | 300 | 387 | 407 | 562 | 4931 |
