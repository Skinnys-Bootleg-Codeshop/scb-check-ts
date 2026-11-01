# Baseline, November 2026

Two agent-written applications (A and B) scored with the frozen TypeScript rule set. These are numbers to compare with **our own later runs**, not with the benchmark's
Python numbers: the formulas are the benchmark's, the TypeScript rules are ours (see the README's limits section).

- Rule set frozen at **27 rules** (13 of the 40 written were pruned; the pruned rules and the threshold each failed are in [the calibration report](../calibration/2026-11-rule-calibration.md#the-candidates-named-in-the-brief)).
- Command, from each application's root (the walker matches the profile's excludes relative to it): `scb-check check <paths> --profile ts --strict-sg --report`. Numbers below come from `scripts/baseline_report.py`, on 2026-11-01.
- Wall time of the `check` command itself (warm cache): A 2.19 s, peak 135 MB; B 0.82 s, peak 75 MB. All far under the time limits.

## Scores

| Measure | A | B |
| --- | --- | --- |
| files scanned | 469 | 89 |
| SLOC | 42,489 | 13,006 |
| verbosity | 0.0386 | 0.0277 |
| erosion | 0.6957 | 0.7905 |
| cog_erosion | 0.8247 | 0.8817 |
| verbosity-flagged SLOC | 1,641 | 360 |
| clone SLOC (below target precision) | 1,251 | 123 |
| ast-grep-flagged SLOC | 391 | 237 |
| ast-only share | 0.92% | 1.82% |
| skipped files | 3 | 0 |

Skipped files: A 3 and B 0. All three are the known `export type * from` grammar gap, which drops the whole file; their code is not scored.

## Top ten rules by flagged SLOC: application A

| Rule | Hits | Flagged SLOC |
| --- | --- | --- |
| `ts-nested-ternary` | 78 | 317 |
| `ts-as-unknown-as` | 23 | 34 |
| `ts-null-and-undefined-check` | 15 | 17 |
| `ts-push-loop` | 8 | 15 |
| `ts-self-ternary` | 1 | 5 |
| `ts-narration-comment` | 2 | 2 |
| `ts-accumulator-loop` | 1 | 1 |
| `ts-if-return-bool` | 1 | 1 |
| `ts-inline-error-message` | 1 | 1 |
| `ts-json-clone` | 1 | 1 |

## Top ten rules by flagged SLOC: application B

| Rule | Hits | Flagged SLOC |
| --- | --- | --- |
| `ts-nested-ternary` | 52 | 196 |
| `ts-push-loop` | 7 | 13 |
| `ts-filter-push-loop` | 3 | 9 |
| `ts-null-and-undefined-check` | 5 | 8 |
| `ts-inline-error-message` | 5 | 5 |
| `ts-as-unknown-as` | 2 | 2 |
| `ts-declare-then-return` | 2 | 2 |
| `ts-self-ternary` | 1 | 1 |
| `ts-template-single-expr` | 1 | 1 |

## Not proven

- Rules are judged on two agent-written applications and one spent hold-out. See the README limits.
- No number here has been checked against the SlopCodeBench paper's own values for TypeScript; the paper has none.
