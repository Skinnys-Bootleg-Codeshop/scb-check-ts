"""Run ast-grep rules and convert matches to findings."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

from scb_check.logging import get_logger
from scb_check.models import AstGrepHit
from scb_check.models import AstGrepSeverity

logger = get_logger(__name__)

_PYTHON_ENV_AST_GREP_BINARIES = ("sg", "ast-grep")


_ARGV_BATCH = 1000


class AstGrepError(ValueError):
    """Raised by strict ast-grep runs when no binary produces usable output."""


def run_sg(files: tuple[Path, ...], rules_path: Path) -> tuple[AstGrepHit, ...]:
    """Invoke ast-grep against ``files`` using ``rules_path``.

    A global ``sg`` executable is tried first; package-managed executables
    next to the current Python interpreter are retried if global ``sg`` is
    missing or fails. Returns an empty tuple — never raises — when no
    binary succeeds, subprocess execution fails, all exits are non-zero,
    or the JSON payload is unparseable. A missing binary is treated as a
    hard failure, so scb-check still produces clone and erosion numbers.
    Line and column numbers in the returned hits are 1-indexed. Files are
    passed in batches of at most 1000 so argv stays below the OS limit.
    """
    hits: list[AstGrepHit] = []
    for batch in _batches(files):
        commands = _commands(batch, rules_path)
        last_failure: subprocess.CompletedProcess[str] | OSError | None = None
        for command in commands:
            result = _run_command(command)
            if isinstance(result, OSError):
                last_failure = result
                continue

            if result.returncode == 0:
                hits.extend(_parse_hits(result.stdout))
                last_failure = None
                break

            last_failure = result

        if last_failure is not None:
            _log_run_failure(last_failure)

    return _sorted_hits(hits)


def run_sg_strict(
    files: tuple[Path, ...],
    rules_path: Path,
) -> tuple[AstGrepHit, ...]:
    """Invoke ast-grep like `run_sg`, but raise `AstGrepError` on any failure."""
    if not files:
        return ()

    hits: list[AstGrepHit] = []
    for batch in _batches(files):
        commands = _commands(batch, rules_path)
        if not commands:
            raise AstGrepError(
                "ast-grep could not run: binary not found or rules file missing",
            )

        stdout = _first_success(commands)
        lines = [line for line in stdout.splitlines() if line.strip()]
        parsed = [hit for line in lines if (hit := _parse_hit(line)) is not None]
        if len(parsed) != len(lines):
            raise AstGrepError("ast-grep output could not be parsed")
        hits.extend(parsed)

    return _sorted_hits(hits)


def _first_success(commands: tuple[tuple[str, ...], ...]) -> str:
    detail = "no binary ran"
    for command in commands:
        result = _run_command(command)
        if isinstance(result, OSError):
            detail = f"failed to execute: {result}"
            continue

        if result.returncode == 0:
            return result.stdout

        stderr_lines = result.stderr.strip().splitlines()
        first_line = stderr_lines[0] if stderr_lines else ""
        detail = f"exit code {result.returncode}: {first_line}"

    raise AstGrepError(f"ast-grep failed ({detail})")


def _batches(files: tuple[Path, ...]) -> tuple[tuple[Path, ...], ...]:
    if not files:
        return ((),)
    return tuple(
        files[start : start + _ARGV_BATCH]
        for start in range(0, len(files), _ARGV_BATCH)
    )


def _sorted_hits(hits: list[AstGrepHit]) -> tuple[AstGrepHit, ...]:
    return tuple(
        sorted(
            hits,
            key=lambda hit: (
                hit.file.as_posix(),
                hit.line,
                hit.col,
                hit.rule_id,
            ),
        ),
    )


def _commands(files: tuple[Path, ...], rules_path: Path) -> tuple[tuple[str, ...], ...]:
    if not files or not rules_path.exists():
        logger.warning(
            "no files to scan or rules file missing",
            files=files,
            rules_path=rules_path,
            rules_exists=rules_path.exists(),
        )
        return ()

    ast_grep_binaries = _ast_grep_binaries()
    if not ast_grep_binaries:
        logger.warning("ast-grep binary not found", binary="ast-grep")
        return ()

    return tuple(
        (
            binary,
            "scan",
            "--json=stream",
            "-r",
            str(rules_path),
            *[str(path) for path in files],
        )
        for binary in ast_grep_binaries
    )


def _ast_grep_binaries() -> tuple[str, ...]:
    binaries: list[str] = []
    if (global_sg := shutil.which("sg")) is not None:
        binaries.append(global_sg)

    for binary in _PYTHON_ENV_AST_GREP_BINARIES:
        if (candidate := _python_env_executable(binary)) is not None:
            candidate_text = str(candidate)
            if candidate_text not in binaries:
                binaries.append(candidate_text)

    return tuple(binaries)


def _python_env_executable(binary: str) -> Path | None:
    candidate = Path(sys.executable).parent / binary
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate

    return None


def _run_command(
    command: tuple[str, ...],
) -> subprocess.CompletedProcess[str] | OSError:
    try:
        return subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return exc


def _log_run_failure(failure: subprocess.CompletedProcess[str] | OSError) -> None:
    if isinstance(failure, OSError):
        logger.warning("failed to execute ast-grep", error=str(failure))
        return

    logger.warning(
        "ast-grep returned non-zero",
        returncode=failure.returncode,
        stderr=failure.stderr.strip(),
    )


def _parse_hits(stdout: str) -> tuple[AstGrepHit, ...]:
    return tuple(
        hit
        for line in stdout.splitlines()
        if line.strip()
        if (hit := _parse_hit(line)) is not None
    )


def _parse_hit(line: str) -> AstGrepHit | None:
    try:
        payload = json.loads(line)
        start = payload["range"]["start"]
        end = payload["range"]["end"]
        return AstGrepHit(
            file=Path(payload["file"]).resolve(),
            line=int(start["line"]) + 1,
            end_line=int(end["line"]) + 1,
            col=int(start["column"]),
            end_col=int(end["column"]),
            rule_id=str(payload["ruleId"]),
            matched_text=str(payload["text"]),
            message=str(payload["message"]),
            severity=_severity(payload.get("severity")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("failed to parse ast-grep output", error=str(exc))
        return None


def _severity(value: object) -> AstGrepSeverity:
    return (
        cast("AstGrepSeverity", value)
        if value in {"info", "warning", "critical"}
        else "warning"
    )
