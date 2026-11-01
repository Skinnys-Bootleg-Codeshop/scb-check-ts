"""Score repos for the R3 separation test and pool them by group.

Usage: separation_score.py --out FILE GROUP:NAME=PATH:SCAN[,SCAN] ...

Each repo runs under the ts profile with strict ast-grep, the same call as
`calibrate_rules.py`. Only numbers are written; no source text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from calibrate_rules import measure_corpus
from calibrate_rules import parse_corpus

from scb_check.reporting.score import compute_report

SUMS = (
    "total_loc",
    "verbosity_flagged_loc",
    "clone_loc",
    "ast_grep_flagged_loc",
    "total_mass",
    "high_cc_mass",
    "total_cog_mass",
    "high_cog_mass",
)


def summarise(report: dict[str, Any], hits: int) -> dict[str, Any]:
    """Reduce a report to the pre-registered measures."""
    loc = report["total_loc"]
    return {
        "sloc": loc,
        "hits": hits,
        "ast_only_share": report["ast_grep_flagged_loc"] / loc if loc else 0.0,
        "verbosity": report["verbosity"],
        "clone_loc_share": report["clone_loc"] / loc if loc else 0.0,
        "erosion": report["erosion"],
        "cog_erosion": report["cog_erosion"],
        "files_scanned": report["files_scanned"],
        "sums": {k: report[k] for k in SUMS},
    }


def pool(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pool repos of one group by summing numerators and denominators."""
    s = {k: sum(i["sums"][k] for i in items) for k in SUMS}
    loc = s["total_loc"]
    return {
        "sloc": loc,
        "hits": sum(i["hits"] for i in items),
        "ast_only_share": s["ast_grep_flagged_loc"] / loc if loc else 0.0,
        "verbosity": s["verbosity_flagged_loc"] / loc if loc else 0.0,
        "clone_loc_share": s["clone_loc"] / loc if loc else 0.0,
        "erosion": s["high_cc_mass"] / s["total_mass"]
        if s["total_mass"]
        else 0.0,
        "cog_erosion": s["high_cog_mass"] / s["total_cog_mass"]
        if s["total_cog_mass"]
        else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    """Score every repo and write per-repo and per-group numbers."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("specs", nargs="+", help="GROUP:NAME=PATH:SCAN[,SCAN]")
    args = ap.parse_args(argv)
    repos: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for spec in args.specs:
        group, _, rest = spec.partition(":")
        name, repo, scans = parse_corpus(rest)
        stats, result = measure_corpus(repo, scans)
        report = dict(compute_report(result.flags).to_dict())
        hits = sum(r["hits"] for r in stats["per_rule"].values())
        item = summarise(report, hits)
        item["group"] = group
        item["per_rule_hits"] = {
            k: v["hits"] for k, v in stats["per_rule"].items()
        }
        item["skipped_files"] = len(result.skipped_files)
        repos[name] = item
        groups[group].append(item)
        print(
            name,
            json.dumps(
                {
                    k: v
                    for k, v in item.items()
                    if k not in {"sums", "per_rule_hits"}
                }
            ),
            file=sys.stderr,
        )
    out = {
        "repos": repos,
        "groups": {g: pool(items) for g, items in groups.items()},
    }
    args.out.write_text(json.dumps(out, indent=1, sort_keys=True))
    print(json.dumps(out["groups"], indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
