"""Measure repos for the baseline report and pool per-rule shares.

Usage: baseline_report.py --out FILE NAME=PATH:SCAN[,SCAN] ...

Runs the ts profile with strict ast-grep, the same call as `calibrate_rules.py`.
Writes numbers, paths and line numbers only; no source text. Per repo: report
scores, run time, skipped files, per-rule hits and flagged SLOC, the ten
functions with the largest cyclomatic mass, and clone groups with exactly two
instances. Across all repos given: each rule's share of the pooled
`ast_grep_flagged_loc`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from calibrate_rules import measure_corpus
from calibrate_rules import parse_corpus

from scb_check.commands.delta import _rule_count
from scb_check.reporting.score import compute_report

TOP = 10


def _functions(result: Any, repo: Path) -> list[dict[str, Any]]:  # noqa: ANN401
    ranked = sorted(
        result.flags.findings.all_functions,
        key=lambda s: (-s.cc_mass(), str(s.file), s.start_line),
    )
    return [
        {
            "file": str(s.file.relative_to(repo)),
            "name": s.qualified_name,
            "lines": [s.start_line, s.end_line],
            "sloc": s.sloc,
            "cyclomatic": s.cyc_complexity,
            "cognitive": s.cog_complexity,
            "cc_mass": round(s.cc_mass(), 3),
        }
        for s in ranked[:TOP]
    ]


def _two_instance_groups(result: Any, repo: Path) -> list[dict[str, Any]]:  # noqa: ANN401
    groups: dict[str, list[Any]] = defaultdict(list)
    for block in result.flags.findings.clones:
        groups[block.group_hash].append(block)
    sloc_by_file = {
        fl.file: frozenset(fl.lines)
        for fl in result.flags.lines.clone_sloc_lines_by_file
    }
    out = []
    for group_hash, blocks in groups.items():
        if len(blocks) != 2:  # noqa: PLR2004
            continue
        size = sum(
            len(
                set(range(b.start_line, b.end_line + 1))
                & sloc_by_file.get(b.file, frozenset())
            )
            for b in blocks
        )
        out.append(
            {
                "group": group_hash[:12],
                "flagged_sloc": size,
                "instances": [
                    [str(b.file.relative_to(repo)), b.start_line, b.end_line]
                    for b in blocks
                ],
            }
        )
    out.sort(key=lambda g: (-g["flagged_sloc"], g["instances"][0]))
    return out[:TOP]


def main(argv: list[str] | None = None) -> int:
    """Measure every repo and write the baseline numbers."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("specs", nargs="+", help="NAME=PATH:SCAN[,SCAN]")
    args = ap.parse_args(argv)
    repos: dict[str, Any] = {}
    pooled_rule: dict[str, dict[str, int]] = defaultdict(
        lambda: {"hits": 0, "flagged_sloc": 0}
    )
    pooled_ast = pooled_loc = pooled_hits = 0
    for spec in args.specs:
        name, repo, scans = parse_corpus(spec)
        started = time.monotonic()
        stats, result = measure_corpus(repo, scans)
        seconds = time.monotonic() - started
        report = dict(compute_report(result.flags).to_dict())
        per_rule = stats["per_rule"]
        repos[name] = {
            "paths": scans,
            "seconds": round(seconds, 1),
            "rule_count": _rule_count("ts"),
            "report": {
                k: report[k]
                for k in (
                    "total_loc",
                    "files_scanned",
                    "verbosity",
                    "erosion",
                    "cog_erosion",
                    "clone_loc",
                    "ast_grep_flagged_loc",
                    "verbosity_flagged_loc",
                )
            },
            "skipped_files": sorted(
                str(p.relative_to(repo)) if repo in p.parents else str(p)
                for p in result.skipped_files
            ),
            "top_rules": sorted(
                (
                    {
                        "rule": rid,
                        "hits": v["hits"],
                        "flagged_sloc": v["flagged_sloc"],
                    }
                    for rid, v in per_rule.items()
                ),
                key=lambda r: (-r["flagged_sloc"], r["rule"]),
            )[:TOP],
            "top_functions": _functions(result, repo),
            "two_instance_clone_groups": _two_instance_groups(result, repo),
        }
        pooled_ast += stats["ast_grep_flagged_loc"]
        pooled_loc += stats["total_loc"]
        for rid, v in per_rule.items():
            pooled_rule[rid]["hits"] += v["hits"]
            pooled_rule[rid]["flagged_sloc"] += v["flagged_sloc"]
            pooled_hits += v["hits"]
        print(name, repos[name]["report"], f"{seconds:.1f}s", file=sys.stderr)
    rules = sorted(
        (
            {
                "rule": rid,
                "hits": v["hits"],
                "flagged_sloc": v["flagged_sloc"],
                "share_of_pooled_ast_flagged": v["flagged_sloc"] / pooled_ast
                if pooled_ast
                else 0.0,
                "share_of_pooled_sloc": v["flagged_sloc"] / pooled_loc
                if pooled_loc
                else 0.0,
            }
            for rid, v in pooled_rule.items()
        ),
        key=lambda r: (-r["flagged_sloc"], r["rule"]),
    )
    out = {
        "repos": repos,
        "pooled": {
            "sloc": pooled_loc,
            "ast_grep_flagged_loc": pooled_ast,
            "ast_only_share": pooled_ast / pooled_loc if pooled_loc else 0.0,
            "hits": pooled_hits,
            "rules_by_flagged_sloc": rules,
        },
    }
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
