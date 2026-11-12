# Authorship ablation: analysis plan

Status: version 2, 2026-11-12. Version 1 approved by Scott. Version 2 adds one rule (see Changes) and awaits his approval. Under "Specs yes, gates no" (9 Nov 2026), this plan is written and hashed before any run. Its sha256 is recorded in the paper repo's `revision-plan.md` when Scott approves it. A later change gets a new version of this file and a dated entry under "Changes" saying what changed and why.

## Question

Do the paper's tag-based results depend on the model that wrote the tags?

Claude Sonnet 4.6 wrote three sets of metadata the paper uses:
- the MetaTool tool tags (199 tools)
- the MetaTool top-5 query tags (21,111 queries)
- the inferred ToolBench categories (top-1, multi, top-5, 1,100 queries each)

Reviewer 1 asked what role the AI models play in the pipeline. Reviewer 2 asked how much the gains depend on metadata quality. This ablation writes all five sets again with a second model family and reruns the tables that use them.

## Design

Everything below is already implemented in `evals/authorship/` and `reproduce/65_authorship.sh`. The README in this folder has the details.

- **Second tagger.** Qwen3.8-27B, served by SGLang on 127.0.0.1:8355. No paid API.
- **Only the client differs.** The original generators run unchanged, with their prompts, closed vocabularies, tool schemas, parsing, retries, validation and failure rules. A shim turns their Anthropic requests into chat/completions requests on 8355.
- **Decoding.** Temperature 0 (the originals' value), seed 20261104, thinking off. Sonnet ran without extended thinking, and the originals' token caps leave no room for thinking.
- **Reruns.**
  - MetaTool+Tags and MetaTool+QueryTags-top5 on all seven backends of Table 9 (BM25, hash, BGE, BGE-M3, Qwen3-0.6B, Qwen3-4B, Nemotron), governed and ungated, through the same runner as the WP0 rows. Only the tag files differ.
  - Table 7 (ToolBench inferred categories, BGE, as the paper reports it), with oracle, Sonnet, second-tagger and ungoverned arms side by side.
- **The Sonnet side** of every comparison is Scott's kit run of the same condition (steps 10, 20 and 30), on BEAR 0.4.2. Qwen3-4B runs at encode batch 2 on both sides.
- **Completeness.** A target that loses more than 1% of its items fails the run. Every failure and fallback is counted for both taggers.

## Outcomes

### Primary

The governance effect under each tagger, per backend and condition. The effect is governed minus ungated Recall@5, paired by query, with a 95% paired bootstrap CI (10,000 resamples, seed 42). These are the effects Table 9's tag rows and their text claim.

For each backend and condition the report gives:
- the effect under Sonnet and under the second tagger, with CIs
- the difference of the two effects (second tagger minus Sonnet), with its CI

### Secondary

- Governed Recall@5 and NDCG@5 under each tagger, and their paired difference.
- The same effect measures with NDCG@5.
- Table 7: Recall@5, NDCG@5 and F1@5 per arm, and the second tagger's inferred categories against Sonnet's and against the oracle (paired differences with CIs).
- Paired t-test and Wilcoxon p-values and d = mean(diff) / sd(diff) beside each bootstrap CI.

### Descriptive

Tagger agreement, with no test attached:
- per-tool Jaccard, exact set agreement, first-tag agreement and kappa
- Cohen's kappa per tag
- query-tag Jaccard
- the gate-pass ceiling under the four combinations of tool and query taggers
- ToolBench category agreement: top-1 kappa, per-category kappa for the sets, accuracy against the oracle, McNemar between the taggers
- out-of-vocabulary tags, failures and fallbacks per tagger

## How the results are read

These rules are fixed now, before any run.

- **Cannot tell** applies first. Where Sonnet's own effect has a 95% CI that includes zero, there is no effect to hold, and the cell reads "cannot tell". The report still gives both effects and their difference with CIs.
- **The effect holds** on a backend and condition when the second tagger's effect has the same sign as Sonnet's and its 95% CI excludes zero. This applies in both directions. MetaTool+Tags helps every backend under Sonnet. MetaTool+QueryTags hurts the dense backends and helps the lexical ones.
- **The effect is comparable** when the CI of the difference of effects lies within ±0.02 Recall@5. If the CI includes zero but reaches past ±0.02, the text says the data cannot tell, and gives the interval.
- **The effect differs** when the CI of the difference of effects excludes zero. The text gives the size, both as a difference and as a fraction of Sonnet's effect.
- **Table 7.** The claim at stake is the ordering: oracle above the inferred conditions, and where each inferred condition sits against ungoverned. The ordering holds when it is the same under both taggers, read from the paired CIs.
- No backend or condition is dropped from the report. Every number goes into the results file and the appendix table, whatever it shows.

## What the paper says

- **Holds on every backend and condition.** One or two sentences in Provenance of Tags (Section 4.1). The full table goes in an appendix. The response to Reviewers 1 and 2 cites it.
- **Holds on some.** The same, plus a sentence naming where it fails and a line in Limitations on dependence on the tagger.
- **Reverses anywhere.** The claims that rest on the affected condition are revised in the text, the abstract if needed, and the letter.

Agreement statistics are reported as description, not as evidence for or against the claim.

## Resources and order

About 10.5 hours, in parts that fit gaps between other windows (see `reproduce/README.md`):
- tag: 8355, 3 to 5 h
- cpu: CPU, about 5 h
- gpu: local GPU, 20 min
- nemotron: 8360, 45 min
- analyze: CPU, 15 min

The cpu, gpu and nemotron parts need the Sonnet-side runs of steps 10, 20 and 30 first. Scott runs every part himself.

## Decisions for Scott

1. Thinking off (recommended, reasons above). `--thinking` turns it on.
2. All seven backends (recommended). Dropping BGE-M3 and Qwen3-0.6B saves about 4 h of CPU time.
3. The ±0.02 Recall@5 margin for "comparable".

## Changes

- **2026-11-12, version 2.** Version 1 (sha256 1f7b1168209af75256773f483d1def11ef545da6614bea879ef7c7530af746a1) was approved by Scott with thinking off, all seven backends and the ±0.02 margin. Added the "cannot tell" rule for cells where Sonnet's own effect CI includes zero. Version 1 would have read such a cell as "does not hold", although there was no effect to hold. Suggested by Work PM, approved by Scott before any run.
