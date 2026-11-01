"""`scb-check delta` end to end, on real git repositories with real ast-grep."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from scb_check.analysis.astgrep import AstGrepError
from scb_check.cli import main

if TYPE_CHECKING:
    import pytest
runner = CliRunner()
_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}
GOOD = "export function a(x: number) {\n  const y = x + 1;\n  return y * 2;\n}\n"
BAD = "export function b(x: unknown) {\n  const y = x as any;\n  return y.length;\n}\n"
BAD_LINE = 2
OTHER = "export function c(x: number) {\n  const z = x - 1;\n  return z * 3;\n}\n"
CLONE = (
    "export function pairUp(a: number, b: number): number {\n"
    "  const sum = a + b;\n  const diff = a - b;\n  return sum * diff;\n}\n"
)
CLONE2 = CLONE.replace("pairUp", "pairDown")
UNPARSABLE = "export type * from './x';\nfunction (((\n"
COMMENT_ONLY = "// nothing here\n"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo), *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
        env=_ENV,
    )
    return done.stdout.strip()


def _commit(repo: Path, files: dict[str, str | None]) -> str:
    for rel, text in files.items():
        path = repo / rel
        if text is None:
            path.unlink()
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "c")
    return _git(repo, "rev-parse", "HEAD")


def _repo(tmp_path: Path, files: dict[str, str | None]) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    base = _commit(repo, {"README.md": "r\n", **files})
    _git(repo, "branch", "base")
    return repo, base


def _delta(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    expect: int = 0,
    fmt: bool = True,
) -> tuple[dict, str]:
    monkeypatch.chdir(repo)
    extra = ["--format", "json"] if fmt else []
    result = runner.invoke(main, ["delta", "--base", "base", *extra, *args])
    assert result.exit_code == expect, (result.stdout, result.stderr)
    return (json.loads(result.stdout) if fmt and expect == 0 else {}), result.stderr


def test_delta_relative_exclude_applies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A repo-relative --exclude holds when the temp directory is under a symlink."""
    link = tmp_path / "linked-tmp"
    real = tmp_path / "real-tmp"
    real.mkdir()
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("TMPDIR", str(link))
    monkeypatch.setattr(tempfile, "tempdir", None)
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/vendor/b.ts": BAD})
    payload, _err = _delta(repo, monkeypatch, "--exclude", "lib/vendor/**", "lib")
    assert payload["new_flagged"] == []


def test_delta_dirty_tree_scores_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uncommitted edits are warned about and not scored."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})
    (repo / "lib" / "a.ts").write_text(BAD)
    payload, err = _delta(repo, monkeypatch, "lib")
    assert "uncommitted" in err
    assert payload["meta"]["dirty"] is True
    assert payload["new_flagged"] == []
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert "Uncommitted changes in the working tree were not scored" in result.stdout


def test_delta_ignores_untracked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An untracked file is never exported or scored."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})
    (repo / "lib" / "new.ts").write_text(BAD)
    payload, err = _delta(repo, monkeypatch, "lib")
    assert payload["head"]["sloc"] == payload["base"]["sloc"] + 3
    assert payload["new_flagged"] == []
    assert "uncommitted" not in err


def test_delta_missing_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing base names its own branch; an expression falls back to origin/HEAD's."""
    repo, sha = _repo(tmp_path, {"lib/a.ts": GOOD})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "nope"])
    assert result.exit_code == 3
    assert "base ref nope not found; try git fetch origin nope" in result.stderr
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    result = runner.invoke(main, ["delta", "--base", "origin/feature-x"])
    assert "try git fetch origin feature-x" in result.stderr
    assert "origin main" not in result.stderr
    result = runner.invoke(main, ["delta", "--base", "nope~1"])
    assert "try git fetch origin main" in result.stderr


def test_delta_missing_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing head fails the same way."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "--head", "nope"])
    assert result.exit_code == 3
    assert "head ref nope not found; try git fetch origin nope" in result.stderr


def test_delta_rejects_option_like_ref(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ref that looks like an option never reaches git."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base=--output=x"])
    assert result.exit_code == 2
    assert not (repo / "x").exists()


def test_delta_shallow_with_merge_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shallow clone that still holds the merge base proceeds with a warning."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})
    shallow = tmp_path / "shallow"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", "--depth", "2", f"file://{repo}", str(shallow)],  # noqa: S607
        check=True,
        env=_ENV,
    )
    monkeypatch.chdir(shallow)
    result = runner.invoke(main, ["delta", "--base", "HEAD~1", "--format", "json"])
    assert result.exit_code == 0, result.stderr
    assert "shallow" in result.stderr


def test_delta_shallow_no_merge_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A shallow clone without the merge base is told to unshallow."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, {"lib/b.ts": OTHER})
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"lib/c.ts": OTHER})
    shallow = tmp_path / "shallow"
    subprocess.run(  # noqa: S603
        ["git", "clone", "-q", "--depth", "1", "--no-single-branch", f"file://{repo}", str(shallow)],  # noqa: S607
        check=True,
        env=_ENV,
    )
    monkeypatch.chdir(shallow)
    result = runner.invoke(
        main,
        ["delta", "--base", "origin/main", "--head", "origin/feature"],
    )
    assert result.exit_code == 3
    assert "no merge base; run git fetch --unshallow" in result.stderr


def test_delta_unrelated_histories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Histories with nothing in common fail without the shallow hint."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _git(repo, "checkout", "-q", "--orphan", "other")
    _commit(repo, {"lib/z.ts": OTHER})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "main", "--head", "other"])
    assert result.exit_code == 3
    assert "no merge base" in result.stderr
    assert "unshallow" not in result.stderr


def test_delta_not_a_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A directory outside git is a usage error."""
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    result = runner.invoke(main, ["delta", "--repo", str(plain)])
    assert result.exit_code == 2
    assert "not a git repository" in result.stderr


def test_delta_deleted_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Flagged lines of a deleted file count as cleared."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/bad.ts": BAD})
    _commit(repo, {"lib/bad.ts": None})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["cleared"] == 1
    assert payload["new_flagged"] == []
    assert payload["head"]["sloc"] == payload["base"]["sloc"] - 3


def test_delta_rename_no_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A pure rename adds, clears and newly flags nothing."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/bad.ts": BAD})
    _git(repo, "mv", "lib/bad.ts", "lib/moved.ts")
    _commit(repo, {})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["new_flagged"] == []
    assert payload["newly_flagged_existing"] == []
    assert payload["cleared"] == 0
    assert payload["delta"]["flagged_sloc"] == 0


def test_delta_rename_with_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """After a rename only the edited line can be new."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/bad.ts": BAD})
    _git(repo, "mv", "lib/bad.ts", "lib/moved.ts")
    edited = BAD.replace("  return y.length;", "  const w = y as any;\n  return w.length;")
    _commit(repo, {"lib/moved.ts": edited})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert [(i["path"], i["line"]) for i in payload["new_flagged"]] == [("lib/moved.ts", 3)]
    assert payload["newly_flagged_existing"] == []
    assert payload["cleared"] == 0


def test_delta_new_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every flagged line of a new file is new."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert [(i["path"], i["line"], i["signals"]) for i in payload["new_flagged"]] == [
        ("lib/bad.ts", BAD_LINE, ["ts-as-any"]),
    ]


def test_delta_clone_partner_flags_old_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding a copy elsewhere flags the untouched original as newly flagged."""
    repo, _ = _repo(tmp_path, {"lib/orig.ts": CLONE})
    _commit(repo, {"lib/copy.ts": CLONE2})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["base"]["flagged_sloc"] == 0
    old = {i["path"] for i in payload["newly_flagged_existing"]}
    new = {i["path"] for i in payload["new_flagged"]}
    assert old == {"lib/orig.ts"}
    assert new == {"lib/copy.ts"}


def test_delta_path_on_one_side(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A path present only at head is empty at base."""
    repo, _ = _repo(tmp_path, {"app/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    payload, _ = _delta(repo, monkeypatch, "app", "lib")
    assert payload["new_flagged"][0]["path"] == "lib/bad.ts"


def test_delta_path_on_neither_side(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path that exists nowhere is named in the error."""
    repo, _ = _repo(tmp_path, {"app/a.ts": GOOD})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "app", "nowhere"])
    assert result.exit_code == 2
    assert "nowhere" in result.stderr


def test_delta_path_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Parent and outside absolute paths are refused."""
    repo, _ = _repo(tmp_path, {"app/a.ts": GOOD})
    monkeypatch.chdir(repo)
    for bad in ("../elsewhere", "app/../../x", str(tmp_path)):
        result = runner.invoke(main, ["delta", "--base", "base", bad])
        assert result.exit_code == 2, bad


def test_delta_next_route_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Route-style paths with brackets and parentheses are scored."""
    route = "app/(shop)/[sku]/page.tsx"
    repo, _ = _repo(tmp_path, {"app/a.ts": GOOD})
    page = BAD.replace("export function b", "export default function Page")
    _commit(repo, {route: page})
    payload, _ = _delta(repo, monkeypatch, "app")
    assert [i["path"] for i in payload["new_flagged"]] == [route]


def test_delta_zero_sloc_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no source at base the base and delta cells read n/a."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": COMMENT_ONLY})
    _commit(repo, {"lib/a.ts": GOOD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["base"] is None
    assert payload["delta"] is None
    assert payload["head"]["sloc"] == 3
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert "| SLOC | n/a | 3 | n/a |" in result.stdout


def test_delta_zero_sloc_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No source on either side says so instead of printing zeros."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": COMMENT_ONLY})
    _commit(repo, {"lib/a.ts": "// still nothing\n"})
    _delta(repo, monkeypatch, "lib")
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert "no scanned source on either side" in result.stdout


def test_delta_zero_sloc_head(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """With no source at head the head cells read n/a and flags clear."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": BAD})
    _commit(repo, {"lib/a.ts": COMMENT_ONLY})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["head"] is None
    assert payload["cleared"] == 1


def test_delta_no_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A change outside the scan leaves every delta at zero."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": BAD})
    _commit(repo, {"README.md": "changed\n"})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert set(payload["delta"].values()) == {0}
    assert payload["new_flagged"] == payload["newly_flagged_existing"] == []
    assert payload["cleared"] == 0


def test_delta_sg_failure_is_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing ast-grep prints no numbers and exits 4."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AstGrepError("exit 8: bad rule")

    monkeypatch.setattr("scb_check.pipeline.run_sg_strict", boom)
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert result.exit_code == 4
    assert "ast-grep" in result.stderr
    assert result.stdout == ""


def test_delta_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Running past --max-seconds exits 5 and removes the temp dirs."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    def slow(*_args: object, **_kwargs: object) -> None:
        time.sleep(10)

    monkeypatch.setattr("scb_check.commands.delta.analyze_paths", slow)
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "--max-seconds", "1", "lib"])
    assert result.exit_code == 5
    assert "timed out after 1 s while scoring base" in result.stderr
    assert list(scratch.iterdir()) == []


def test_delta_interrupt_cleans_up(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ctrl-C exits 130 and removes the temp dirs."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": OTHER})
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    def interrupt(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("scb_check.commands.delta.analyze_paths", interrupt)
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert result.exit_code == 130
    assert list(scratch.iterdir()) == []


def test_delta_asymmetric_skip_incomparable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file parsed at base and skipped at head makes the numbers incomparable."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/b.ts": OTHER})
    _commit(repo, {"lib/b.ts": UNPARSABLE})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["comparable"] is False
    assert payload["delta"] is None
    assert payload["new_flagged"] is None
    assert "lib/b.ts" in payload["incomparable"][0]
    assert payload["base"]["sloc"] == 6
    result = runner.invoke(main, ["delta", "--base", "base", "lib"])
    assert "| SLOC | 6 | 3 | incomparable |" in result.stdout
    assert "Incomparable" in result.stdout


def test_delta_new_unparsable_file_incomparable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A new file that cannot be parsed makes the numbers incomparable."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/new.ts": UNPARSABLE})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["comparable"] is False
    assert "lib/new.ts" in payload["incomparable"][0]


def test_delta_skip_both_sides_comparable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A file skipped on both sides is counted and the delta still compares."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/bad.ts": UNPARSABLE})
    _commit(repo, {"lib/bad.ts": UNPARSABLE + "// edited\n", "lib/c.ts": BAD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["comparable"] is True
    assert payload["skipped_files"] == {"base": ["lib/bad.ts"], "head": ["lib/bad.ts"]}
    assert len(payload["new_flagged"]) == 1


def _tree_state(repo: Path) -> dict[str, str]:
    state = {
        "index": hashlib.sha256((repo / ".git" / "index").read_bytes()).hexdigest(),
        "head": _git(repo, "rev-parse", "HEAD"),
        "status": _git(repo, "status", "--porcelain=v1"),
        "worktrees": _git(repo, "worktree", "list"),
        "stash": _git(repo, "stash", "list"),
        "refs": _git(repo, "for-each-ref"),
    }
    for path in sorted(repo.rglob("*")):
        if path.is_file() and ".git" not in path.relative_to(repo).parts:
            state[f"file:{path.relative_to(repo)}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return state


def test_delta_never_touches_working_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dirty tree with an untracked file is left byte for byte as it was."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/b.ts": BAD})
    (repo / "lib" / "a.ts").write_text(BAD)
    (repo / "lib" / "untracked.ts").write_text(OTHER)
    before = _tree_state(repo)
    assert before["status"]
    assert before["stash"] == ""
    _delta(repo, monkeypatch, "lib")
    _delta(repo, monkeypatch)
    assert _tree_state(repo) == before
    assert "refs/stash" not in before["refs"]


def test_delta_merge_base_not_tip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Base moving on after branching does not change the numbers."""
    repo, base_sha = _repo(tmp_path, {"lib/a.ts": GOOD})
    _git(repo, "checkout", "-q", "-b", "feature")
    _commit(repo, {"lib/bad.ts": BAD})
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"lib/other.ts": OTHER + OTHER.replace("c(", "d(")})
    monkeypatch.chdir(repo)
    args = ["delta", "--format", "json", "--head", "feature", "lib"]
    moved = json.loads(runner.invoke(main, [*args[:1], "--base", "main", *args[1:]]).stdout)
    at_fork = json.loads(runner.invoke(main, [*args[:1], "--base", base_sha, *args[1:]]).stdout)
    for payload in (moved, at_fork):
        payload["meta"].pop("base_ref")
    assert moved == at_fork
    assert moved["new_flagged"][0]["path"] == "lib/bad.ts"


def test_delta_json_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--format json prints one JSON document with the documented keys."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["meta"]["profile"] == "ts"
    assert payload["meta"]["clone_loc_below_target_precision"] is True
    assert payload["changed_functions"][0][:2] == ["lib/bad.ts", "bad.b"]
    assert payload["head"]["flagged_sloc"] == 1


def test_delta_max_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--max-lines caps the listing."""
    many = "export function m(x: unknown) {\n" + "".join(
        f"  const v{n} = x as any;\n" for n in range(4)
    ) + "  return x;\n}\n"
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/many.ts": many})
    monkeypatch.chdir(repo)
    result = runner.invoke(main, ["delta", "--base", "base", "--max-lines", "1", "lib"])
    assert result.stdout.count("- `lib/many.ts:") == 1
    assert "- ... and 3 more" in result.stdout
    assert "clone_loc (below target precision)" in result.stdout


def test_delta_default_base_is_origin_dev(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without --base the comparison is against origin/dev."""
    repo, base_sha = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    monkeypatch.chdir(repo)
    missing = runner.invoke(main, ["delta", "lib"])
    assert missing.exit_code == 3
    assert "base ref origin/dev not found" in missing.stderr
    _git(repo, "update-ref", "refs/remotes/origin/dev", base_sha)
    ok = runner.invoke(main, ["delta", "--format", "json", "lib"])
    assert ok.exit_code == 0, ok.stderr
    assert json.loads(ok.stdout)["meta"]["base_ref"] == "origin/dev"


def test_delta_exit_0_when_worse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A change that makes the scores worse still exits 0: never a gate."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["delta"]["verbosity"] > 0


def test_delta_honours_ancestor_gitignore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A root .gitignore rule applies when only a sub-path is scanned."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, ".gitignore": "lib/auto/\n"})
    (repo / "lib" / "auto").mkdir()
    (repo / "lib" / "auto" / "bad.ts").write_text(BAD)
    _git(repo, "add", "-f", "lib/auto/bad.ts")
    _commit(repo, {"lib/b.ts": OTHER})
    partial, _ = _delta(repo, monkeypatch, "lib")
    whole, _ = _delta(repo, monkeypatch)
    assert partial["new_flagged"] == []
    assert partial["head"]["flagged_sloc"] == whole["head"]["flagged_sloc"] == 0


def test_delta_working_tree_symlink_cannot_redirect_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dirty symlink in place of a scanned directory changes nothing."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "else/x.ts": OTHER})
    _commit(repo, {"lib/bad.ts": BAD})
    clean, _ = _delta(repo, monkeypatch, "lib")
    for child in (repo / "lib").iterdir():
        child.unlink()
    (repo / "lib").rmdir()
    (repo / "lib").symlink_to(repo / "else")
    dirty, _ = _delta(repo, monkeypatch, "lib")
    clean["meta"].pop("dirty")
    dirty["meta"].pop("dirty")
    assert dirty["head"] == clean["head"]
    assert dirty["new_flagged"] == clean["new_flagged"]


def test_delta_export_ignore_attribute_does_not_hide_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adding an export-ignore rule alone leaves every score unchanged."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD, "lib/private.ts": BAD})
    _commit(repo, {".gitattributes": "lib/private.ts export-ignore\n"})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["delta"]["flagged_sloc"] == 0
    assert payload["delta"]["sloc"] == 0
    assert payload["cleared"] == 0


def test_delta_scores_upper_case_extensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A supported source with an upper-case suffix is exported and diffed."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/NEW.TS": GOOD})
    payload, _ = _delta(repo, monkeypatch, "lib")
    assert payload["delta"]["sloc"] == 3
    assert [fn[0] for fn in payload["changed_functions"]] == ["lib/NEW.TS"]


def test_delta_absolute_path_through_symlinked_location(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An absolute path reached through a symlink above the repo still works."""
    repo, _ = _repo(tmp_path, {"lib/a.ts": GOOD})
    _commit(repo, {"lib/bad.ts": BAD})
    alias = tmp_path / "alias"
    alias.symlink_to(repo)
    relative, _ = _delta(repo, monkeypatch, "lib")
    through_alias, _ = _delta(repo, monkeypatch, str(alias / "lib"))
    assert through_alias["new_flagged"] == relative["new_flagged"]
