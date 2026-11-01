"""Compare two scored snapshots of one repository: a pull request delta.

Pure functions. Git access lives in `scb_check.commands.delta_git`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from scb_check.commands.delta_git import ChangedFile
from scb_check.commands.delta_git import LineMap
from scb_check.models import Report
from scb_check.pipeline import AnalysisResult
from scb_check.reporting.score import compute_report

_MAX_SOURCE_CHARS = 120
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_METRICS = ("verbosity", "erosion", "cog_erosion", "sloc", "flagged_sloc")
_FLOAT_METRICS = frozenset({"verbosity", "erosion", "cog_erosion"})
_CLONE_ROW = "clone_loc"
_CLONE_NOTE = "below target precision"
_LABELS = {
    "sloc": "SLOC",
    "flagged_sloc": "flagged SLOC",
    _CLONE_ROW: f"{_CLONE_ROW} ({_CLONE_NOTE})",
}


@dataclass(frozen=True, slots=True)
class ScanSnapshot:
    """Everything a delta needs from one scored tree."""

    report: Report | None
    flagged: Mapping[str, Mapping[int, tuple[str, ...]]]
    source_lines: Mapping[str, tuple[str, ...]]
    functions: tuple[tuple[str, str, int, int, int], ...]
    skipped_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FlaggedLine:
    """One flagged head line."""

    path: str
    line: int
    signals: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class DeltaReport:
    """The outcome of comparing base and head snapshots."""

    base: ScanSnapshot
    head: ScanSnapshot
    comparable: bool
    incomparable: tuple[str, ...]
    new_lines: tuple[FlaggedLine, ...]
    newly_flagged: tuple[FlaggedLine, ...]
    cleared: int
    changed_functions: tuple[tuple[str, str, int, int, int], ...]


@dataclass(frozen=True, slots=True)
class DeltaMeta:
    """Context printed around a delta."""

    tool_sha: str
    profile: str
    rule_count: int
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    paths: tuple[str, ...]
    dirty: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)
    clone_row: bool = False


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.resolve().relative_to(root.resolve()).as_posix()


def _lines_of(spans: tuple[tuple[int, int, str], ...], line: int) -> list[str]:
    return [name for start, end, name in spans if start <= line <= end]


def snapshot_from_result(result: AnalysisResult, root: Path) -> ScanSnapshot:
    """Reduce an analysis `result` of the tree at `root` to a snapshot."""
    flags = result.flags
    names: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for entry in flags.lines.clone_sloc_lines_by_file:
        for line in entry.lines:
            names[_rel(entry.file, root)][line].add("clone")
    ast_spans: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    for hit in flags.findings.ast_grep_hits:
        ast_spans[hit.file].append((hit.line, hit.end_line, hit.rule_id))
    for entry in flags.lines.ast_sloc_lines_by_file:
        spans = tuple(ast_spans.get(entry.file, ()))
        for line in entry.lines:
            names[_rel(entry.file, root)][line].update(
                _lines_of(spans, line) or ["ast-grep"],
            )
    structural: dict[Path, list[tuple[int, int, str]]] = defaultdict(list)
    for finding in flags.findings.structural_findings:
        structural[finding.file].append(
            (finding.span.start_line, finding.span.end_line, finding.rule_id),
        )
    for entry in flags.lines.structural_sloc_lines_by_file:
        spans = tuple(structural.get(entry.file, ()))
        for line in entry.lines:
            names[_rel(entry.file, root)][line].update(
                _lines_of(spans, line) or ["structural"],
            )
    prefixes = (root.as_posix() + "/", root.resolve().as_posix() + "/")
    functions = sorted(
        (
            _rel(fn.file, root),
            _strip_prefixes(fn.qualified_name, prefixes),
            fn.sloc,
            fn.cyc_complexity,
            fn.cog_complexity,
        )
        for fn in flags.findings.all_functions
    )
    return ScanSnapshot(
        report=compute_report(flags) if flags.lines.total_loc_by_file else None,
        flagged={
            path: {line: tuple(sorted(found)) for line, found in by_line.items()}
            for path, by_line in names.items()
        },
        source_lines={
            _rel(path, root): lines
            for path, lines in result.source_lines_by_file.items()
        },
        functions=tuple(functions),
        skipped_files=tuple(sorted(_rel(path, root) for path in result.skipped_files)),
    )


def _strip_prefixes(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        text = text.replace(prefix, "")
    return text


def empty_snapshot() -> ScanSnapshot:
    """Return the snapshot of a tree with nothing scanned."""
    return ScanSnapshot(None, {}, {}, (), ())


def _base_path_of(path: str, renames: Mapping[str, str]) -> str:
    return renames.get(path, path)


def compute_delta(
    base: ScanSnapshot,
    head: ScanSnapshot,
    changes: tuple[tuple[ChangedFile, LineMap], ...],
) -> DeltaReport:
    """Compare `head` against `base` using the git `changes` between them."""
    maps: dict[str, LineMap] = {}
    renames: dict[str, str] = {}
    to_head: dict[str, str] = {}
    for change, lmap in changes:
        if change.new_path is not None:
            maps[change.new_path] = lmap
        if change.status == "R" and change.old_path and change.new_path:
            renames[change.new_path] = change.old_path
            to_head[change.old_path] = change.new_path
    incomparable = _incomparable_reasons(base, head, renames, to_head)
    new_lines: list[FlaggedLine] = []
    newly: list[FlaggedLine] = []
    mapped_old: dict[str, set[int]] = defaultdict(set)
    for path in sorted(head.flagged):
        lmap = maps.get(path)
        base_path = _base_path_of(path, renames)
        base_flagged = base.flagged.get(base_path, {})
        for line in sorted(head.flagged[path]):
            entry = FlaggedLine(
                path,
                line,
                head.flagged[path][line],
                _source_text(head, path, line),
            )
            old_line = line if lmap is None else lmap.to_old(line)
            if old_line is None:
                new_lines.append(entry)
                continue
            mapped_old[base_path].add(old_line)
            if old_line not in base_flagged:
                newly.append(entry)
    cleared = sum(
        len(set(lines) - mapped_old.get(path, set()))
        for path, lines in base.flagged.items()
    )
    changed_paths = {
        change.new_path for change, _ in changes if change.new_path is not None
    }
    return DeltaReport(
        base=base,
        head=head,
        comparable=not incomparable,
        incomparable=incomparable,
        new_lines=tuple(new_lines),
        newly_flagged=tuple(newly),
        cleared=cleared,
        changed_functions=tuple(
            fn for fn in head.functions if fn[0] in changed_paths
        ),
    )


def _incomparable_reasons(
    base: ScanSnapshot,
    head: ScanSnapshot,
    renames: Mapping[str, str],
    to_head: Mapping[str, str],
) -> tuple[str, ...]:
    reasons: list[str] = []
    base_scored = set(base.source_lines)
    head_scored = set(head.source_lines)
    base_skipped = set(base.skipped_files)
    head_skipped = set(head.skipped_files)
    for path in sorted(head_skipped):
        counterpart = _base_path_of(path, renames)
        if counterpart in base_skipped:
            continue
        if counterpart in base_scored:
            reasons.append(f"`{_escape(path)}` was scored at base and skipped at head")
        else:
            reasons.append(f"`{_escape(path)}` is new at head and was skipped")
    for path in sorted(base_skipped):
        counterpart = to_head.get(path, path)
        if counterpart in head_skipped:
            continue
        if counterpart in head_scored:
            reasons.append(f"`{_escape(path)}` was skipped at base and scored at head")
    return tuple(reasons)


def _source_text(snapshot: ScanSnapshot, path: str, line: int) -> str:
    lines = snapshot.source_lines.get(path, ())
    return lines[line - 1].strip() if 0 < line <= len(lines) else ""


def _metrics(snapshot: ScanSnapshot) -> dict[str, float | int] | None:
    report = snapshot.report
    if report is None or not report.verbosity_summary.total_loc:
        return None
    summary = report.verbosity_summary
    return {
        "verbosity": report.scores.verbosity,
        "erosion": report.scores.erosion,
        "cog_erosion": report.scores.cog_erosion,
        "sloc": summary.total_loc,
        "flagged_sloc": summary.verbosity_flagged_loc,
        _CLONE_ROW: summary.clone_loc,
    }


def _fmt(name: str, value: float) -> str:
    return f"{value:.4f}" if name in _FLOAT_METRICS else str(int(value))


def _fmt_delta(name: str, base: float, head: float) -> str:
    diff = head - base
    if name in _FLOAT_METRICS:
        return "0.0000" if round(diff, 4) == 0 else f"{diff:+.4f}"
    return "0" if diff == 0 else f"{int(diff):+d}"


def _escape(text: str) -> str:
    """Make `text` safe inside a Markdown code span: no backtick can close it."""
    text = _CONTROL.sub("", text)
    return text.replace("`", "'").replace("|", "\\|")


def _plain(text: str) -> str:
    """Keep only characters that cannot start Markdown or HTML."""
    return re.sub(r"[^A-Za-z0-9_.:-]", "", text)


def _cut(text: str) -> str:
    return text[:_MAX_SOURCE_CHARS]


def _table(delta: DeltaReport, meta: DeltaMeta) -> list[str]:
    base, head = _metrics(delta.base), _metrics(delta.head)
    rows = ["| Metric | Base | Head | Delta |", "| --- | --- | --- | --- |"]
    names = [*_METRICS, *((_CLONE_ROW,) if meta.clone_row else ())]
    for name in names:
        label = _LABELS.get(name, name)
        base_cell = "n/a" if base is None else _fmt(name, base[name])
        head_cell = "n/a" if head is None else _fmt(name, head[name])
        if base is None or head is None or not delta.comparable:
            delta_cell = "incomparable" if not delta.comparable else "n/a"
        else:
            delta_cell = _fmt_delta(name, base[name], head[name])
        rows.append(f"| {label} | {base_cell} | {head_cell} | {delta_cell} |")
    return rows


def render_markdown(
    delta: DeltaReport,
    meta: DeltaMeta,
    *,
    max_lines: int,
) -> str:
    """Render `delta` as a Markdown block for a pull request."""
    scanned = ", ".join(f"`{_escape(path)}`" for path in meta.paths)
    out = [
        f"### Slop delta (scb-check {meta.tool_sha}, profile {meta.profile}, "
        f"{meta.rule_count} rules)",
        "",
        f"Base `{_escape(meta.base_ref)}` at merge-base `{meta.base_sha[:7]}`, "
        f"head `{meta.head_sha[:7]}`. Scanned: {scanned}.",
        "",
    ]
    if _metrics(delta.base) is None and _metrics(delta.head) is None:
        out.append("no scanned source on either side")
    else:
        out.extend(_table(delta, meta))
    out.append("")
    if not delta.comparable:
        out.append(
            "Incomparable: a file was parsed on one side only, so the numbers "
            "do not compare.",
        )
        out.extend(f"- {reason}" for reason in delta.incomparable)
        out.append("")
        out.append(_skipped_line(delta))
        return _finish(out, delta, meta)
    out.append(
        f"New flagged lines: {len(delta.new_lines)}. "
        f"Existing lines newly flagged: {len(delta.newly_flagged)}. "
        f"Flagged lines cleared: {delta.cleared}.",
    )
    out.append("")
    entries = (*delta.new_lines, *delta.newly_flagged)
    out.extend(_entry(item) for item in entries[:max_lines])
    if len(entries) > max_lines:
        out.append(f"- ... and {len(entries) - max_lines} more")
    return _finish(out, delta, meta)


def _skipped_line(delta: DeltaReport) -> str:
    return (
        f"Skipped (unparsable) files: base {len(delta.base.skipped_files)}, "
        f"head {len(delta.head.skipped_files)}."
    )


def _finish(out: list[str], delta: DeltaReport, meta: DeltaMeta) -> str:
    extra: list[str] = []
    if delta.base.skipped_files or delta.head.skipped_files:
        line = _skipped_line(delta)
        if line not in out:
            extra.append(line)
    if meta.dirty:
        extra.append(
            "Uncommitted changes in the working tree were not scored; "
            "only the committed head was.",
        )
    extra.extend(meta.notes)
    return "\n".join([*out, *extra]).rstrip("\n") + "\n"


def _entry(item: FlaggedLine) -> str:
    text = _escape(_cut(_CONTROL.sub("", item.text)))
    signals = ", ".join(_plain(name) for name in item.signals)
    return f"- `{_escape(item.path)}:{item.line}` {signals}: `{text}`"


def delta_to_dict(delta: DeltaReport, meta: DeltaMeta) -> dict[str, object]:
    """Return the JSON-compatible form of `delta`."""
    base, head = _metrics(delta.base), _metrics(delta.head)

    def _side(metrics: dict[str, float | int] | None) -> dict[str, object] | None:
        return None if metrics is None else dict(metrics)

    diff: dict[str, object] | None = None
    if base is not None and head is not None and delta.comparable:
        diff = {name: head[name] - base[name] for name in base}

    def _flagged(items: tuple[FlaggedLine, ...]) -> list[dict[str, object]]:
        return [
            {
                "path": item.path,
                "line": item.line,
                "signals": list(item.signals),
                "text": _cut(_CONTROL.sub("", item.text)),
            }
            for item in items
        ]

    return {
        "comparable": delta.comparable,
        "incomparable": list(delta.incomparable),
        "meta": {
            "tool_sha": meta.tool_sha,
            "profile": meta.profile,
            "rule_count": meta.rule_count,
            "base_ref": meta.base_ref,
            "base_sha": meta.base_sha,
            "head_ref": meta.head_ref,
            "head_sha": meta.head_sha,
            "paths": list(meta.paths),
            "dirty": meta.dirty,
            "notes": list(meta.notes),
            "clone_loc_below_target_precision": meta.clone_row,
        },
        "base": _side(base),
        "head": _side(head),
        "delta": diff,
        "new_flagged": _flagged(delta.new_lines) if delta.comparable else None,
        "newly_flagged_existing": (
            _flagged(delta.newly_flagged) if delta.comparable else None
        ),
        "cleared": delta.cleared if delta.comparable else None,
        "skipped_files": {
            "base": list(delta.base.skipped_files),
            "head": list(delta.head.skipped_files),
        },
        "changed_functions": [list(fn) for fn in delta.changed_functions],
    }
