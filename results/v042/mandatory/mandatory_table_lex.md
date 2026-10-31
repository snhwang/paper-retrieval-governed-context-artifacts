| Backend | Level | Query set | n | Safety present 0.1.10 (mean) | queries missing any (0.1.10) | Safety present 0.4.2 (mean) | F1 0.1.10 | F1 0.4.2 | Switch restoring 0.1.10 counts |
|---|---|---|---|---|---|---|---|---|---|
| bm25 | Full governance | Standard | 60 | 2.77 | 7 | 3.00 | 0.865 | 0.875 | none |
| hash | Full governance | Standard | 60 | 2.95 | 3 | 3.00 | 0.841 | 0.845 | none |
| bm25 | Full governance | Paraphrase | 60 | 3.00 | 0 | 3.00 | 0.890 | 0.890 | (unchanged) |
| hash | Full governance | Paraphrase | 60 | 3.00 | 0 | 3.00 | 0.886 | 0.886 | (unchanged) |
| bm25 | Full governance | No-tag | 54 | 3.00 | 0 | 3.00 | 0.718 | 0.718 | (unchanged) |
| hash | Full governance | No-tag | 54 | 3.00 | 0 | 3.00 | 0.837 | 0.837 | (unchanged) |
| bm25 | Full governance | Complex | 60 | 2.92 | 3 | 3.00 | 0.856 | 0.866 | none |
| hash | Full governance | Complex | 60 | 2.97 | 2 | 3.00 | 0.891 | 0.896 | none |
| bm25 | Mandatory only | Standard | 60 | 2.47 | 26 | 3.00 | 0.478 | 0.550 | none |
| hash | Mandatory only | Standard | 60 | 2.28 | 33 | 3.00 | 0.431 | 0.518 | none |
| bm25 | Mandatory only | Paraphrase | 60 | 2.35 | 25 | 3.00 | 0.384 | 0.467 | none |
| hash | Mandatory only | Paraphrase | 60 | 2.50 | 25 | 3.00 | 0.416 | 0.481 | none |
| bm25 | Mandatory only | No-tag | 54 | 2.24 | 31 | 3.00 | 0.378 | 0.479 | none |
| hash | Mandatory only | No-tag | 54 | 2.85 | 8 | 3.00 | 0.447 | 0.469 | none |
| bm25 | Mandatory only | Complex | 60 | 2.38 | 32 | 3.00 | 0.480 | 0.557 | none |
| hash | Mandatory only | Complex | 60 | 2.43 | 28 | 3.00 | 0.405 | 0.477 | none |
