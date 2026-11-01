"""Helpers for the TypeScript rule fixture tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from scb_check.analysis.astgrep import run_sg_strict
from scb_check.models import AstGrepHit

RULES_DIR = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "scb_check"
    / "resources"
    / "slop_rules_typescript"
)
FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ts_rules"
HIT_MARKER = "// HIT"
HIT_NEXT_MARKER = "// HIT-NEXT"


@dataclass(frozen=True, slots=True)
class RuleCase:
    """One rule document and where it came from."""

    rule_id: str
    language: str
    document: dict[str, object]
    source: Path

    @property
    def variants(self) -> tuple[str, ...]:
        """Fixture suffixes the rule must pass on."""
        return ("ts", "tsx") if self.language == "typescript" else ("tsx",)


def load_rule_cases() -> tuple[RuleCase, ...]:
    """Read every rule document from the bundled TypeScript rule files."""
    cases: list[RuleCase] = []
    for path in sorted(RULES_DIR.glob("*.yaml")):
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8")):
            if not isinstance(document, dict):
                continue
            cases.append(
                RuleCase(
                    rule_id=str(document["id"]),
                    language=str(document["language"]),
                    document=document,
                    source=path,
                ),
            )
    return tuple(cases)


def fixture_path(rule_id: str, kind: str, suffix: str) -> Path:
    """Return the fixture file for `rule_id`, `kind` (pos or neg) and `suffix`."""
    return FIXTURES_DIR / rule_id / f"{kind}.{suffix}"


def source_fixture(rule_id: str, kind: str) -> Path | None:
    """Return the authored fixture for a rule, `.ts` first then `.tsx`."""
    for suffix in ("ts", "tsx"):
        candidate = fixture_path(rule_id, kind, suffix)
        if candidate.is_file():
            return candidate
    return None


def expected_hit_lines(path: Path) -> tuple[int, ...]:
    """Lines a rule must hit: `// HIT` marks its own line, `// HIT-NEXT` the next.

    `// HIT-NEXT` exists for hits such as `catch {}`, where a trailing comment
    on the same line would change how the statement parses.
    """
    expected: list[int] = []
    for number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if HIT_NEXT_MARKER in line:
            expected.append(number + 1)
        elif HIT_MARKER in line:
            expected.append(number)
    return tuple(expected)


def run_rule(
    case: RuleCase,
    fixture: Path,
    suffix: str,
    work_dir: Path,
) -> tuple[AstGrepHit, ...]:
    """Run only `case`'s rule over a copy of `fixture` named `.suffix`."""
    document = dict(case.document)
    document["language"] = "typescript" if suffix == "ts" else "tsx"
    rules_path = work_dir / f"{case.rule_id}-{suffix}.yml"
    rules_path.write_text(
        yaml.safe_dump(document, sort_keys=False),
        encoding="utf-8",
    )
    target = work_dir / f"{case.rule_id}-{suffix}-{fixture.stem}.{suffix}"
    target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    hits = run_sg_strict((target,), rules_path)
    return tuple(hit for hit in hits if hit.rule_id == case.rule_id)
