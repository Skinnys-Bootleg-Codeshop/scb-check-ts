# Contributor note

`scb-check` is a Python CLI that reports verbosity and erosion for source codebases. This fork adds TypeScript and `.tsx` scoring, TypeScript ast-grep rules and a pull-request delta. See [README.md](README.md) for usage and for the warning that the fork is vibe coded and has not been reviewed.

- Do not change `src/scb_check/reporting/score.py` or the mass methods in `src/scb_check/tree_walking/models.py`: the scoring formulas match upstream and `tests/golden/` checks it.
- With no flag, Python and `.ts` score exactly as upstream. TypeScript behaviour sits behind `--profile ts`.
- Do not create a GitHub release: `.github/workflows/publish.yml` publishes on a release.
- `ty` is the type checker, not mypy.
- Verbosity is a union of clone lines and ast-grep lines per file, intersected with SLOC lines. Do not double-count.
- Dataclasses are `frozen=True, slots=True`; pass tuples across module boundaries.

Before sending a change:

```bash
uv run ruff check --fix .
uv run ty check .
uv run pytest
uv run vulture
```

Maintainer guides are in [docs/index.md](docs/index.md). Keep them in step with behaviour.
