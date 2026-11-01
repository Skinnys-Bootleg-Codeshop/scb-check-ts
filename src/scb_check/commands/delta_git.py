"""Read-only git access for `scb-check delta`.

This is the only module that shells out to git. Every call passes
`--no-optional-locks` and `--literal-pathspecs`, uses no shell, and puts refs
after `--end-of-options`. Only `rev-parse`, `merge-base`, `status`,
`cat-file`, `symbolic-ref`, `ls-tree`, `remote` (listing only) and `diff`
are ever run.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath

from scb_check.logging import get_logger
from scb_check.tree_walking.dispatch import SUPPORTED_SOURCE_SUFFIXES

_LOGGER = get_logger(__name__)
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_ROOT = "."
_BATCH = 500
_BRANCH_NAME = re.compile(r"^[A-Za-z0-9._+][A-Za-z0-9._+/-]*$")
_HEX_SHA = re.compile(r"^[0-9a-f]{7,40}$")


class GitStateError(Exception):  # scbc ignore[empty-exception-subclass]
    """Raised when the repository state cannot support a delta (exit 3)."""


class UsageError(ValueError):  # scbc ignore[empty-exception-subclass]
    """Raised when the command line or repository path is wrong (exit 2)."""


@dataclass(frozen=True, slots=True)
class ChangedFile:
    """One changed file between two commits."""

    status: str
    old_path: str | None
    new_path: str | None


@dataclass(frozen=True, slots=True)
class LineMap:
    """Line correspondence between the old and new side of one file."""

    added: frozenset[int]
    deleted: frozenset[int]
    hunks: tuple[tuple[int, int, int, int], ...]

    def to_old(self, new_line: int) -> int | None:
        """Return the old line number for `new_line`, or None when added."""
        if new_line in self.added:
            return None
        offset = 0
        for old_count, new_start, new_count in (
            (h[1], h[2], h[3]) for h in self.hunks
        ):
            last_new = new_start + new_count - 1 if new_count else new_start
            if last_new < new_line:
                offset += old_count - new_count
        return new_line + offset


def _git_env() -> dict[str, str]:
    """Return the environment for git: never fetch missing objects lazily."""
    return {**os.environ, "GIT_NO_LAZY_FETCH": "1"}


def _git_argv(repo: Path, *args: str) -> list[str]:
    return [
        "git",
        "--no-optional-locks",
        "--literal-pathspecs",
        "-C",
        str(repo),
        *args,
    ]


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(  # noqa: S603
            _git_argv(repo, *args),
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            errors="replace",
            env=_git_env(),
        )
    except OSError as exc:
        raise UsageError(f"cannot run git: {exc}") from exc


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0] if lines else ""


def repo_root(repo: Path) -> Path:
    """Return the top-level directory of the repository at `repo`."""
    if not repo.is_dir():
        raise UsageError(f"not a git repository: {repo}")
    done = _run(repo, "rev-parse", "--show-toplevel")
    if done.returncode != 0:
        raise UsageError(f"not a git repository: {repo}")
    return Path(done.stdout.strip())


def _reject_option_like(ref: str) -> None:
    if ref.startswith("-"):
        raise UsageError(f"refs must not start with '-': {ref}")


def default_branch(repo: Path) -> str | None:
    """Return the branch `origin/HEAD` points at, when resolvable."""
    done = _run(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if done.returncode != 0:
        return None
    return done.stdout.strip().removeprefix("origin/") or None


def _remotes(repo: Path) -> list[str]:
    done = _run(repo, "remote")
    return done.stdout.split() if done.returncode == 0 else []


def _fetch_hint(repo: Path, ref: str) -> str:
    """Name the remote and branch of the missing ref itself.

    `origin/feature`, `upstream/feature/x` and `refs/remotes/upstream/x` name
    their own remote and branch; a bare `feature` is taken to be an `origin`
    branch. A commit id or an expression such as `abc123~1` names no branch,
    so those fall back to origin/HEAD's branch when resolvable.
    """
    remote = "origin"
    if ref.startswith("refs/heads/"):
        name = ref.removeprefix("refs/heads/")
    else:
        name = ref.removeprefix("refs/remotes/")
        for candidate in dict.fromkeys([*_remotes(repo), "origin"]):
            if name.startswith(f"{candidate}/"):
                remote = candidate
                name = name.removeprefix(f"{candidate}/")
                break
    if (
        _BRANCH_NAME.match(name)
        and not _HEX_SHA.match(name)
        and ".." not in name
        and name != "HEAD"
    ):
        return f"git fetch {remote} {name}"
    branch = default_branch(repo)
    return f"git fetch origin {branch}" if branch else "git fetch origin"


def resolve_commit(repo: Path, ref: str, *, role: str = "ref") -> str:
    """Resolve `ref` to a full commit SHA without touching the repository."""
    _reject_option_like(ref)
    done = _run(
        repo,
        "rev-parse",
        "--verify",
        "--quiet",
        "--end-of-options",
        f"{ref}^{{commit}}",
    )
    if done.returncode != 0:
        raise GitStateError(
            f"{role} ref {ref} not found; try {_fetch_hint(repo, ref)}"
        )
    return done.stdout.strip()


def is_shallow(repo: Path) -> bool:
    """Return whether the repository is a shallow clone."""
    done = _run(repo, "rev-parse", "--is-shallow-repository")
    return done.stdout.strip() == "true"


def merge_base(repo: Path, base: str, head: str) -> str:
    """Return the merge base of `base` and `head`."""
    done = _run(repo, "merge-base", "--end-of-options", base, head)
    sha = done.stdout.strip()
    if done.returncode == 0 and sha:
        return sha
    if is_shallow(repo):
        raise GitStateError("no merge base; run git fetch --unshallow")
    raise GitStateError("no merge base: base and head share no history")


def is_dirty(repo: Path) -> bool:
    """Return whether tracked files have uncommitted changes."""
    done = _run(repo, "status", "--porcelain", "--untracked-files=no")
    return bool(done.stdout.strip())


def path_exists(repo: Path, sha: str, path: str) -> bool:
    """Return whether `path` exists in commit `sha`."""
    if path in {"", _ROOT}:
        return True
    return _run(repo, "cat-file", "-e", f"{sha}:{path}").returncode == 0


def _pathspecs(paths: tuple[str, ...]) -> list[str]:
    return [] if paths == (_ROOT,) else list(paths)


def is_supported_name(name: str) -> bool:
    """Return whether the analyzer would scan a file called `name`."""
    pure = PurePosixPath(name)
    return pure.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES or pure.name == ".gitignore"


def _blob_entries(
    repo: Path,
    sha: str,
    paths: tuple[str, ...],
) -> list[tuple[str, str]]:
    """List `(blob sha, path)` of regular files the analyzer could scan."""
    done = _run(
        repo,
        "ls-tree",
        "-r",
        "-z",
        "--full-tree",
        "--end-of-options",
        sha,
        *_pathspecs(paths),
    )
    if done.returncode != 0:
        raise GitStateError(f"git ls-tree failed: {_first_line(done.stderr)}")
    entries: list[tuple[str, str]] = []
    for record in done.stdout.split("\0"):
        meta, _, name = record.partition("\t")
        fields = meta.split()
        if len(fields) != 3 or fields[1] != "blob":  # noqa: PLR2004
            continue
        if fields[0] not in {"100644", "100755"}:
            continue  # symlinks and submodules are never exported
        if is_supported_name(name):
            entries.append((fields[2], name))
    return entries


def export_tree(
    repo: Path,
    sha: str,
    paths: tuple[str, ...],
    dest: Path,
) -> None:
    """Write scannable files under `paths` at `sha` into `dest`.

    Reads blobs directly, so `.gitattributes` rules such as `export-ignore`
    cannot hide committed source that a direct scan would score.
    """
    dest.mkdir(parents=True, exist_ok=True)
    entries = _blob_entries(repo, sha, paths)
    root = dest.resolve()
    for start in range(0, len(entries), _BATCH):
        chunk = entries[start : start + _BATCH]
        try:
            done = subprocess.run(  # noqa: S603
                _git_argv(repo, "cat-file", "--batch"),
                input="".join(f"{blob}\n" for blob, _ in chunk).encode(),
                capture_output=True,
                check=False,
                env=_git_env(),
            )
        except OSError as exc:
            raise GitStateError(f"cannot run git: {exc}") from exc
        if done.returncode != 0:
            message = done.stderr.decode("utf-8", "replace")
            raise GitStateError(f"git cat-file failed: {_first_line(message)}")
        _write_blobs(done.stdout, [name for _, name in chunk], root)


def _write_blobs(output: bytes, names: list[str], root: Path) -> None:
    position = 0
    for name in names:
        newline = output.index(b"\n", position)
        header = output[position:newline].split()
        if len(header) != 3 or header[1] != b"blob":  # noqa: PLR2004
            raise GitStateError(f"git cat-file returned no blob for {name}")
        size = int(header[2])
        body = output[newline + 1 : newline + 1 + size]
        position = newline + 1 + size + 1
        target = (root / name).resolve()
        if root not in target.parents:
            _LOGGER.warning("skipping unsafe path %s", name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)


def changed_files(
    repo: Path,
    old: str,
    new: str,
    paths: tuple[str, ...],
) -> tuple[ChangedFile, ...]:
    """Return files changed between `old` and `new` under `paths`."""
    done = _run(
        repo,
        "diff",
        "-z",
        "--name-status",
        "--find-renames=50%",
        "--no-ext-diff",
        "--end-of-options",
        old,
        new,
        "--",
        *(paths or (_ROOT,)),
    )
    if done.returncode != 0:
        raise GitStateError(f"git diff failed: {_first_line(done.stderr)}")
    fields = done.stdout.split("\0")
    out: list[ChangedFile] = []
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index][0]
        if status in {"R", "C"}:
            out.append(ChangedFile(status, fields[index + 1], fields[index + 2]))
            index += 3
        elif status == "D":
            out.append(ChangedFile(status, fields[index + 1], None))
            index += 2
        else:
            out.append(ChangedFile(status, None, fields[index + 1]))
            index += 2
    return tuple(out)


def line_map(
    repo: Path,
    old: str,
    new: str,
    change: ChangedFile,
) -> LineMap:
    """Return the line correspondence for `change`, from `@@` headers only."""
    specs = tuple(p for p in (change.old_path, change.new_path) if p)
    done = _run(
        repo,
        "diff",
        "--unified=0",
        "--inter-hunk-context=0",
        "--text",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--find-renames=50%",
        "--end-of-options",
        old,
        new,
        "--",
        *specs,
    )
    if done.returncode != 0:
        raise GitStateError(f"git diff failed: {_first_line(done.stderr)}")
    return _parse_line_map(done.stdout, wants_new=change.new_path is not None)


def _parse_line_map(patch: str, *, wants_new: bool) -> LineMap:
    sections: list[tuple[bool, list[tuple[int, int, int, int]]]] = []
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            sections.append((False, []))
        elif sections and line.startswith("deleted file mode"):
            sections[-1] = (True, sections[-1][1])
        elif sections:
            match = _HUNK.match(line)
            if match:
                old_start, old_count, new_start, new_count = match.groups()
                sections[-1][1].append(
                    (
                        int(old_start),
                        1 if old_count is None else int(old_count),
                        int(new_start),
                        1 if new_count is None else int(new_count),
                    ),
                )
    hunks: list[tuple[int, int, int, int]] = []
    for deleted, section_hunks in sections:
        if wants_new and deleted:
            continue
        hunks.extend(section_hunks)
    added: set[int] = set()
    deleted_lines: set[int] = set()
    for old_start, old_count, new_start, new_count in hunks:
        added.update(range(new_start, new_start + new_count))
        deleted_lines.update(range(old_start, old_start + old_count))
    return LineMap(frozenset(added), frozenset(deleted_lines), tuple(hunks))


def tool_sha(tool_dir: Path) -> str:
    """Return the short SHA of the fork checkout at `tool_dir`, or `unknown`."""
    if not (tool_dir / ".git").exists():
        return "unknown"
    done = _run(tool_dir, "rev-parse", "--short", "HEAD")
    sha = done.stdout.strip()
    return sha if done.returncode == 0 and sha else "unknown"
