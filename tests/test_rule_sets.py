"""Rule-set routing in the resources layer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from typer.testing import CliRunner

from scb_check.cli import main
from scb_check.resources import RuleSet
from scb_check.resources import find_rule_document
from scb_check.resources import is_clean_rule_text
from scb_check.resources import rule_texts

if TYPE_CHECKING:
    import pytest

_EXTRA = """---
id: extra-ts
language: typescript
severity: warning
message: ts extra
rule:
  pattern: debugger
---
id: extra-py
language: python
severity: warning
message: py extra
rule:
  pattern: pass
---
id: extra-ts-only
language: typescript
severity: warning
message: ts only
metadata:
  no_tsx_twin: true
rule:
  pattern: debugger
"""


def _docs(rule_set: RuleSet) -> list[dict[str, object]]:
    return [
        document
        for _, text in rule_texts(rule_set)
        for document in yaml.safe_load_all(text)
        if isinstance(document, dict)
    ]


def _extra(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "extra.yaml"
    path.write_text(_EXTRA, encoding="utf-8")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(path))


def test_default_rule_texts_python_only() -> None:
    """With no argument only Python rules are yielded."""
    documents = [
        document
        for _, text in rule_texts()
        for document in yaml.safe_load_all(text)
        if isinstance(document, dict)
    ]
    assert {document["language"] for document in documents} == {"python"}


def test_ts_rule_set_twins_tsx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A typescript rule is emitted with a tsx twin of the same id."""
    _extra(monkeypatch, tmp_path)
    pairs = [
        (document["id"], document["language"])
        for document in _docs(RuleSet.TYPESCRIPT)
    ]
    assert ("extra-ts", "typescript") in pairs
    assert ("extra-ts", "tsx") in pairs


def test_no_tsx_twin_metadata_respected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`metadata.no_tsx_twin` suppresses the twin."""
    _extra(monkeypatch, tmp_path)
    languages = [
        document["language"]
        for document in _docs(RuleSet.TYPESCRIPT)
        if document["id"] == "extra-ts-only"
    ]
    assert languages == ["typescript"]


def test_extra_rules_routed_by_language(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Python extras stay in the Python set; TS extras go to the TS set."""
    _extra(monkeypatch, tmp_path)
    ts_ids = {document["id"] for document in _docs(RuleSet.TYPESCRIPT)}
    assert "extra-py" not in ts_ids
    assert "extra-ts" in ts_ids
    assert "extra-py" in {document["id"] for document in _docs(RuleSet.PYTHON)}


def test_find_rule_document_ts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """`find_rule_document` searches the TypeScript set too."""
    _extra(monkeypatch, tmp_path)
    document = find_rule_document("extra-ts")
    assert document is not None
    assert document["language"] == "typescript"


def test_rule_command_prints_ts_rule(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`scb-check rule <id>` prints a TypeScript rule's YAML."""
    _extra(monkeypatch, tmp_path)
    result = CliRunner().invoke(main, ["rule", "extra-ts"])
    assert result.exit_code == 0
    assert "id: extra-ts" in result.stdout


def test_ts_alias_and_malformed_extras(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """`language: ts` is routed and twinned; malformed YAML never raises."""
    alias = tmp_path / "alias.yaml"
    alias.write_text(
        "---\nid: a-ts\nlanguage: ts\nseverity: warning\nmessage: m\nrule:\n  pattern: debugger\n",
        encoding="utf-8",
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: [unclosed\n", encoding="utf-8")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", f"{alias}:{bad}")
    ts = [(d["id"], d["language"]) for d in _docs(RuleSet.TYPESCRIPT)]
    assert ("a-ts", "ts") in ts
    assert ("a-ts", "tsx") in ts
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(alias))
    assert "a-ts" not in {d.get("id") for d in _docs(RuleSet.PYTHON)}


def test_malformed_bundled_ts_text_is_passed_through() -> None:
    """Unparseable or non-mapping rule text is not dropped or raised on."""
    assert not is_clean_rule_text("language: typescript\nrule: [\n")
    assert not is_clean_rule_text("- a\n- b\n")
    assert is_clean_rule_text("id: x\nlanguage: typescript\n")
