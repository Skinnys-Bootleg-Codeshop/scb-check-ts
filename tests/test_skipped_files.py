from __future__ import annotations

from pathlib import Path

from scb_check.pipeline import analyze_files


def test_parse_failure_listed(tmp_path: Path) -> None:
    """Parse failure listed."""
    bad = tmp_path / "bad.ts"
    bad.write_text("export type * from './x';\nfunction (((\n")
    good = tmp_path / "good.ts"
    good.write_text("export function f() {\n  const a = 1;\n  return a;\n}\n")
    result = analyze_files((bad, good), disable_sg=True)
    assert result.skipped_files == (bad,)
    assert good in result.source_lines_by_file


def test_recursion_error_skips_file(tmp_path: Path) -> None:
    """Recursion error skips file."""
    lines = ["export function f(x: number): number {"]
    for index in range(600):
        keyword = "if" if index == 0 else "} else if"
        lines.extend([f"  {keyword} (x === {index}) {{", f"    return {index};"])
    lines.extend(["  }", "  return -1;", "}"])
    deep = tmp_path / "deep.ts"
    deep.write_text("\n".join(lines) + "\n")
    good = tmp_path / "good.ts"
    good.write_text("export function g() {\n  const a = 1;\n  return a;\n}\n")
    result = analyze_files((deep, good), disable_sg=True)
    assert good in result.source_lines_by_file


def test_clone_overflow_is_skipped_and_unscored(tmp_path: Path) -> None:
    """A file whose clone scan overflows recursion is listed and not scored."""
    deep = tmp_path / "deep.py"
    deep.write_text("if True:\n    x = " + " + ".join(["1"] * 1100) + "\n    y = 2\n")
    good = tmp_path / "good.py"
    good.write_text("def f():\n    a = 1\n    return a\n")
    result = analyze_files((deep, good), disable_sg=True)
    assert result.skipped_files == (deep,)
    assert set(result.source_lines_by_file) == {good}
