"""Pipeline behaviour across rule sets, with real ast-grep."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from scb_check.analysis.astgrep import AstGrepError
from scb_check.cli import main
from scb_check.config import PROFILES
from scb_check.pipeline import AnalysisResult
from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report

runner = CliRunner()

_RULES = """---
id: extra-ts-debugger
language: typescript
severity: warning
message: remove debugger
metadata: {weight: 5, category: slop}
rule:
  pattern: debugger
---
id: extra-py-pass
language: python
severity: warning
message: remove pass
metadata: {weight: 5, category: slop}
rule:
  pattern: pass
"""

_TS = "export function f(x: number) {\n  debugger;\n  return x;\n}\n"
_PY = "def f(x):\n    pass\n    return x\n"


def _tree(root: Path) -> tuple[Path, Path, Path]:
    files = (root / "a.ts", root / "b.tsx", root / "c.py")
    for file, text in zip(files, (_TS, _TS, _PY), strict=True):
        file.write_text(text, encoding="utf-8")
    return files


def _env(monkeypatch: pytest.MonkeyPatch, root: Path, text: str = _RULES) -> None:
    rules = root / "extra.yaml"
    rules.write_text(text, encoding="utf-8")
    monkeypatch.setenv("SCB_CHECK_EXTRA_SLOP_RULES", str(rules))


def _hits(result: AnalysisResult) -> set[tuple[str, str]]:
    return {
        (hit.file.name, hit.rule_id)
        for hit in result.flags.findings.ast_grep_hits
    }


@pytest.mark.integration
def test_ts_rules_on_under_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Under the profile a .ts, a .tsx and a .py file each report their hit."""
    files = _tree(tmp_path)
    _env(monkeypatch, tmp_path)
    result = analyze_files(files, rule_sets=PROFILES["ts"].rule_sets)
    assert _hits(result) == {
        ("a.ts", "extra-ts-debugger"),
        ("b.tsx", "extra-ts-debugger"),
        ("c.py", "extra-py-pass"),
    }
    assert compute_report(result.flags).to_dict()["ast_grep_flagged_loc"] == 3


@pytest.mark.integration
def test_ts_rules_off_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no profile the TS rule never fires, as before this stage."""
    files = _tree(tmp_path)
    _env(monkeypatch, tmp_path)
    assert _hits(analyze_files(files)) == {("c.py", "extra-py-pass")}


@pytest.mark.integration
def test_broken_ts_rule_keeps_python_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken TS rule set is logged and Python hits survive."""
    files = _tree(tmp_path)
    _env(
        monkeypatch,
        tmp_path,
        _RULES.replace("pattern: debugger", "kind: no_such_node_kind_xyz"),
    )
    result = analyze_files(files, rule_sets=PROFILES["ts"].rule_sets)
    assert _hits(result) == {("c.py", "extra-py-pass")}


@pytest.mark.integration
def test_strict_sg_raises_for_broken_rule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strict mode raises naming ast-grep for a broken TS rule."""
    files = _tree(tmp_path)
    _env(
        monkeypatch,
        tmp_path,
        _RULES.replace("pattern: debugger", "kind: no_such_node_kind_xyz"),
    )
    with pytest.raises(AstGrepError, match="ast-grep"):
        analyze_files(files, rule_sets=PROFILES["ts"].rule_sets, strict_sg=True)


@pytest.mark.integration
def test_strict_sg_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`check --profile ts --strict-sg` exits 2 on a broken rule; without it, warns."""
    _tree(tmp_path)
    _env(
        monkeypatch,
        tmp_path,
        _RULES.replace("pattern: debugger", "kind: no_such_node_kind_xyz"),
    )
    monkeypatch.chdir(tmp_path)
    strict = runner.invoke(
        main,
        ["check", "a.ts", "b.tsx", "c.py", "--profile", "ts", "--strict-sg", "--report"],
    )
    assert strict.exit_code == 2
    assert "ast-grep" in strict.output
    lax = runner.invoke(
        main,
        ["check", "a.ts", "b.tsx", "c.py", "--profile", "ts", "--report"],
    )
    assert lax.exit_code in {0, 1}
    assert json.loads(lax.stdout)["ast_grep_flagged_loc"] == 1


def test_thresholds_merge_across_sets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TS rule's min_file_count applies: one file is below a threshold of 2."""
    files = _tree(tmp_path)[:1]
    _env(
        monkeypatch,
        tmp_path,
        _RULES.replace(
            "metadata: {weight: 5, category: slop}\nrule:\n  pattern: debugger",
            "metadata: {weight: 5, category: slop, min_file_count: 2}\nrule:\n  pattern: debugger",
        ),
    )
    result = analyze_files(files, rule_sets=PROFILES["ts"].rule_sets)
    assert _hits(result) == set()


def test_info_rule_not_scored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TS rule with severity info is dropped like any info hit."""
    files = _tree(tmp_path)[:1]
    _env(monkeypatch, tmp_path, _RULES.replace("severity: warning", "severity: info"))
    result = analyze_files(files, rule_sets=PROFILES["ts"].rule_sets)
    assert _hits(result) == set()


def test_comment_only_hit_adds_no_verbosity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hit on a comment line is not SLOC, so it adds nothing to verbosity."""
    source = tmp_path / "a.ts"
    source.write_text("// debugger here\nexport const x = 1;\n", encoding="utf-8")
    _env(
        monkeypatch,
        tmp_path,
        """---
id: comment-hit
language: typescript
severity: warning
message: comment
metadata: {weight: 5, category: slop}
rule:
  kind: comment
""",
    )
    result = analyze_files((source,), rule_sets=PROFILES["ts"].rule_sets)
    assert len(result.flags.findings.ast_grep_hits) == 1
    assert compute_report(result.flags).to_dict()["ast_grep_flagged_loc"] == 0


@pytest.mark.integration
def test_strict_sg_validates_rules_without_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A TS rule with no explicit id is still run, and still validated strictly."""
    files = _tree(tmp_path)[:1]
    _env(
        monkeypatch,
        tmp_path,
        "---\nlanguage: typescript\nseverity: warning\nmessage: m\nrule:\n  kind: no_such_kind_xyz\n",
    )
    with pytest.raises(AstGrepError):
        analyze_files(files, rule_sets=PROFILES["ts"].rule_sets, strict_sg=True)


@pytest.mark.integration
def test_malformed_ts_rule_warns_and_keeps_python_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unparseable TS rule YAML without strict mode keeps Python hits, no crash."""
    files = _tree(tmp_path)
    _env(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "scb_check.resources._typescript_rule_texts",
        lambda: iter([("bad.yaml", "id: ts-bad\nlanguage: typescript\nrule: [\n")]),
    )
    result = analyze_files(files, rule_sets=PROFILES["ts"].rule_sets)
    assert ("c.py", "extra-py-pass") in _hits(result)
