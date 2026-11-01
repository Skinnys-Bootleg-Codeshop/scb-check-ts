from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from scb_check.cli import main
from scb_check.commands import check as check_module
from scb_check.config import Config
from scb_check.pipeline import AnalysisResult

_BODY = "export function f(x: number) {\n  const a = x + 1;\n  return a;\n}\n"
if TYPE_CHECKING:
    import pytest

runner = CliRunner()


def _tree(root: Path) -> None:
    for rel in ("a/x.ts", "b/y.tsx", "b/skip/z.ts"):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_BODY)


def _run(monkeypatch: pytest.MonkeyPatch, root: Path, *args: str) -> dict:
    monkeypatch.chdir(root)
    result = runner.invoke(main, ["check", *args, "--report", "--disable-sg"])
    assert result.exit_code in {0, 1}, result.output
    return json.loads(result.stdout)


def test_two_paths_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two paths union."""
    _tree(tmp_path)
    report = _run(monkeypatch, tmp_path, "a", "b")
    assert report["total_loc"] == 9


def test_overlapping_paths_counted_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overlapping paths counted once."""
    _tree(tmp_path)
    assert _run(monkeypatch, tmp_path, "b", "b/skip", "b/y.tsx")["total_loc"] == 6


def test_single_path_calls_analyze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single path calls analyze."""
    _tree(tmp_path)
    calls: list[object] = []
    real = check_module.analyze

    def spy(path: Path, config: Config, **kwargs: bool) -> AnalysisResult:
        calls.append(path)
        return real(path, config, **kwargs)

    monkeypatch.setattr(check_module, "analyze", spy)
    _run(monkeypatch, tmp_path, "a")
    assert calls == [Path("a")]


def test_exclude_option(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Exclude option."""
    _tree(tmp_path)
    report = _run(monkeypatch, tmp_path, "b", "--exclude", "b/skip/**")
    assert report["total_loc"] == 3
