"""Git helpers behind `scb-check delta`, against real repositories."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scb_check.commands import delta_git
from scb_check.commands.delta_git import ChangedFile
from scb_check.commands.delta_git import LineMap

_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


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


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    return repo


def test_line_map_to_old(tmp_path: Path) -> None:
    """Unchanged lines map back through insertions and deletions."""
    repo = _repo(tmp_path)
    old = _commit(repo, {"a.ts": "".join(f"l{n}\n" for n in range(1, 9))})
    body = "l1\nNEW\nl2\nl3\nl6\nl7\nl8\n"  # insert after l1, drop l4 and l5
    new = _commit(repo, {"a.ts": body})
    lmap = delta_git.line_map(repo, old, new, ChangedFile("M", None, "a.ts"))
    assert lmap.added == frozenset({2})
    assert lmap.deleted == frozenset({4, 5})
    assert lmap.to_old(2) is None
    assert [lmap.to_old(n) for n in (1, 3, 4, 5, 6, 7)] == [1, 2, 3, 6, 7, 8]


def test_line_map_zero_context_hunks() -> None:
    """Counts default to one and zero-length hunks parse from headers alone."""
    patch = (
        "diff --git a/f.ts b/f.ts\n--- a/f.ts\n+++ b/f.ts\n"
        "@@ -3 +3 @@\n-x\n+y\n"
        "@@ -7,2 +6,0 @@\n-a\n-b\n"
        "@@ -10,0 +9,3 @@\n+p\n+q\n+r\n"
    )
    lmap = delta_git._parse_line_map(patch, wants_new=True)  # noqa: SLF001
    assert lmap.hunks == ((3, 1, 3, 1), (7, 2, 6, 0), (10, 0, 9, 3))
    assert lmap.added == frozenset({3, 9, 10, 11})
    assert lmap.deleted == frozenset({3, 7, 8})
    assert lmap.to_old(4) == 4
    assert lmap.to_old(7) == 9
    assert LineMap(frozenset(), frozenset(), ()).to_old(5) == 5


def test_changed_files_rename_status(tmp_path: Path) -> None:
    """A moved, lightly edited file is a rename; add and delete are typed."""
    repo = _repo(tmp_path)
    text = "".join(f"line {n}\n" for n in range(10))
    old = _commit(repo, {"a.ts": text, "gone.ts": "x\n"})
    _git(repo, "mv", "a.ts", "b.ts")
    new = _commit(repo, {"b.ts": text + "extra\n", "gone.ts": None, "fresh.ts": "y\n"})
    got = {c.status: c for c in delta_git.changed_files(repo, old, new, (".",))}
    assert got["R"] == ChangedFile("R", "a.ts", "b.ts")
    assert got["D"] == ChangedFile("D", "gone.ts", None)
    assert got["A"] == ChangedFile("A", None, "fresh.ts")


def test_changed_files_z_paths_with_spaces(tmp_path: Path) -> None:
    """Paths with spaces and brackets survive the NUL-separated listing."""
    repo = _repo(tmp_path)
    old = _commit(repo, {"keep.ts": "k\n"})
    new = _commit(repo, {"app/(group)/[id]/my page.tsx": "z\n"})
    got = delta_git.changed_files(repo, old, new, ("app",))
    assert got == (ChangedFile("A", None, "app/(group)/[id]/my page.tsx"),)


def test_export_tree_supported_suffixes_only(tmp_path: Path) -> None:
    """Only supported sources and .gitignore files are written."""
    repo = _repo(tmp_path)
    sha = _commit(
        repo,
        {
            "app/a.ts": "a\n",
            "app/b.tsx": "b\n",
            "app/c.md": "c\n",
            "app/d.png": "d\n",
            "app/.gitignore": "x\n",
        },
    )
    dest = tmp_path / "out"
    delta_git.export_tree(repo, sha, ("app",), dest)
    got = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert got == ["app/.gitignore", "app/a.ts", "app/b.tsx"]


def test_export_ignores_export_ignore_and_keeps_upper_case(tmp_path: Path) -> None:
    """`export-ignore` cannot hide source, and upper-case suffixes are exported."""
    repo = _repo(tmp_path)
    sha = _commit(
        repo,
        {
            ".gitattributes": "lib/private.ts export-ignore\n",
            "lib/private.ts": "p\n",
            "lib/HOT.CPP": "int f() { return 1; }\n",
        },
    )
    dest = tmp_path / "out"
    delta_git.export_tree(repo, sha, ("lib",), dest)
    got = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file())
    assert got == ["lib/HOT.CPP", "lib/private.ts"]
    assert delta_git.is_supported_name("a/B.TSX")


def test_export_skips_unsafe_members(tmp_path: Path) -> None:
    """A symlink escaping the export is refused and the rest still lands."""
    repo = _repo(tmp_path)
    (repo / "app").mkdir()
    (repo / "app" / "evil.ts").symlink_to("/etc/passwd")
    (repo / "app" / "up.ts").symlink_to("../../outside.ts")
    sha = _commit(repo, {"app/good.ts": "g\n"})
    dest = tmp_path / "out"
    delta_git.export_tree(repo, sha, ("app",), dest)
    assert (dest / "app" / "good.ts").is_file()
    assert not (dest / "app" / "evil.ts").exists()
    assert not (dest / "app" / "up.ts").exists()


def test_every_git_call_has_no_optional_locks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every git invocation is read-only, lock-free and literal-pathspec."""
    repo = _repo(tmp_path)
    old = _commit(repo, {"app/a.ts": "a\nb\n"})
    new = _commit(repo, {"app/a.ts": "a\nc\n"})
    seen: list[list[str]] = []
    real_run, real_popen = subprocess.run, subprocess.Popen

    def run(argv: list[str], **kwargs: Any) -> Any:  # noqa: ANN401
        seen.append(argv)
        return real_run(argv, **kwargs)

    def popen(argv: list[str], **kwargs: Any) -> Any:  # noqa: ANN401
        seen.append(argv)
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(subprocess, "Popen", popen)
    delta_git.repo_root(repo)
    delta_git.resolve_commit(repo, new)
    delta_git.merge_base(repo, old, new)
    delta_git.is_shallow(repo)
    delta_git.is_dirty(repo)
    delta_git.path_exists(repo, new, "app")
    delta_git.default_branch(repo)
    delta_git.export_tree(repo, new, ("app",), tmp_path / "out")
    changes = delta_git.changed_files(repo, old, new, ("app",))
    delta_git.line_map(repo, old, new, changes[0])
    delta_git.tool_sha(Path(__file__).resolve().parents[2])
    assert len(seen) >= 10
    allowed = {"rev-parse", "merge-base", "status", "cat-file", "symbolic-ref", "ls-tree", "diff", "remote"}
    for argv in seen:
        assert argv[:3] == ["git", "--no-optional-locks", "--literal-pathspecs"]
        verb = argv[argv.index("-C") + 2]
        assert verb in allowed


def test_line_map_ignores_inter_hunk_context_setting(tmp_path: Path) -> None:
    """A repository diff.interHunkContext setting cannot merge hunks."""
    repo = _repo(tmp_path)
    _git(repo, "config", "diff.interHunkContext", "5")
    old = _commit(repo, {"a.ts": "".join(f"l{n}\n" for n in range(1, 9))})
    lines = [f"l{n}\n" for n in range(1, 9)]
    lines[1], lines[5] = "X\n", "Y\n"
    new = _commit(repo, {"a.ts": "".join(lines)})
    lmap = delta_git.line_map(repo, old, new, ChangedFile("M", None, "a.ts"))
    assert lmap.added == frozenset({2, 6})
    assert lmap.to_old(3) == 3


def test_line_map_ignores_binary_attribute(tmp_path: Path) -> None:
    """A .gitattributes binary rule does not hide the hunks of scored sources."""
    repo = _repo(tmp_path)
    old = _commit(repo, {".gitattributes": "*.ts binary\n", "a.ts": "a\nb\n"})
    new = _commit(repo, {"a.ts": "a\nc\n", "n.ts": "x\ny\n"})
    modified = delta_git.line_map(repo, old, new, ChangedFile("M", None, "a.ts"))
    added = delta_git.line_map(repo, old, new, ChangedFile("A", None, "n.ts"))
    assert modified.added == frozenset({2})
    assert added.added == frozenset({1, 2})


def test_every_git_call_disables_lazy_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every git call runs with GIT_NO_LAZY_FETCH=1, so a partial clone never fetches."""
    repo = _repo(tmp_path)
    old = _commit(repo, {"app/a.ts": "a\nb\n"})
    new = _commit(repo, {"app/a.ts": "a\nc\n"})
    monkeypatch.delenv("GIT_NO_LAZY_FETCH", raising=False)
    envs: list[dict[str, str]] = []
    real_run = subprocess.run

    def run(argv: list[str], **kwargs: Any) -> Any:  # noqa: ANN401
        envs.append(kwargs.get("env") or {})
        return real_run(argv, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)
    delta_git.repo_root(repo)
    delta_git.resolve_commit(repo, new)
    delta_git.merge_base(repo, old, new)
    delta_git.export_tree(repo, new, ("app",), tmp_path / "out")
    changes = delta_git.changed_files(repo, old, new, ("app",))
    delta_git.line_map(repo, old, new, changes[0])
    assert len(envs) >= 6
    assert all(env.get("GIT_NO_LAZY_FETCH") == "1" for env in envs)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("feature", "git fetch origin feature"),
        ("origin/feature/x", "git fetch origin feature/x"),
        ("refs/remotes/origin/feature", "git fetch origin feature"),
        ("upstream/feature/x", "git fetch upstream feature/x"),
        ("refs/remotes/upstream/x", "git fetch upstream x"),
        ("refs/heads/upstream/topic", "git fetch origin upstream/topic"),
        ("feat+one", "git fetch origin feat+one"),
        ("abc1234", "git fetch origin main"),
        ("abc1234~1", "git fetch origin main"),
        ("HEAD", "git fetch origin main"),
    ],
)
def test_fetch_hint_names_the_refs_own_branch(
    tmp_path: Path, ref: str, expected: str
) -> None:
    """The hint names the missing ref's branch; only non-branch refs use origin/HEAD."""
    repo = _repo(tmp_path)
    sha = _commit(repo, {"app/a.ts": "a\n"})
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    _git(repo, "remote", "add", "upstream", "https://example.invalid/x.git")
    assert delta_git._fetch_hint(repo, ref) == expected  # noqa: SLF001
