"""Every bundled TypeScript rule has a firing and a silent fixture."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml
from rule_helpers import RULES_DIR
from rule_helpers import RuleCase
from rule_helpers import expected_hit_lines
from rule_helpers import load_rule_cases
from rule_helpers import run_rule
from rule_helpers import source_fixture

from scb_check.resources import RuleSet
from scb_check.resources import rule_texts

pytestmark = pytest.mark.integration

_CASES = load_rule_cases()
_PARAMS = [
    pytest.param(case, suffix, id=f"{case.rule_id}-{suffix}")
    for case in _CASES
    for suffix in case.variants
]
_MAX_SPAN_LINES = 12
_PYTHON_RULES_DIR = RULES_DIR.parent / "slop_rules"


def test_every_rule_has_fixtures() -> None:
    """Each rule id has a positive and a negative fixture."""
    missing = [
        f"{case.rule_id}/{kind}"
        for case in _CASES
        for kind in ("pos", "neg")
        if source_fixture(case.rule_id, kind) is None
    ]
    assert missing == []


@pytest.mark.parametrize(("case", "suffix"), _PARAMS)
def test_rule_fires_on_positive(
    case: RuleCase, suffix: str, tmp_path: Path
) -> None:
    """The rule hits exactly the lines the positive fixture marks."""
    fixture = source_fixture(case.rule_id, "pos")
    assert fixture is not None
    hits = run_rule(case, fixture, suffix, tmp_path)

    expected = expected_hit_lines(fixture)
    assert expected, "positive fixture marks no HIT lines"
    assert sorted({hit.line for hit in hits}) == sorted(expected)


@pytest.mark.parametrize(("case", "suffix"), _PARAMS)
def test_rule_silent_on_negative(
    case: RuleCase, suffix: str, tmp_path: Path
) -> None:
    """The near-miss fixture produces no hit."""
    fixture = source_fixture(case.rule_id, "neg")
    assert fixture is not None
    assert run_rule(case, fixture, suffix, tmp_path) == ()


@pytest.mark.parametrize(("case", "suffix"), _PARAMS)
def test_positive_hits_are_bounded(
    case: RuleCase, suffix: str, tmp_path: Path
) -> None:
    """A hit flags at most twelve lines."""
    fixture = source_fixture(case.rule_id, "pos")
    assert fixture is not None
    for hit in run_rule(case, fixture, suffix, tmp_path):
        assert hit.end_line - hit.line + 1 <= _MAX_SPAN_LINES


def test_rule_ids_prefixed_and_unique() -> None:
    """Rule ids start with `ts-` and never repeat."""
    ids = [case.rule_id for case in _CASES]
    assert all(rule_id.startswith("ts-") for rule_id in ids)
    assert len(ids) == len(set(ids))


def test_no_collision_with_python_rules() -> None:
    """No TypeScript rule id reuses a Python rule id."""
    python_ids = {
        str(document["id"])
        for path in _PYTHON_RULES_DIR.glob("*.yaml")
        for document in yaml.safe_load_all(path.read_text(encoding="utf-8"))
        if isinstance(document, dict)
    }
    assert python_ids.isdisjoint(case.rule_id for case in _CASES)


def test_no_error_severity() -> None:
    """`severity: error` makes `sg` exit 1 and discards every hit."""
    assert [
        case.rule_id for case in _CASES if case.document["severity"] == "error"
    ] == []


def test_weights_match_severity() -> None:
    """Every rule is a weight-5 slop warning."""
    for case in _CASES:
        metadata = case.document["metadata"]
        assert isinstance(metadata, Mapping)
        assert case.document["severity"] == "warning"
        assert dict(metadata) == {
            "weight": 5,
            "category": "slop",
            **({"source": "slopcheck-deslop"} if "source" in metadata else {}),
        }


def test_rule_file_accepted_by_ast_grep(tmp_path: Path) -> None:
    """The pinned ast-grep accepts the whole TypeScript rule set."""
    rules_path = tmp_path / "all.yml"
    rules_path.write_text(
        "".join(
            text if text.startswith("---") else f"---\n{text}"
            for _, text in rule_texts(RuleSet.TYPESCRIPT)
        ),
        encoding="utf-8",
    )
    target = tmp_path / "empty.ts"
    target.write_text("export const x = 1;\n", encoding="utf-8")
    binary = Path(sys.executable).parent / "ast-grep"
    result = subprocess.run(  # noqa: S603
        [str(binary), "scan", "-r", str(rules_path), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
