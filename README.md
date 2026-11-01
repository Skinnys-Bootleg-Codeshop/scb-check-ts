> [!WARNING]
> **This repository is vibe coded and has not been reviewed.** AI agents wrote all of the changes in this fork, and no human has read or reviewed the code. Automated AI review ran, but that is not human review. Treat it as an experiment: don't rely on it, and don't run it on anything sensitive without reading it first. Not affiliated with or endorsed by the upstream author.

## Limits: read these before quoting a number

**Plain words, first.** We tested whether these scores separate agent-written code from human-written code. Verbosity did not. Erosion did. The pattern-rule share did, narrowly,
and mostly because of one rule. The clone signal is below the precision we aimed for. The scores do not measure whether code is correct. Compare them only with our own earlier runs.

- **Verbosity did not separate agent from human code:** 3.57% for the agent group (two agent-written Next.js applications, A and B, and a spent hold-out, 57,124 SLOC) against 3.98% for the human group (hyper, Kap, appsmith and vercel/commerce at their last commits before June 2021, 109,890 SLOC). The human group is higher, driven by commerce (6.17%, clone-heavy).
- **Erosion did separate them:** 0.720 for the agent group against 0.350 for the human group (cognitive erosion 0.838 against 0.611). Agent code concentrates more of its complexity mass in functions over the cutoff of 10.
- **Pattern-rule share did separate them, narrowly:** 1.127% of agent SLOC is flagged by the TypeScript rules against 0.764% of human SLOC (215 and 470 hits). Two caveats. The agent repos were also the repos the rules were calibrated on, so they are not a clean test. And appsmith is 71% of the human group's SLOC, so the human figure is mostly one repo (per repo the human range is 0.34% to 0.87%, and appsmith and hyper are about as high as application A's 0.92%).
- **One rule carries the agent group's pattern-rule share.** Measured on the agent group at the frozen rules: `ts-nested-ternary` accounts for 528 of the 644 flagged lines (82.0%), `ts-as-unknown-as` for 36 (5.6%) and `ts-push-loop` for 28 (4.3%). Lines flagged by two rules count for both, so these shares add to a little over 100%. The human group's biggest rules are `ts-else-after-return` (30.8%), `ts-as-any` (15.6%) and `ts-nested-ternary` (14.0%). Leave nested ternaries out and the human group's rule-flagged lines are 0.66% of SLOC against 0.21% for the agent group (sums over rules). So the pattern-rule result is "agents write more nested ternaries here", not "agents write more of everything the rules look for".
- **The clone signal is below target precision.** On 30 sampled clone groups per repo, 63.3% were real clones in application A and 46.2% in application B (all 13 groups), against a 70% target, even after the filter. Expression-bodied arrows and markup skeletons are the usual noise. Delta output labels the clone row "below target precision".
- **The scores do not measure correctness.** They count shape: duplicated blocks, flagged patterns and concentrated complexity. Code can score well and be wrong, or score badly and be right.
- **Compare only with our own earlier runs** of the same tool and rule set (`delta` output stamps the rule count, and the tool commit when run from a git checkout). A TypeScript number is not comparable with the benchmark's Python numbers, or with another team's.
- **Complexity follows the benchmark's definition, not React's.** Nested functions fold into the enclosing function, so roughly half the high-complexity `.tsx` components are high only because inner callbacks fold in (application A 25 of 52, application B 7 of 14). `??` and `?.` add nothing, `switch` adds one, function expressions are not counted as functions, and a callback inside `const Foo = () => {}` takes the name `Foo`; that moves erosion by under 0.005. A `/>` or `>` alone on a line counts as a line of code (2.2% of application A's `.tsx` SLOC).
- **Known skip:** a file with `export type * from "./x"` fails to parse in the pinned grammar and is skipped whole, with a warning and a count (3 files in application A). Other grammar failures skip files the same way: 122 appsmith files did not parse, for reasons other than this construct.
- **Comment-only hits cannot count.** Only lines of code score, so a rule that matches a comment alone adds nothing; the narration-comment rule matches the statement after the comment.
- **No `.jsx`, `.mts` or `.cts`, no TypeScript structural rules, no `// scbc ignore` for TypeScript.**
- **Rules unproven on real code:** a rule with no hits on our repos kept only its test fixtures as evidence; the calibration report marks each one "unproven on real code" or "thin evidence".

# scb-check

> Fork of [gabeorlanski/scb-check](https://github.com/gabeorlanski/scb-check) (Apache-2.0), seeded from upstream a8618228. This fork lives at `github.com/Skinnys-Bootleg-Codeshop/scb-check-ts`.
> It is being extended to score TypeScript and Next.js repos as well as Python. `.tsx` files are scanned; `.jsx` files are not. TypeScript-specific behaviour (test and generated exclusions, size cap) sits behind `--profile ts`. What changed is listed in [NOTICE](NOTICE).
> Scoring formulas are unchanged from upstream.

Python CLI that reports SCBench verbosity and erosion composites for supported source codebases.

- [Paper](https://arxiv.org/abs/2603.24755)
- [Source](https://github.com/gabeorlanski/scb-check)
- [SlopCodeBench (main repo)](https://github.com/SprocketLab/slop-code-bench)

- **Verbosity**: fraction of SLOC flagged by clone detection, ast-grep slop rules, or structural rules. Python gets all three. TypeScript and TSX get clone detection plus 27 TypeScript ast-grep rules under `--profile ts`, and no structural rules. Other languages contribute clone lines only.
- **Erosion**: share of function "mass" (`complexity * sqrt(sloc)`) concentrated in high-complexity functions (cyclomatic complexity > 10).
- **Cognitive erosion**: same mass-share calculation using cognitive complexity > 10.

## Install

Requires Python 3.12+.

Run without installing (recommended):

```bash
uvx --from git+https://github.com/Skinnys-Bootleg-Codeshop/scb-check-ts scb-check check PATH --profile ts
```

Or install into the current project:

```bash
uv sync              # for development in this repo
uv add "scb-check @ git+https://github.com/Skinnys-Bootleg-Codeshop/scb-check-ts"     # as a dependency elsewhere; PyPI's scb-check is upstream, without these changes
```

For hash-checked dependency installs from this repository, use the exported lock files:

```bash
python -m pip install --require-hashes -r requirements.lock
python -m pip install --require-hashes -r requirements-dev.lock
```

Regenerate them after dependency changes with:

```bash
uv export --format requirements.txt --no-dev --no-emit-project --frozen --output-file requirements.lock
uv export --format requirements.txt --all-groups --no-emit-project --frozen --output-file requirements-dev.lock
```

`scb-check` runs bundled ast-grep rules by trying a global `sg` executable first. If global `sg` is missing or fails, it falls back to the `ast-grep-cli` executable installed with `scb-check`.

## Usage

```bash
scb-check check PATH                    # human-readable flags
scb-check check PATH --output-format json  # JSON report with verbosity/erosion scores
scb-check check PATH --report           # shortcut for --output-format json
scb-check check PATH -v / --verbosity   # add info logging
scb-check check PATH -vv                # add debug logging
scb-check check PATH --config FILE      # explicit config path
scb-check check PATH --include-all      # include gitignored files plus ignored, lower-severity, and boundary-suppressed findings
scb-check check PATH --disable-sg  # skip ast-grep subprocess findings
scb-check check PATH --min-duplicate-lines N  # show duplicate groups with at least N SLOC lines
scb-check rule RULE_ID                  # print YAML or metadata for a specific rule
scb-check check PATH [PATH ...]         # score the union of several paths; overlaps count once
scb-check check app lib --profile ts --strict-sg  # the TypeScript profile (below); a broken rule file exits 2
```

`PATH` may be a file or directory. Directories are walked for supported source files: Python (`.py`, `.pyw`), Rust (`.rs`), JavaScript (`.js`, `.mjs`, `.cjs`), TypeScript (`.ts`, `.tsx`), Zig (`.zig`), Haskell (`.hs`), and C++ (`.cpp`, `.cc`, `.cxx`, `.c++`, `.hpp`, `.hh`, `.hxx`). Directory discovery respects `.gitignore` globs by default; use `--include-all` to scan gitignored supported files too.

### JSON report fields

`verbosity`, `erosion`, `cog_erosion`, `files_scanned`, `total_loc`, `verbosity_flagged_loc`, `clone_loc`, `ast_grep_flagged_loc`, `structural_rule_loc`, `structural_rule_findings`, `total_functions`, `high_cc_functions`, `high_cog_functions`, `total_mass`, `high_cc_mass`, `total_cog_mass`, `high_cog_mass`, `syntax_tree_count`, `syntax_node_count`, and `syntax_by_language`.

`syntax_by_language` is keyed by language value and reports `tree_count` plus total Tree-sitter `node_count` for parsed files in that language.

### Exit codes

`scb-check check` exits `0` when no findings are reported, `1` when any finding is present (clones, ast-grep hits, structural findings, or high-complexity functions), and `2` for usage errors (bad path, missing config, invalid directives).

Clone detection only emits duplicated syntax blocks with at least two executable body statements. Function signatures, comments, blanks, and Python docstrings do not satisfy that threshold; displayed clone line counts and `--min-duplicate-lines` still use duplicated `SLOC` in the clone span.

## TypeScript and Next.js

Comparable means the same formulas, not the same numbers: the benchmark has no TypeScript rules, so our TypeScript scores
use the benchmark's verbosity and erosion formulas (`src/scb_check/reporting/score.py` is unchanged, and a test pins its hash) with rules we wrote.
With no flag, Python and `.ts` files score exactly as upstream a8618228 (`tests/golden/` and `scripts/compare-to-pristine` prove it). `.tsx` is always scanned.

`--profile ts` bundles the TypeScript behaviour. Run it from the repository root, because the exclusions match paths relative to the working directory:

- **Exclusions:** `tests/`, `test/`, `__tests__/`, `__mocks__/`, `e2e/`, `playwright/`, `fixtures/`, `__fixtures__/`, `*-fixture/`, `*-fixtures/`, `*.test.ts(x)`, `*.spec.ts(x)`, `*.stories.ts(x)`, `*.d.ts`, `.next/`, `.contentlayer/`, `out/`, `coverage/`, `generated/`, `__generated__/`, `_generated/`, `*.generated.ts(x)`, `*.gen.ts(x)` (`TS_EXCLUDES` in `src/scb_check/config.py`), plus files over 1 MiB.
- **Clone filter:** `no-jsx-dominated`. A one-line arrow such as `(x) => x.id` is not a clone candidate.
- **Rules:** 27 TypeScript ast-grep rules in `src/scb_check/resources/slop_rules_typescript/`, run in an `ast-grep` process of their own, separate from the Python rules, so a broken TypeScript rule cannot silence Python hits. One broken TypeScript rule does silence every TypeScript hit in that run, which is why `--strict-sg` exists. Thirteen of the 40 written were pruned by measurement (`docs/calibration/2026-11-rule-calibration.md`).
- `--strict-sg` turns an `ast-grep` failure into exit `2` instead of a warning and zero hits. `delta` always uses it.

### Score a pull request

```bash
cd path/to/repo
path/to/scb-check/scripts/pr-delta --base origin/main app lib   # Markdown block for a PR description
path/to/scb-check/scripts/pr-delta --base origin/main --format json app lib  # the same numbers as JSON
```

`delta` scores the merge base and the head, each from a temporary export of the committed files, and prints base, head and delta for verbosity, erosion, cog_erosion, SLOC and flagged SLOC, plus the new flagged lines.
It is a report, not a gate: exit `0` whatever the direction of change. Other exits: `2` usage, `3` git state (missing ref, no merge base), `4` analysis failure, `5` over `--max-seconds` (default 900), `130` interrupted.
It runs read-only git only (`rev-parse`, `merge-base`, `status`, `cat-file`, `symbolic-ref`, `ls-tree`, `remote` to list names, `diff`), never checks out, fetches or stashes, and never touches the working tree. Uncommitted changes are not scored. If a file fails to parse on one side only, the deltas print `incomparable` rather than a wrong number.
Baseline numbers: `docs/baselines/2026-11-baseline.md`.

## Configuration

scb-check looks for `scb-check.toml` or a `pyproject.toml` containing `[tool.scb-check]`, `[tool.ruff]`, or `[tool.ty.src]`, walking upward from the current directory until it hits a `.git` root.

```toml
# scb-check.toml
exclude = ["tests/fixtures/*", "vendor/**"]
context = 1

[low-use-short-function]
enabled = true
max-call-sites = 2
max-function-sloc = 5
max-inline-caller-sloc = 50
max-inline-caller-complexity = 10
max-inline-caller-cognitive-complexity = 10
max-inline-call-nesting = 3
```

```toml
# pyproject.toml
[tool.scb-check]
exclude = ["tests/fixtures/*"]
context = 2

[tool.scb-check.low-use-short-function]
enabled = true
```

- `exclude`: list of glob patterns to skip while discovering supported source files.
- `context`: number of surrounding source lines to show around human-readable ast-grep, structural rule, and erosion findings.
- `low-use-short-function`: opt-in budgets for the short low-use helper rule. Set `enabled = true` to enable it, then tune `max-call-sites`, `max-function-sloc`, `max-inline-caller-sloc`, `max-inline-caller-complexity`, `max-inline-caller-cognitive-complexity`, and `max-inline-call-nesting`.

Configured `exclude` patterns still apply when `--include-all` is used; only `.gitignore` file discovery is extended.

Structural rules and source directives are Python-only. Python ast-grep rules run on Python files; TypeScript ast-grep rules run on `.ts` and `.tsx` files under `--profile ts` only. Rust, JavaScript, Zig, Haskell, and C++ still participate in SLOC totals, clone detection, cyclomatic erosion, and cognitive erosion.

When using `pyproject.toml`, scb-check also includes excludes from:

- `[tool.ruff].exclude`
- `[tool.ruff].extend-exclude`
- `[tool.ty.src].exclude`

## Source directives

In Python files, you can suppress specific ast-grep or structural rule findings at the source line level with:

```python
# scbc ignore[rule-id]
# scbc ignore[trivial-wrapper]
```

Same-line form:

```python
value = cfg.get("a", {}).get("b", {})  # scbc ignore[chained-dict-get] Boundary normalization for legacy webhook payloads.
```

Standalone block form:

```python
# scbc ignore[chained-dict-get]
# Boundary normalization for legacy webhook payloads.
value = cfg.get("a", {}).get("b", {})
```

Multiple rule IDs:

```python
# scbc ignore[chained-dict-get,dict-get-empty-dict-default]
# Legacy webhook payloads are partially populated and normalized downstream.
value = cfg.get("a", {}).get("b", {})
```

Function-level boundary suppression is available for code that intentionally validates or normalizes external input:

```python
def _load_toml(path: Path) -> dict[str, Any]:
    # scbc boundary: reads and validates user config
    ...
```

Boundary directives must be inside the function body, after the `def` line. By default, ast-grep findings inside that function are hidden, and informational ast-grep rules are omitted. Use `--include-all` to show ignored, informational, and boundary-suppressed ast-grep findings.

Rules:

- Rule IDs inside `ignore[...]` are required.
- Reason text is optional.
- Same-line ignore directives apply to that same physical line.
- Standalone ignore directives apply to the next non-blank, non-comment code line.
- Boundary directives apply to the containing function body.
- Ast-grep and structural rule findings are suppressible; clone and erosion findings are not.
- Invalid directives fail the run with exit code `2` unless `--include-all` is used.

## How it works

- **Tree walking**: language dispatch backed by tree-sitter grammars emits language-agnostic `ModuleIR` and semantic project context.
- **Clone detection**: hashed AST blocks across the scanned set; two or more matching instances become a `CloneBlock`.
- **Slop patterns**: Python ast-grep rules in `src/scb_check/resources/slop_rules/`, and TypeScript rules in `src/scb_check/resources/slop_rules_typescript/` (`--profile ts`), split by category (e.g. `range(len(x))`, `dict.get(k, None)`, `isinstance` ladders, manual min/max, defensive guards).
- **Structural rules**: typed Python classes in `src/scb_check/rules/` run over tree-walking IR. `trivial-wrapper` flags removable single-return pass-through functions (identity returns and calls that only forward parameters to another scanned function), while semantic keep reasons skip constant returns, default-backed value providers, external calls, decorated functions, dunder methods, and inherited API implementations. `low-use-short-function` flags short helpers with few resolved call sites only when inlining them would stay within configured caller SLOC, complexity, cognitive complexity, and nesting budgets.
- **Extra local slop patterns**: set `SCB_CHECK_EXTRA_SLOP_RULES` to a `:`-separated list of YAML paths to layer additional rules on top of the bundled set.
- **Complexity**: per-function cyclomatic and cognitive complexity plus SLOC, combined into mass scores for erosion metrics.

## Documentation

- [Docs index](docs/index.md)
- [Architecture and concepts](docs/architecture.md)
- [Current status and development approach](docs/development.md)
- [Rule calibration](docs/calibration/2026-11-rule-calibration.md), [baseline](docs/baselines/2026-11-baseline.md) and [TSX spike](docs/spikes/2026-11-tsx-spike.md)

## Development

```bash
uv run pytest
uv run ruff check
uv run ty check src/
```
