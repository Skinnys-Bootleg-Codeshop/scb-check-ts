"""Dump a full scb-check analysis as stable JSON, for golden comparison.

Uses only API present at the pristine commit, so the same script runs against
both the pristine export and the current tree.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from scb_check.models import FileLineSet
from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _line_sets(sets: Iterable[FileLineSet], root: Path) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for item in sets:
        out.setdefault(_rel(item.file, root), []).extend(item.lines)
    return {key: sorted(set(value)) for key, value in sorted(out.items())}


def dump(root: Path, suffixes: tuple[str, ...]) -> dict[str, object]:
    """Analyze files under `root` with `suffixes` and return the dump."""
    root = root.resolve()
    if root.is_file():
        candidates = [root]
        root = root.parent
    elif root.is_dir():
        candidates = list(root.rglob("*"))
    else:
        raise SystemExit(f"golden_dump: no such path: {root}")
    files = tuple(
        sorted(
            path.resolve()
            for path in candidates
            if path.is_file()
            and path.suffix in suffixes
            and "node_modules" not in path.parts
        )
    )
    if not files:
        raise SystemExit(f"golden_dump: no {suffixes} files under {root}")
    result = analyze_files(files)
    flags = result.flags
    prefix = root.as_posix() + "/"
    functions = sorted(
        [
            _rel(fn.file, root),
            fn.qualified_name.replace(prefix, ""),
            fn.start_line,
            fn.end_line,
            fn.sloc,
            fn.cyc_complexity,
            fn.cog_complexity,
        ]
        for fn in flags.findings.all_functions
    )
    clones = sorted(
        [
            _rel(c.file, root),
            c.start_line,
            c.end_line,
            c.group_hash,
            c.instance_count,
        ]
        for c in flags.findings.clones
    )
    ast_hits = sorted(
        [_rel(h.file, root), h.line, h.rule_id]
        for h in flags.findings.ast_grep_hits
    )
    return {
        "report": compute_report(flags).to_dict(),
        "functions": functions,
        "clones": clones,
        "clone_lines": _line_sets(flags.lines.clone_sloc_lines_by_file, root),
        "ast_lines": _line_sets(flags.lines.ast_sloc_lines_by_file, root),
        "structural_lines": _line_sets(
            flags.lines.structural_sloc_lines_by_file, root
        ),
        "ast_hits": ast_hits,
    }


def main(argv: list[str] | None = None) -> int:
    """Write the dump named by `argv` and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--suffix", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = dump(args.root, tuple(args.suffix))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
