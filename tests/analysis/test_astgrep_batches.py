"""Batching and strict mode of the ast-grep runner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scb_check.analysis import astgrep
from scb_check.analysis.astgrep import AstGrepError
from scb_check.analysis.astgrep import run_sg
from scb_check.analysis.astgrep import run_sg_strict


def _hit_line(file: Path, line: int) -> str:
    return json.dumps(
        {
            "file": str(file),
            "range": {
                "start": {"line": line, "column": 0},
                "end": {"line": line, "column": 1},
            },
            "ruleId": "x",
            "text": "t",
            "message": "m",
            "severity": "warning",
        },
    )


def _setup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_run: object,
) -> Path:
    rules = tmp_path / "rules.yaml"
    rules.write_text("---\nid: x\nrule:\n  pattern: x\n", encoding="utf-8")
    monkeypatch.setattr(astgrep.shutil, "which", lambda _: "/global/sg")
    monkeypatch.setattr(astgrep.subprocess, "run", fake_run)
    return rules


def test_run_sg_batches_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """2,500 files reach ast-grep in batches of at most 1,000."""
    sizes: list[int] = []

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        sizes.append(len(command) - 5)
        return subprocess.CompletedProcess(command, 0, "", "")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    files = tuple(tmp_path / f"f{i}.ts" for i in range(2500))

    assert run_sg(files, rules) == ()
    assert sizes == [1000, 1000, 500]


def test_batches_merge_sorted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Hits from several batches come back sorted as if from one run."""
    files = tuple(tmp_path / f"f{i:04}.ts" for i in range(1500))

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        last = Path(command[-1])
        return subprocess.CompletedProcess(command, 0, _hit_line(last, 3) + "\n", "")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    hits = run_sg(tuple(reversed(files)), rules)

    assert [hit.file.name for hit in hits] == sorted(hit.file.name for hit in hits)
    assert len(hits) == 2


def test_run_sg_strict_raises_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Strict mode raises where `run_sg` swallows."""

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 8, "", "Error: bad rule\nmore")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    with pytest.raises(AstGrepError):
        run_sg_strict((tmp_path / "a.ts",), rules)


def test_run_sg_strict_names_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The error names the exit code and the first stderr line."""

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 8, "", "Error: bad rule\nmore")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    with pytest.raises(AstGrepError, match=r"exit code 8: Error: bad rule"):
        run_sg_strict((tmp_path / "a.ts",), rules)


def test_run_sg_strict_raises_on_unparseable_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A stream line that does not parse is an error in strict mode."""

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "not json\n", "")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    with pytest.raises(AstGrepError, match="could not be parsed"):
        run_sg_strict((tmp_path / "a.ts",), rules)


def test_run_sg_still_never_raises(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The non-strict runner keeps its contract."""

    def fake_run(command: tuple[str, ...], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 8, "", "Error: bad rule")

    rules = _setup(monkeypatch, tmp_path, fake_run)
    assert run_sg((tmp_path / "a.ts",), rules) == ()
