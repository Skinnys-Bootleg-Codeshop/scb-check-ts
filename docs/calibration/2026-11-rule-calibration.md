# Rule calibration, November 2026

## What the first pass got wrong

The first calibration (25 rules kept) ended in a failed acceptance criterion, kept here, with the application name replaced and one internal plan reference removed:

> **Outcome: acceptance criterion D3 not met.** The hold-out ast-only share (0.061%) does not exceed application A's (0.106%). The rule set, after pruning, does not separate the sloppy hold-out from real code on the ast-grep signal. No rule was edited after the freeze and none will be tuned to the hold-out.

There are two reasons that this test could not have told us anything:
1. At application A's rate the hold-out's 1,629 SLOC expected about 1.7 hits and got 1. One hit cannot be told apart from one more or one fewer.
2. Applications A and B are themselves agent-written, so neither is a control group.

Also, the labellers never saw the real rubric (`configs/prompts/anti_slop.jinja`), because it lives in SprocketLab/slop-code-bench and not in this fork. The relabel below fixes that.
The hold-out is spent: it is never used for tuning, and it validates nothing changed after the first pass.

## Relabel with the real rubric

- Rubric: `configs/prompts/anti_slop.jinja` and `configs/rubrics/llm_judge.jsonl` from SprocketLab/slop-code-bench fetched as text at commit `af5a9cbc311605b5cceb80200ca9832bdff2d7b1`.
- A fresh blind subagent (claude-sonnet-5-5) re-labelled every one of the 325 labelled rows from the snippet (two lines either side), the rule message, the rubric and the plan's true-positive definition, with no hit rates and no earlier labels: 123 true positives, 202 false positives.
- A second blind subagent re-labelled a seeded 10% (32 rows, seed 1233) and disagreed with the first on 2 (6.3%, under the 20% limit, so no relabel).
- The plan thresholds were reapplied in order, unchanged, to the new labels and the original (first-run, all 40 rules) measurements. Three rules landed in the tighten bands. `ts-as-unknown-as` (65% on the new labels) had not been tightened, so it was tightened once, a negative fixture was added, and a seed 1234 resample of 20 hits was labelled by a third blind subagent. `ts-nested-ternary` (line share 59.5% with 75% precision) and `ts-wrapper-function` (50% precision) were already tightened in the first pass, so are not tightened again: the seed 1234 rows were relabelled and decide them. The decision logic is `scripts/calibrate_rules.py`; a rule already tightened once is decided on its seed-1234 rows and pruned, not tightened again. The tightened `ts-nested-ternary` had been deleted with the pruned rules, so it was rebuilt from its description (comparator chains with `-1` exempt); its hit list matches the first pass's 130 hits (52 in B, 78 in A) exactly, so the seed 1234 rows still apply. `ts-if-return-bool` (80%) keeps its first-pass tightening; nothing was loosened.
- Result: 27 of 40 kept, 13 pruned. Compared with the first pass, `ts-nested-ternary` and `ts-as-unknown-as` come back (on the new labels only); `ts-wrapper-function` stays pruned. Final rule count 27 (at least 20 required). Every kept rule has a positive and a negative fixture.

Corpus: application A (469 files, 42,489 SLOC) and application B (89 files, 13,006 SLOC), `--profile ts`, `--strict-sg`, measured by `scripts/calibrate_rules.py`. Columns: hits across both repos on the original rule; file-hit rate per repo; max line share of `ast_grep_flagged_loc`; mean flagged SLOC per hit, weighted by hits across the two repos; labelled sample (tp/total) on the first pass; decision. No file-hit rate exceeded 30%.

| Rule | Hits | File-hit rate A / B | Line share | Mean span | Sample tp/n | Precision | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ts-accumulator-loop | 1 | 0.2% / 0.0% | 0.1% | 1.0 | 0/1 | 0% | keep: thin evidence |
| ts-as-any | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-as-unknown-as | 31 | 3.2% / 2.2% | 4.3% | 1.6 | 13/20 | 65% | keep: tightened once (a cast that is directly the returned expression is exempt; added as a negative fixture); resample seed 1234: precision 15/20 = 75% |
| ts-async-no-await | 50 | 3.6% / 6.7% | 7.1% | 1.4 | 4/20 | 20% | prune: precision 20% under 50% |
| ts-bool-ternary | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-boolean-wrap-boolean | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-catch-failure-result | 6 | 0.9% / 1.1% | 3.0% | 3.0 | 0/6 | 0% | prune: precision 0% under 50% |
| ts-catch-log-only | 22 | 2.1% / 0.0% | 5.1% | 2.0 | 0/20 | 0% | prune: precision 0% under 50% |
| ts-catch-rethrow | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-catch-return-null | 51 | 7.0% / 6.7% | 10.2% | 2.0 | 0/20 | 0% | prune: precision 0% under 50% |
| ts-declare-then-return | 2 | 0.0% / 2.2% | 0.6% | 1.0 | 2/2 | 100% | keep: thin evidence |
| ts-double-bang-condition | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-else-after-return | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-empty-catch | 9 | 1.5% / 0.0% | 1.0% | 1.0 | 0/9 | 0% | prune: precision 0% under 50% |
| ts-explicit-any | 7 | 1.1% / 0.0% | 0.7% | 1.0 | 3/7 | 43% | prune: precision 43% under 50% |
| ts-explicit-boolean-compare | 52 | 4.9% / 9.0% | 4.5% | 1.0 | 1/20 | 5% | prune: precision 5% under 50% |
| ts-filter-first | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-filter-push-loop | 3 | 0.0% / 2.2% | 2.7% | 3.0 | 3/3 | 100% | keep: thin evidence |
| ts-foreach-push | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-guard-ladder | 53 | 4.1% / 2.2% | 5.9% | 1.0 | 3/20 | 15% | prune: precision 15% under 50% |
| ts-if-return-bool | 5 | 0.9% / 0.0% | 0.8% | 1.4 | 4/5 | 80% | keep: precision 4/5 = 80% on the first pass; the earlier tighten (not the tail of a guard chain) stays, nothing is loosened; 1 hit left, thin evidence |
| ts-index-loop | 13 | 1.5% / 2.2% | 4.0% | 3.5 | 2/13 | 15% | prune: precision 15% under 50% |
| ts-inline-error-message | 6 | 0.2% / 1.1% | 1.5% | 1.0 | 5/6 | 83% | keep |
| ts-json-clone | 1 | 0.2% / 0.0% | 0.1% | 1.0 | 1/1 | 100% | keep: thin evidence |
| ts-jsx-useless-fragment | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-narration-comment | 2 | 0.2% / 0.0% | 0.2% | 1.0 | 0/2 | 0% | keep: thin evidence |
| ts-nested-ternary | 150 | 9.8% / 18.0% | 59.5% | 4.8 | 15/20 | 75% | keep: first-pass precision 15/20 = 75%, line share 59.5% over 25% and under 85%: tightened once (comparator chains with `-1` exempt); resample seed 1234: precision 18/20 = 90%, at least 85% |
| ts-non-null-chain | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-null-and-undefined-check | 20 | 2.6% / 2.2% | 2.4% | 1.2 | 20/20 | 100% | keep |
| ts-nullish-chain | 31 | 3.8% / 1.1% | 3.7% | 1.1 | 0/20 | 0% | prune: precision 0% under 50% |
| ts-optional-chain-long | 1 | 0.2% / 0.0% | 0.1% | 1.0 | 0/1 | 0% | keep: thin evidence |
| ts-passthrough-arrow | 46 | 4.9% / 5.6% | 4.8% | 1.0 | 3/20 | 15% | prune: precision 15% under 50% |
| ts-promise-catch-noop | 15 | 1.9% / 4.5% | 2.1% | 1.5 | 0/15 | 0% | prune: precision 0% under 50% |
| ts-push-loop | 15 | 1.1% / 4.5% | 3.9% | 1.9 | 13/15 | 87% | keep |
| ts-return-await | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-self-ternary | 2 | 0.2% / 1.1% | 0.6% | 3.0 | 2/2 | 100% | keep: thin evidence |
| ts-string-wrap-template | 0 | 0.0% / 0.0% | 0.0% | 0.0 | 0/0 | n/a | keep: unproven on real code |
| ts-template-single-expr | 1 | 0.0% / 1.1% | 0.3% | 1.0 | 1/1 | 100% | keep: thin evidence |
| ts-ts-suppress | 1 | 0.2% / 0.0% | 0.1% | 1.0 | 1/1 | 100% | keep: thin evidence |
| ts-wrapper-function | 8 | 1.1% / 1.1% | 1.8% | 2.2 | 4/8 | 50% | prune: first-pass precision 4/8 = 50%: tightened once (callee must be an identifier); resample seed 1234: precision 4/6 = 67%, under 70% |

Kept rules marked "unproven on real code" have a positive and a negative fixture and nothing more. Kept rules marked "thin evidence" had fewer than 5 hits.

### The candidates named in the brief

| Candidate | Kept | Pruned |
| --- | --- | --- |
| Casts and `any` | `as-any`, `as-unknown-as`, `non-null-chain`, `ts-suppress` | `explicit-any` |
| Swallowed catch | `catch-rethrow` | `empty-catch`, `catch-log-only`, `catch-return-null`, `promise-catch-noop` |
| JSON clone | `json-clone` | none |
| Redundant wrapping | `boolean-wrap-boolean`, `string-wrap-template`, `template-single-expr` | `wrapper-function` |
| Manual loops | `push-loop`, `accumulator-loop`, `foreach-push`, `filter-push-loop` | `index-loop` |
| Chained `?.` and `??` | `optional-chain-long` | `nullish-chain` |
| Pass-through arrows | none | `passthrough-arrow` |
| Guard ladders | none | `guard-ladder` |
| Generic failure Results | none | `catch-failure-result` |
| Narration comments | `narration-comment` | none |

Why, by candidate: the swallowed-catch rules (`empty-catch`, `catch-log-only`, `catch-return-null`, `promise-catch-noop`) were 0 to 5% precise: in these repos a caught error that is logged or answered with `null` is the intended, observable behaviour. `explicit-any` was 43% precise on 7 hits. `wrapper-function` stayed under 70% after its one tighten. `index-loop`, `passthrough-arrow`, `guard-ladder` and `nullish-chain` were 0 to 15% precise. `catch-failure-result` was 0 of 6. `narration-comment`, `json-clone`, `optional-chain-long` and the others kept as thin evidence had under 5 hits and are not judged; `ts-narration-comment` went 0 of 2 but sits below the 5-hit line.

## Frozen rule set

Frozen after the relabel at 27 rules. No rule, threshold or profile edit after it in this stage.

## Hold-out

A sealed hold-out of 21 files (1,629 SLOC) of agent-written Next.js code was hash-checked before it was read and again before the separation run: 21 of 21 matched, 0 failures. The hold-out is not in this repository.

The earlier single scoring (25 rules): ast-only share 0.061% (1 hit), against application A's 0.106%. Reason it said nothing: see the first-pass section above. At the frozen 27 rules the hold-out has 4 hits (0.982%).

## Separation test (pre-registered)

Pre-registration `docs/calibration/2026-11-separation-prereg.md`, committed before any rule score of the human repos. That ordering was in the private development history; this public fork holds one commit, so it cannot be checked here, and the text has since been edited to remove private names. The run is `scripts/separation_score.py`, `--profile ts --strict-sg`, at the frozen rules, on 2026-11-01. Human repos at the commits in the pre-registration.

| Repo | SLOC | Hits | ast-only share | Verbosity | clone_loc share | erosion | cog_erosion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| human: Kap | 11,220 | 28 | 0.392% | 3.21% | 2.82% | 0.286 | 0.459 |
| human: appsmith | 78,490 | 365 | 0.871% | 3.87% | 3.05% | 0.361 | 0.639 |
| human: commerce | 11,739 | 33 | 0.341% | 6.17% | 5.83% | 0.034 | 0.148 |
| human: hyper | 8,441 | 44 | 0.853% | 3.06% | 2.20% | 0.532 | 0.737 |
| **human pooled** | 109,890 | 470 | 0.764% | 3.98% | 3.26% | 0.350 | 0.611 |
| agent: B | 13,006 | 78 | 1.822% | 2.77% | 0.95% | 0.791 | 0.882 |
| agent: holdout | 1,629 | 4 | 0.982% | 2.21% | 1.23% | 0.658 | 0.783 |
| agent: A | 42,489 | 133 | 0.920% | 3.86% | 2.94% | 0.696 | 0.825 |
| **agent pooled** | 57,124 | 215 | 1.127% | 3.57% | 2.44% | 0.720 | 0.838 |

Skipped as unparsable: appsmith 122 files (a grammar limit), application A 3, commerce 1. Pooling is sums over sums (erosion: `high_cc_mass` over `total_mass`).

**Deviation from the pre-registration, disclosed:** before the pre-registration commit, one report of hyper's rule-free metrics (verbosity, erosion, cog_erosion, clone_loc; ast-grep off) was printed while its language mix was checked, so the pre-registration's "before scoring anything" was not met to the letter. Hyper had already been accepted by the selection order, no ast-grep score of any human repo had been seen, and the pass rule concerns the ast-only share. The result is reported as "run as pre-registered, with this one disclosed deviation". Sensitivity, computed afterwards and not used for any decision: with hyper left out the human pooled ast-only share is 0.757% (768 of 101,449 SLOC, 426 hits), against the agent group's 1.127%, so the outcome does not depend on hyper.

**Pass rule, ast-only share: PASS.** Agent pooled share 1.127% exceeds human pooled share 0.764%, with 685 hits across both groups (at least 30 required).

Measured results with no pass rule:
- Erosion: agent 0.720 against human 0.350; cog_erosion: agent 0.838 against human 0.611. Agent greater.
- Verbosity: agent 3.57% against human 3.98%. Agent **not** greater: the human group is higher, driven by commerce (6.17%, clone-heavy).

What this does and does not show:
- The agent group includes applications A and B, the corpora the rules were calibrated on (they are not a control for the rules, but were not used to choose rules after the freeze). The hold-out alone (0.982%, 4 hits) is also above the human group's 0.764%, but 4 hits is too few to carry weight.
- The human group is dominated by appsmith (71% of its SLOC); per repo, the human ast-only shares run from 0.34% (commerce) to 0.87% (appsmith), and appsmith and hyper are about as high as application A's 0.92%. The ast-only separation is therefore a difference in pooled means, not a clean split between every agent repo and every human repo.
- Four human repos is a small sample, and two are Electron apps. Erosion differs widely among humans (0.03 to 0.53), so the large erosion gap may reflect repo size and kind, not authorship.
- Nothing was tuned after this run.
