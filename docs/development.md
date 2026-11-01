# Development

This guide summarizes the current implementation status and the preferred approach for common changes.

## Current status

`scb-check` is a Python CLI with two public commands:

- `scb-check check PATH` reports human-readable flags or JSON scores.
- `scb-check rule RULE_ID` prints bundled `ast-grep` YAML or structural rule metadata.

Implemented analysis paths:

- Source discovery for supported Python, Rust, JavaScript, TypeScript, Zig, Haskell, and C++ suffixes.
- Tree-sitter parsing into language-agnostic IR.
- `SLOC` accounting shared by verbosity, clone line counts, and rule spans.
- Duplicate-structure detection by normalized AST hashing for all supported languages.
- Bundled Python `ast-grep` slop patterns, plus optional local rules from `SCB_CHECK_EXTRA_SLOP_RULES`.
- Structural rules over `ProjectIR`; the current bundled Python rules are `trivial-wrapper` and opt-in `low-use-short-function`.
- Cyclomatic and cognitive erosion scores for all supported languages.
- Python source ignores for `ast-grep` and structural rule IDs.
- Python boundary suppression for validation/normalization functions.

## Runtime contracts

- `scb-check check` exits `0` with no findings, `1` when any finding is reported (see `commands/check.py`), and `2` for usage errors. `scb-check delta` is a report, not a gate: it exits `0` whatever the direction of change.
- Exit `2` is for user-facing failures such as bad config, bad paths, unknown rules, invalid directives, or no discoverable supported source files.
- Individual parse failures warn and skip the file instead of aborting the run.
- Non-Python files skip Python ast-grep rules, structural rules, and source directives. TypeScript and TSX files get the TypeScript rule set under `--profile ts` only.
- Config discovery and source-directive behavior are user-facing; keep README examples synchronized when they change.

## PR delta

`scripts/pr-delta [PATHS...]`, run from the repository being scored, calls `scb-check delta`. It scores the merge base and the head of a pull request in a temporary export of the committed files (`git ls-tree` plus `git cat-file --batch`, so `.gitattributes` `export-ignore` cannot hide source), then prints base, head and delta for verbosity, erosion, cog_erosion, SLOC and flagged SLOC, plus the new flagged lines.

- Options: `--repo`, `--base` (default `origin/dev`), `--head` (default `HEAD`), `--profile` (default `ts`), `--exclude`, `--format md|json`, `--max-lines`, `--max-seconds` (default 900). ast-grep is always strict.
- Read-only: the scanned repo is never checked out or modified. Git verbs are `rev-parse`, `merge-base`, `status`, `cat-file`, `symbolic-ref`, `ls-tree` and `diff`, all with `--no-optional-locks`. Uncommitted changes are warned about and not scored.
- It reports and never gates. Exit `0` whatever the direction of change; `2` usage; `3` git state (missing ref, no merge base); `4` analysis failure (including ast-grep); `5` timeout; `130` interrupted.
- If a file is parsed on one side only, every delta cell reads `incomparable` and the output names the file.
- Under `--profile ts` the table carries `clone_loc` as its own row, flagged "below target precision" (spike outcome, `docs/spikes/2026-11-tsx-spike.md`).

## Where to make changes

| Change | Primary location |
| --- | --- |
| CLI command or option | `src/scb_check/commands/` |
| Config loading or path walking | `src/scb_check/config.py`, `src/scb_check/walker.py` |
| Source parsing, `SLOC`, directives, IR | `src/scb_check/tree_walking/`; see [Tree walking](tree-walking.md) |
| Language parser configs | `src/scb_check/tree_walking/languages/` |
| Clone detection | `src/scb_check/analysis/clones.py` |
| `ast-grep` integration | `src/scb_check/analysis/astgrep.py` and `src/scb_check/resources/slop_rules/` |
| Structural rule behavior | `src/scb_check/rules/` |
| JSON scores or human rendering | `src/scb_check/reporting/` |
| Shared analysis/reporting records | `src/scb_check/models.py` |

## Adding an `ast-grep` rule

1. Add or update YAML under `src/scb_check/resources/slop_rules/` (Python) or `src/scb_check/resources/slop_rules_typescript/` (TypeScript: write `language: typescript`; loading adds a `language: tsx` twin with the same id unless `metadata.no_tsx_twin` is true; never use `severity: error`, which makes `sg` exit 1 and discards every hit).
2. Use a unique rule ID across both `ast-grep` and structural rules.
3. Set severity and any `min_file_count` metadata deliberately.
4. Add behavioral tests that exercise `pipeline.run_sg` through monkeypatching rather than invoking `sg`; TypeScript rules instead get real ast-grep fixtures.
5. Update README or docs if the rule changes user-facing behavior or scoring expectations.

## Adding a structural rule

1. Add a rule class under `src/scb_check/rules/`.
2. Keep rule metadata immutable: `id`, `severity`, `languages`, `target`, and `description`.
3. Operate on `SymbolIR` or another typed IR subject plus `RuleContext`; do not inspect tree-sitter nodes.
4. Register the rule in `rules/registry.py`.
5. Ensure the rule ID does not collide with bundled `ast-grep` rule IDs.
6. Test observable findings, ignore behavior, report fields, and rendering prefixes.

## Adding a language

1. Add the tree-sitter grammar dependency.
2. Add a `Language` enum value, parser module/config under `tree_walking/languages/`, dispatch suffix mapping, and discovery coverage.
3. Add clone node/literal/identifier config so `analysis/clones.py` can hash duplicate blocks.
4. Add behavioral parser, clone, and pipeline tests.
5. Document whether ast-grep rules, directives, and structural rules apply to the language.

## Changing scoring

Treat scoring changes as public behavior changes. Update tests first, then implementation, then docs.

Pay special attention to:

- `verbosity` as a union, never a sum,
- `SLOC` as the denominator for verbosity and the source of counted flagged lines,
- non-Python verbosity includes clone LOC, plus TypeScript ast-grep LOC under `--profile ts`, but not Python ast-grep or structural rule LOC,
- high-complexity threshold `> 10`,
- mass formulas for `erosion` and `cog_erosion`,
- line spans used by clone, `ast-grep`, and structural findings.

## Verification

Run the project workflow after changes:

```bash
uv run ruff check --fix .
uv run ty check .
uv run pytest
uv run scb-check check .
uv run vulture
```

Use focused tests while iterating, then run the full workflow before presenting results. Keep tests behavioral: assert scores, exit codes, report fields, and rendering prefixes instead of internal call order.
