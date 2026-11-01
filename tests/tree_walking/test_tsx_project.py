from __future__ import annotations

from pathlib import Path

from scb_check.analysis.clones import detect_clones
from scb_check.pipeline import analyze_files
from scb_check.tree_walking.dispatch import parse_source_file

_PAGE = "export default function Page() {\n  const a = 1;\n  return a;\n}\n"
_THREE = "export function same(x: number) {\n  const a = x + 1;\n  const b = a * 2;\n  return b;\n}\n"
_ONE = "export function one(x: number) {\n  return x + 1;\n}\n"


def test_two_page_files_both_scored(tmp_path: Path) -> None:
    """Two page files both scored."""
    files = []
    for name in ("a", "b"):
        directory = tmp_path / name
        directory.mkdir()
        file = directory / "page.tsx"
        file.write_text(_PAGE)
        files.append(file)
    result = analyze_files(tuple(files), disable_sg=True)
    assert len(result.flags.findings.all_functions) == 2


def test_ts_and_tsx_share_clone_group(tmp_path: Path) -> None:
    """Ts and tsx share clone group."""
    ts = tmp_path / "a.ts"
    tsx = tmp_path / "b.tsx"
    ts.write_text(_THREE)
    tsx.write_text(_THREE)
    parsed = tuple(parse_source_file(f, f.read_text()) for f in (ts, tsx))
    clones = detect_clones(parsed)
    assert len(clones) == 2
    assert {clone.group_hash for clone in clones} == {clones[0].group_hash}
    assert {clone.file for clone in clones} == {ts, tsx}


def test_tsx_clone_requires_two_statements(tmp_path: Path) -> None:
    """Tsx clone requires two statements."""
    files = []
    for name in ("a.tsx", "b.tsx"):
        file = tmp_path / name
        file.write_text(_ONE)
        files.append(file)
    parsed = tuple(parse_source_file(f, f.read_text()) for f in files)
    assert detect_clones(parsed) == ()
