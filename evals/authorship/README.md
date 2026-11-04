# Authorship ablation

Claude Sonnet 4.6 wrote three sets of metadata the paper uses:
- the MetaTool tool tags (`plugin_tags.json`, 199 tools)
- the MetaTool top-5 query tags (`query_tags_top5.json`, 21,111 queries)
- the inferred ToolBench categories (top-1, multi, top-5, 1,100 queries each)

The categories are inferred per query, not per API. The 3,225 ToolBench APIs keep their oracle categories.

This ablation writes all five again with a second model family, the local Qwen3.8-27B served by SGLang on 127.0.0.1:8355. It then reruns the tables that use them and reports both taggers. A reviewer can then see whether the results depend on the tagger. Scott runs it with `reproduce/65_authorship.sh`. The kit's README has its place in the run order.

## Only the client differs

The original generators are run unchanged. They own the prompts, the closed vocabularies, the tool schemas, the parsing, the retries, the validation and the failure rules:
- `evals/metatool_tagging.py`, `metatool_generate_tags.py`, `metatool_generate_query_tags_top5.py`
- `evals/eval_toolbench_inferred_categories.py`, `eval_toolbench_multitag_categories.py`, `eval_toolbench_top5_categories.py`

They post Anthropic Messages requests with `urllib`. `evals/authorship_regenerate.py` (written in WP6) replaces `urllib.request.urlopen` in its own process with a shim. The shim turns each request into `/v1/chat/completions` on the SGLang endpoint and turns the reply back into the Anthropic shape, so the originals' own code reads it. This follows the vendor-shim pattern of paper-knowledge-flow's `facts/make_questions.py`. There, `_OPENAI` switches the vendor, and `_OpenAIClient` with `_OpenAIMessages` offers `messages.create` over chat/completions. Here the same switch sits at the wire, because the originals call `urllib`, not an SDK client. The Anthropic path stays as it is, and the kit never reaches it. The shim refuses every host except the SGLang endpoint, and no key leaves the process.

`tag.py` adds what this ablation needs on top of that shim.

## Files

| File | What it does | Resources |
|---|---|---|
| `tag.py` | writes the five tag sets, logs every call, checks the server | 8355 |
| `validate.py` | the originals' validation on every logged reply, every failure and fallback counted | CPU |
| `eval_tagged.py` | MetaTool+Tags and MetaTool+QueryTags-top5 with other tag files, via `evals/wp0_v040/eval_toolbench_v040.py` | as the backend |
| `analyze.py` | tagger agreement and the retrieval results under each tagger | CPU |
| `tests/test_offline.py` | canned replies, malformed ones included, no network | CPU |
| `../authorship_regenerate.py` | the shim, the drivers of the original generators, `compare` and `evaluate` | |

## Decoding and the server

- **Temperature 0.** This is the originals' own value, carried in their requests.
- **A fixed seed, 20261104** (`seed` in the request). At temperature 0 SGLang decodes greedily, so the seed matters only where the server would sample. Server batching can still change a reply at a near-tie, as it can for any served model.
- **Thinking off** (`chat_template_kwargs.enable_thinking = false`). Please confirm. The reasons:
  - Sonnet ran without extended thinking, so thinking on would change more than the client.
  - The originals cap the reply at 300 tokens for the tag tool calls and at 64 or 256 for the category answers. Those caps were set for a model that does not think. Qwen3's thinking would spend them and cut the answer short. A cut answer fails the originals' validation, and then their failure rules apply.
  - Tagging is a choice from a closed vocabulary. It needs no long reasoning.
  - `--thinking` turns it on, if Scott prefers it.
- **top_k is not sent.** SGLang rejects 0, and the originals send none.
- **Tool calls.** The MetaTool generators force a tool call whose schema enumerates the vocabulary. Anthropic treats an enum as a soft guide, and SGLang's tool-call grammar may enforce it strictly. So the second tagger may produce fewer out-of-vocabulary tags. That is a property of the server, and `validate.py` counts it for both taggers.
- **Concurrency.** The MetaTool generators run `--workers` requests at a time (default 4). This is never above the server's `max_running_requests` minus 2, nor above 8, so other clients keep room. The ToolBench classifiers send one request at a time, as written.
- **Before the first request** `tag.py` reads the server's queue (`/get_load`, or `/metrics`). It refuses to start when requests are queued. It also refuses when other requests are running, unless `--share-server`. It never flushes the server's cache.
- **The server's identity** is recorded at the start and after every target: `get_server_info` (by allow-list, as `hermes/provenance.py` does), `get_model_info` and `/v1/models`. A changed model path, revision or version stops the run.

## The record of every call

`calls.jsonl` has one line per request. It holds:
- the target and the item (tool name or query)
- the hashes of the system prompt, user prompt, tool schema and translated request
- the raw reply (text, and the tool-call arguments as the server sent them)
- the served model id, finish reason, usage, latency and HTTP status
- the shim's parse outcome: `tool_call`, `no_tool_call`, `bad_tool_arguments`, `text`, `empty_text`, `http_error` or `transport_error`

`manifest.json` holds the run settings, the server's identity, the hashes of the generator sources and the system prompts.

## Resume, failures and fallbacks

- The MetaTool generators keep their own `--resume` and periodic flush. The ToolBench classifiers keep their per-query cache, saved every 25 queries.
- `tag.py --passes 3` reruns any target that still has missing items, with `--resume`. So an item that failed gets the originals' retries again.
- The originals' rules decide what a failure becomes, and `validate.py` counts each case, for both taggers:
  - MetaTool tool tags. A reply without a valid tag raises `TaggingError`, and the tool is left out of the file. At evaluation an absent tool carries no required tags.
  - MetaTool query tags. A reply without a domain tag raises `TaggingError`, and the query is left out of the file. It is then missing from the MetaTool+QueryTags-top5 set.
  - ToolBench top-1. An out-of-vocabulary answer becomes the empty tag, so the query is not gated. An empty reply makes the original code stop. `validate.py` counts it as `empty_reply`.
  - ToolBench multi and top-5. Out-of-vocabulary labels are dropped, and an empty set leaves the query ungated.
- `reproduce/65_authorship.sh` fails when a target loses more than 1% of its items (`AUTH_MAX_MISSING`).

## The reruns

- **MetaTool+Tags and MetaTool+QueryTags-top5, every backend of Table 9.** BM25, hash, BGE, BGE-M3 and Qwen3-0.6B run on the CPU. Qwen3-4B runs on the GPU, and Nemotron on 8360. Both governed and ungated rows are rerun, because the ungated tool texts carry the tag header too. They go through `eval_tagged.py`, so the conditions are built exactly as in the WP0 runs. Only the tag files differ.
  - The tagged tool texts and the tagged queries change, so the dense backends embed them anew.
  - Ungated queries carry no tags, so they hit the WP0 embedding cache.
- **Table 7 (ToolBench inferred categories, BGE only, as the paper reports it).** This is `authorship_regenerate.py evaluate`. It builds the retrievers as the three category scripts do, and runs the oracle, Sonnet, second-tagger and ungoverned arms side by side.
- **The Sonnet side** of each pair is the WP0 run of the kit (steps `tb_bge`, `tb_bm25` and so on), with the committed tag files.
  - For Qwen3-4B every step of the kit runs at encode batch 2 (`REPRO_Q4B_BATCH`), 20_'s reported rows included, so `tb_auth_q4b` pairs with 20_'s `tb_qwen4b` at one batch size. `AUTH_Q4B_BATCH` overrides it for 65_ alone, and `analyze.py` notes any batch difference it finds in the runs' provenance.

## The analysis

`analyze.py` writes `analysis/authorship.{json,md}`.
- **Agreement.**
  - per-tool Jaccard and exact set agreement, and first-tag agreement and kappa
  - Cohen's kappa per tag, from each tag's presence on each tool, or on each query, under the two taggers
  - query-tag Jaccard
  - the gate-pass ceiling under the four combinations of tool and query taggers
  - ToolBench category agreement: top-1 kappa, per-category kappa for the sets, accuracy against the oracle category, McNemar between the taggers
- **Retrieval, per backend and condition.**
  - governed Recall@5 and NDCG@5 under each tagger, with 95% bootstrap CIs
  - the paired difference, second tagger minus Sonnet
  - the governed-minus-ungated effect under each tagger, which is the claim that must survive
  - the difference of the two effects

  MetaTool+Tags pairs queries by position. MetaTool+QueryTags-top5 pairs them by query and tools, because each tagger's file has its own order. The tests are a paired bootstrap (10,000 resamples, seed 42), the paired t-test and the Wilcoxon test, with d = mean(diff) / sd(diff).

## Cost per backend

| Part | Backend or step | Resource | Time (estimate) |
|---|---|---|---|
| tag | 199 tools | 8355 | about 2 min |
| tag | 21,111 queries | 8355, 4 at a time | about 1.5 to 3 h |
| tag | 3 x 1,100 ToolBench queries | 8355, one at a time | about 1 to 1.5 h |
| cpu | BM25, hash | CPU, 8G | a few minutes each |
| cpu | BGE | CPU, 20G | about 30 min |
| cpu | BGE-M3 | CPU, 20G | about 1.5 h |
| cpu | Qwen3-0.6B | CPU, 20G | about 2.5 h |
| cpu | Table 7 (BGE) | CPU, 20G | about 20 min |
| gpu | Qwen3-4B | local GPU | about 15 to 20 min |
| nemotron | Nemotron | 8360 | about 30 to 45 min |
| analyze | | CPU | about 15 min |

To save time, drop BGE-M3 and Qwen3-0.6B from the CPU part (`--backends "bm25 hash bge"`).

## Offline tests

```bash
python -m unittest discover -s evals/authorship/tests -v        # or: bash reproduce/65_authorship.sh --part test
python evals/authorship/tag.py generate --dry-run                # one translated request per target, nothing sent
```
