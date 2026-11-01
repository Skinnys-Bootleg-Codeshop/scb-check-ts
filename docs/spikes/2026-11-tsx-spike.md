# TSX spike

Measures what `scb-check check --profile ts` sees on real Next.js code and selects the profile's clone filter. Numbers select the outcome; none is argued.

- Tool: this fork, after the `.tsx` scanning change. Script: `scripts/spike_tsx.py`. Raw JSON and the labelled-source samples were kept machine-local; no source text is committed.
- Two agent-written Next.js applications, A and B, were measured. Both were read only.

```sh
uv run --frozen python scripts/spike_tsx.py --repo PATH/TO/APP_A --paths <paths> --seed 1233 --label a \
  --out-json OUT/a.json --sample-dir OUT/a
uv run --frozen python scripts/spike_tsx.py --repo PATH/TO/APP_B --paths src --seed 1233 --label b \
  --out-json OUT/b.json --sample-dir OUT/b
# after labelling: add --labels <sample-dir>/labels.csv (same --out-json) to compute precision
```

## Gates

| Gate | Result | Outcome |
| --- | --- | --- |
| G-parse | `.tsx` parse rate on application A 194/194 = 100% | continue |
| G-clones | V0 precision 30.0%, `.tsx` clone lines from expression-bodied arrows 31.8%. V1 63.3%. V2 63.3%. None reaches 70% | none pass: `PROFILES["ts"].clone_filter = "no-jsx-dominated"` (V2); show `clone_loc` as its own row in delta and baseline, flagged "below target precision" |
| G-time | `check --profile ts` on application A 1.7 s wall (limit 300 s) | continue |

## M1 parse

| Repo | seen | parsed | skipped |
| --- | --- | --- | --- |
| A | 194 tsx, 274 ts, 4 js | 194 tsx, 271 ts, 4 js | 3 `.ts` files (`export type *`, known grammar gap) |
| B | 12 tsx, 77 ts | all | none |

Application A holds 472 in-scope files here against the plan's 470 because four `.js` files are also scanned (supported suffix); the 3 `.ts` skips are the plan's pre-check.

## M2 callables (information)

| Repo | symbols | name taken across a function boundary | symbols if nearest parent only | erosion upstream | erosion nearest-parent |
| --- | --- | --- | --- | --- | --- |
| A | 3041 | 187 | 2854 | 0.6957 | 0.7000 |
| B | 713 | 23 | 690 | 0.7905 | 0.7916 |

The callable definition moves erosion by under 0.005 on both repos.

## M3 clone lines per variant (clone SLOC)

| Repo | V0 upstream | V1 no-expression-bodies | V2 no-jsx-dominated | V0 `.tsx` lines | `.tsx` lines V1 removes |
| --- | --- | --- | --- | --- | --- |
| A | 1980 (204 groups) | 1251 (83) | 1251 (83) | 1017 | 323 (31.8%) |
| B | 345 (54) | 123 (13) | 123 (13) | 118 | 81 (68.6%) |

"Share of `.tsx` clone lines from expression-bodied arrows" is read as the lines that exist only because of those candidates, which is exactly what V1 removes (V1 drops only those candidates and nothing nested in them).

**V2 equals V1 as specified.** The plan counts `jsx_*` node types against all nodes, tokens included. A markup-heavy component reaches about 30% (54 nodes, 17 `jsx_*`; a `<div>` with four nested elements), so the 50% cut never fires: V2 and V1 give identical numbers on both repos. The filter is implemented as specified and `test_no_jsx_dominated_equals_v1_at_the_specified_share` pins it. Counting named nodes only would change this; that is a planner decision and was not made here.

## M4 precision (30 groups per variant, seed 1233)

Labelled by an independent subagent that saw the source and the definition (section 5) and no rates.

| Repo | V0 | V1 | V2 |
| --- | --- | --- | --- |
| A | 9/30 = 30.0% | 19/30 = 63.3% | 19/30 = 63.3% |
| B | 7/30 = 23.3% | 6/13 = 46.2% (all 13 groups) | 6/13 = 46.2% |

Application B has only 13 groups under V1 and V2, so its sample is the whole population. The per-group labels are not published (91 groups, deduplicated across variants).

## M5 nested reading (information)

| Repo | `.tsx` symbols | high cyclomatic (folded) | high only because of folding | erosion folded | erosion exclusive |
| --- | --- | --- | --- | --- | --- |
| A | 916 | 52 | 25 | 0.6995 | 0.4917 |
| B | 119 | 14 | 7 | 0.8951 | 0.7190 |

Exclusive keeps the inclusive SLOC. Roughly half the high-complexity `.tsx` components are high only because inner callbacks fold into them. This is the benchmark's definition (Python folds the same way) and is documented as a limit, not retuned.

## M6 closer lines (information)

`/>` or `>` alone on a line: A 359 of 16,548 `.tsx` SLOC (2.2%); B 97 of 3,396 (2.9%).

## M7 time

| Repo | Command | Wall | Peak RSS | Skipped |
| --- | --- | --- | --- | --- |
| A | `scb-check check <paths> --profile ts` | 1.7 s | 133 MB | 3 |
| B | `scb-check check src --profile ts` | 0.6 s | 74 MB | 0 |

No ast-grep rule applies to TypeScript yet, so the run is parse, SLOC, complexity and clones.

Final scores under the selected filter (application A, 469 files scanned): verbosity 0.0294, erosion 0.6957, cog_erosion 0.8247, clone_loc 1251 of 42,489 LOC.
