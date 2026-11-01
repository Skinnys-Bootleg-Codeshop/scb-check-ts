"""Implement the `scb-check delta` command: score a pull request against its base."""

from __future__ import annotations

import json
import os
import signal
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Annotated

import click
import typer
import yaml

from scb_check.analysis.astgrep import AstGrepError
from scb_check.commands import delta_git
from scb_check.commands.delta_git import ChangedFile
from scb_check.commands.delta_git import GitStateError
from scb_check.commands.delta_git import LineMap
from scb_check.commands.delta_git import UsageError
from scb_check.config import PROFILES
from scb_check.config import Config
from scb_check.config import ConfigError
from scb_check.logging import configure_logging
from scb_check.pipeline import IgnoreDirectiveError
from scb_check.pipeline import analyze_paths
from scb_check.reporting.delta import DeltaMeta
from scb_check.reporting.delta import ScanSnapshot
from scb_check.reporting.delta import compute_delta
from scb_check.reporting.delta import delta_to_dict
from scb_check.reporting.delta import empty_snapshot
from scb_check.reporting.delta import render_markdown
from scb_check.reporting.delta import snapshot_from_result
from scb_check.resources import RuleSet
from scb_check.resources import rule_texts

EXIT_USAGE = 2
EXIT_GIT = 3
EXIT_ANALYSIS = 4
EXIT_TIMEOUT = 5
EXIT_INTERRUPTED = 130


class DeltaTimeout(BaseException):
    """Raised by the alarm handler.

    Not a `TimeoutError`: that is an `OSError`, which the source reader and the
    ast-grep runner catch, so a timeout would turn into a silently skipped file.
    """


def delta(  # noqa: PLR0913
    paths: Annotated[list[Path] | None, typer.Argument()] = None,
    *,
    repo: Annotated[
        Path,
        typer.Option("--repo", help="Repository to score."),
    ] = Path(),
    base: Annotated[str, typer.Option("--base", help="Base ref.")] = "origin/dev",
    head: Annotated[str, typer.Option("--head", help="Head ref.")] = "HEAD",
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            click_type=click.Choice(tuple(PROFILES)),
            help="Scan profile: ts (default) or upstream.",
        ),
    ] = "ts",
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Extra exclude glob (repeatable)."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            click_type=click.Choice(("md", "json")),
            help="Output format: md (default) or json.",
        ),
    ] = "md",
    max_lines: Annotated[
        int,
        typer.Option("--max-lines", min=0, help="Cap on listed flagged lines."),
    ] = 50,
    max_seconds: Annotated[
        int,
        typer.Option("--max-seconds", min=1, help="Give up after N seconds."),
    ] = 900,
    verbosity: Annotated[
        int,
        typer.Option("-v", "--verbosity", count=True, help="Log detail."),
    ] = 0,
) -> None:
    """Report how a pull request moves the slop scores. Never a gate."""
    configure_logging(verbosity)
    try:
        _run(
            tuple(paths or ()),
            repo=repo,
            base=base,
            head=head,
            profile=profile,
            exclude=tuple(exclude or ()),
            output_format=output_format,
            max_lines=max_lines,
            max_seconds=max_seconds,
        )
    except UsageError as exc:
        _fail(str(exc), EXIT_USAGE, exc)
    except GitStateError as exc:
        _fail(str(exc), EXIT_GIT, exc)
    except DeltaTimeout as exc:
        stage = str(exc) or "starting up"
        _fail(f"timed out after {max_seconds} s while {stage}", EXIT_TIMEOUT, exc)
    except KeyboardInterrupt as exc:
        _fail("interrupted", EXIT_INTERRUPTED, exc)
    except AstGrepError as exc:
        _fail(f"ast-grep failed: {exc}", EXIT_ANALYSIS, exc)
    except (ConfigError, IgnoreDirectiveError, OSError, ValueError) as exc:
        _fail(f"analysis failed: {exc}", EXIT_ANALYSIS, exc)


def _fail(message: str, code: int, cause: BaseException) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=code) from cause


@contextmanager
def _alarm(seconds: int) -> Iterator[None]:
    def handler(_signum: int, _frame: FrameType | None) -> None:
        raise DeltaTimeout

    previous = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def _run(  # noqa: PLR0913
    paths: tuple[Path, ...],
    *,
    repo: Path,
    base: str,
    head: str,
    profile: str,
    exclude: tuple[str, ...],
    output_format: str,
    max_lines: int,
    max_seconds: int,
) -> None:
    root = delta_git.repo_root(repo).resolve()
    scan_paths = _scan_paths(paths, repo, root)
    head_sha = delta_git.resolve_commit(root, head, role="head")
    base_sha = delta_git.resolve_commit(root, base, role="base")
    notes: list[str] = []
    mb_sha = delta_git.merge_base(root, base_sha, head_sha)
    if delta_git.is_shallow(root):
        notes.append("Shallow clone: the merge base was found, but history is partial.")
        typer.echo("warning: shallow clone; history is partial", err=True)
    dirty = delta_git.is_dirty(root)
    if dirty:
        typer.echo(
            "warning: uncommitted changes are not scored; scoring the committed head",
            err=True,
        )
    base_paths = _existing(root, mb_sha, scan_paths)
    head_paths = _existing(root, head_sha, scan_paths)
    for path in scan_paths:
        if path not in base_paths and path not in head_paths:
            raise UsageError(f"path {path} exists on neither side")
    scan_profile = PROFILES[profile]
    stage = "scoring base"
    try:
        with _alarm(max_seconds):
            with tempfile.TemporaryDirectory(prefix="scb-delta-") as tmp:
                sides = Path(tmp)
                base_snap = _score_side(
                    root, mb_sha, base_paths, sides / "base", exclude, profile
                )
                stage = "scoring head"
                head_snap = _score_side(
                    root, head_sha, head_paths, sides / "head", exclude, profile
                )
            stage = "comparing changed lines"
            changes = _changes(root, mb_sha, head_sha, scan_paths)
            report = compute_delta(base_snap, head_snap, changes)
    except DeltaTimeout as exc:
        raise DeltaTimeout(stage) from exc
    meta = DeltaMeta(
        tool_sha=delta_git.tool_sha(Path(__file__).resolve().parents[3]),
        profile=profile,
        rule_count=_rule_count(profile),
        base_ref=base,
        base_sha=mb_sha,
        head_ref=head,
        head_sha=head_sha,
        paths=scan_paths,
        dirty=dirty,
        notes=tuple(notes),
        clone_row=scan_profile.name == "ts",
    )
    if output_format == "json":
        sys.stdout.write(json.dumps(delta_to_dict(report, meta), indent=1, sort_keys=True))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_markdown(report, meta, max_lines=max_lines))


def _scan_paths(paths: tuple[Path, ...], repo: Path, root: Path) -> tuple[str, ...]:
    if not paths:
        return (".",)
    out: list[str] = []
    for path in paths:
        if ".." in path.parts:
            raise UsageError(f"path escapes the repository: {path}")
        # Lexical only: a symlink in the working tree must not redirect the
        # committed path being scored. A symlink above the repository (such
        # as /var -> /private/var) is fine: only an ancestor that is the root
        # counts.
        full = Path(
            os.path.normpath(path if path.is_absolute() else repo.resolve() / path),
        )
        rel = _relative_to_root(full, root)
        if rel is None:
            raise UsageError(f"path is outside the repository: {path}")
        out.append(rel)
    return tuple(dict.fromkeys(out))


def _relative_to_root(full: Path, root: Path) -> str | None:
    if full == root or root in full.parents:
        return full.relative_to(root).as_posix()
    for ancestor in full.parents:
        if Path(os.path.realpath(ancestor)) == root:
            return full.relative_to(ancestor).as_posix()
    return None


def _existing(root: Path, sha: str, paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(p for p in paths if delta_git.path_exists(root, sha, p))


def _score_side(  # noqa: PLR0913
    root: Path,
    sha: str,
    paths: tuple[str, ...],
    dest: Path,
    exclude: tuple[str, ...],
    profile: str,
) -> ScanSnapshot:
    if not paths:
        return empty_snapshot()
    delta_git.export_tree(root, sha, (*paths, *_ancestor_ignores(root, sha, paths)), dest)
    config = Config(exclude=exclude, base_dir=dest)
    targets = tuple(dest if p == "." else dest / p for p in paths)
    try:
        result = analyze_paths(
            tuple(t for t in targets if t.exists()),
            config,
            profile=PROFILES[profile],
            strict_sg=True,
        )
    except FileNotFoundError:
        return empty_snapshot()
    return snapshot_from_result(result, dest)


def _ancestor_ignores(root: Path, sha: str, paths: tuple[str, ...]) -> tuple[str, ...]:
    """Return `.gitignore` files above each scan path, so ignore rules apply."""
    if "." in paths:
        return ()
    found: dict[str, None] = {}
    for path in paths:
        for parent in Path(path).parents:
            ignore = (parent / ".gitignore").as_posix()
            if delta_git.path_exists(root, sha, ignore):
                found[ignore] = None
    return tuple(found)


def _changes(
    root: Path,
    old: str,
    new: str,
    paths: tuple[str, ...],
) -> tuple[tuple[ChangedFile, LineMap], ...]:
    files = delta_git.changed_files(root, old, new, paths)
    out: list[tuple[ChangedFile, LineMap]] = []
    for change in files:
        target = change.new_path or change.old_path or ""
        if not delta_git.is_supported_name(target):
            continue
        out.append((change, delta_git.line_map(root, old, new, change)))
    return tuple(out)


def _rule_count(profile: str) -> int:
    rule_set = (
        RuleSet.TYPESCRIPT
        if RuleSet.TYPESCRIPT in PROFILES[profile].rule_sets
        else RuleSet.PYTHON
    )
    ids: set[str] = set()
    for _name, text in rule_texts(rule_set):
        for doc in yaml.safe_load_all(text):
            if isinstance(doc, dict) and doc.get("id"):
                ids.add(str(doc["id"]))
    return len(ids)

