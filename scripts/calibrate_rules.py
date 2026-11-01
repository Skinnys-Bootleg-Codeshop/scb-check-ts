"""Measure TS rules on real repos and apply the D pruning thresholds.

Phases:
  measure (default)  run `analyze_paths` under the ts profile with strict ast-grep, write
                     per-rule statistics to --out-json and a labelling sheet
                     (`labels.todo.csv`, with source snippets) to --labels-dir
  --labels FILE      read a filled `labels.csv` (rule,repo,file,line,label) and the
                     measure output, apply the thresholds, print one decision per rule

Source text stays in --labels-dir, which is machine-local; only numbers and paths go in
--out-json.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from scb_check.config import PROFILES
from scb_check.config import Config
from scb_check.pipeline import AnalysisResult
from scb_check.pipeline import analyze_paths
from scb_check.reporting.score import compute_report

PREFIX = "ts-"
MAX_FILE_HIT_RATE = 0.30
KEEP_PRECISION = 0.70
TIGHTEN_PRECISION = 0.50
LINE_SHARE_LIMIT = 0.25
LINE_SHARE_PRECISION = 0.85
MAX_MEAN_SPAN = 12
THIN_HITS = 5
SAMPLE_SIZE = 20
CONTEXT_LINES = 2


def parse_corpus(spec: str) -> tuple[str, Path, list[str]]:
    """Split NAME=PATH:SCAN[,SCAN] into its parts."""
    name, _, rest = spec.partition("=")
    path, _, scans = rest.rpartition(":")
    return (
        name,
        Path(path).expanduser().resolve(),
        [s for s in scans.split(",") if s],
    )


def measure_corpus(
    repo: Path, scans: list[str]
) -> tuple[dict[str, Any], AnalysisResult]:
    """Run the ts profile on one repo and collect per-rule statistics."""
    profile = PROFILES["ts"]
    result = analyze_paths(
        tuple(repo / s for s in scans),
        Config(exclude=(), base_dir=repo),
        profile=profile,
        strict_sg=True,
    )
    flags = result.flags
    report: dict[str, Any] = dict(compute_report(flags).to_dict())
    sloc_flagged: dict[Path, frozenset[int]] = {
        fl.file: frozenset(fl.lines)
        for fl in flags.lines.ast_sloc_lines_by_file
    }
    scanned = len(flags.lines.total_loc_by_file)
    per_rule: dict[str, Any] = {}
    by_rule: dict[str, list] = defaultdict(list)
    for hit in flags.findings.ast_grep_hits:
        by_rule[hit.rule_id].append(hit)
    ast_total = int(report["ast_grep_flagged_loc"])
    for rule_id, hits in sorted(by_rule.items()):
        lines_by_file: dict[Path, set[int]] = defaultdict(set)
        spans = []
        for hit in hits:
            span = set(range(hit.line, hit.end_line + 1)) & sloc_flagged.get(
                hit.file, frozenset()
            )
            spans.append(len(span))
            lines_by_file[hit.file] |= span
        flagged = sum(len(v) for v in lines_by_file.values())
        per_rule[rule_id] = {
            "hits": len(hits),
            "files_hit": len({h.file for h in hits}),
            "file_hit_rate": len({h.file for h in hits}) / scanned
            if scanned
            else 0.0,
            "flagged_sloc": flagged,
            "line_share": flagged / ast_total if ast_total else 0.0,
            "mean_span": sum(spans) / len(spans),
            "hit_list": sorted(
                [str(h.file.relative_to(repo)), h.line, h.end_line]
                for h in hits
            ),
        }
    return {
        "repo": str(repo),
        "files_scanned": scanned,
        "total_loc": report["total_loc"],
        "ast_grep_flagged_loc": ast_total,
        "ast_share": ast_total / report["total_loc"]
        if report["total_loc"]
        else 0.0,
        "per_rule": per_rule,
    }, result


def sample_hits(
    stats: dict[str, Any],
    only: set[str] | None,
    seed: int,
    ruleset_ids: set[str],
) -> list[tuple[str, str, str, int]]:
    """Return (rule, repo, file, line) samples, min(20, hits) per rule, stratified by repo."""
    rng = random.Random(seed)  # noqa: S311
    rows: list[tuple[str, str, str, int]] = []
    for rule_id in sorted(ruleset_ids):
        if only and rule_id not in only:
            continue
        pool: dict[str, list[tuple[str, int]]] = {}
        for repo, data in stats.items():
            entry = data["per_rule"].get(rule_id)
            if entry:
                pool[repo] = [(f, ln) for f, ln, _ in entry["hit_list"]]
        total = sum(len(v) for v in pool.values())
        want = min(SAMPLE_SIZE, total)
        if not want:
            continue
        # stratified: one per repo first, then proportional, then top up at random
        chosen: dict[str, list[tuple[str, int]]] = {}
        for repo in sorted(pool):
            share = max(1, round(want * len(pool[repo]) / total))
            chosen[repo] = rng.sample(pool[repo], min(share, len(pool[repo])))
        flat = [
            (repo, f, ln) for repo, items in chosen.items() for f, ln in items
        ]
        while len(flat) > want:
            flat.pop(rng.randrange(len(flat)))
        for repo, f, ln in sorted(flat):
            rows.append((rule_id, repo, f, ln))
    return rows


def write_todo(
    rows: list[tuple[str, str, str, int]],
    repos: dict[str, Path],
    messages: dict[str, str],
    path: Path,
    seed: int = 1233,
) -> None:
    """Write the labelling sheet, with a two-line snippet either side of each hit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rule",
                "repo",
                "file",
                "line",
                "message",
                "snippet",
                "label",
                "seed",
            ]
        )
        for rule_id, repo, file, line in rows:
            lines = (
                (repos[repo] / file).read_text(errors="replace").splitlines()
            )
            lo = max(0, line - 1 - CONTEXT_LINES)
            snippet = "\n".join(
                f"{n + 1:>5}{'>' if n + 1 == line else ' '} {lines[n]}"
                for n in range(lo, min(len(lines), line + CONTEXT_LINES))
            )
            writer.writerow(
                [
                    rule_id,
                    repo,
                    file,
                    line,
                    messages.get(rule_id, ""),
                    snippet,
                    "",
                    seed,
                ]
            )


def rule_messages() -> tuple[dict[str, str], set[str]]:
    """Return rule messages and ids for the active TS rule set."""
    import yaml  # noqa: PLC0415

    from scb_check.resources import RuleSet  # noqa: PLC0415
    from scb_check.resources import rule_texts  # noqa: PLC0415

    messages: dict[str, str] = {}
    for _, text in rule_texts(RuleSet.TYPESCRIPT):
        for doc in yaml.safe_load_all(text):
            if doc and str(doc.get("id", "")).startswith(PREFIX):
                messages[doc["id"]] = str(doc.get("message", ""))
    return messages, set(messages)


def verdict(  # noqa: PLR0911
    hits: int, rate: float, share: float, span: float, precision: float | None
) -> tuple[str, str]:
    """Apply the thresholds, in order, to one rule's measurements."""
    if hits == 0:
        return "keep", "unproven on real code"
    if rate > MAX_FILE_HIT_RATE:
        return "tighten", f"file-hit rate {rate:.1%} over 30%"
    if hits < THIN_HITS:
        return "keep", "thin evidence"
    if precision is None:
        return "unlabelled", ""
    if precision < TIGHTEN_PRECISION:
        return "prune", f"precision {precision:.0%} under 50%"
    if precision < KEEP_PRECISION:
        return "tighten", f"precision {precision:.0%} in 50-70%"
    if share > LINE_SHARE_LIMIT and precision < LINE_SHARE_PRECISION:
        return (
            "tighten",
            f"line share {share:.1%} over 25% with precision {precision:.0%}",
        )
    if span > MAX_MEAN_SPAN:
        return "tighten", f"mean span {span:.1f} over 12"
    return "keep", ""


# Rules the first pass already tightened once; the one-tighten limit means a second
# "tighten" verdict on them is a prune, decided on the seed-1234 resample alone.
ALREADY_TIGHTENED = frozenset(
    {
        "ts-nested-ternary",
        "ts-wrapper-function",
        "ts-if-return-bool",
        "ts-as-unknown-as",
    }
)


def _tally(labels: Path) -> dict[str, dict[str, list[int]]]:
    """Count tp/fp per rule and seed from a filled labels file."""
    tally: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0])
    )
    with labels.open() as handle:
        for row in csv.DictReader(handle):
            label = row["label"].strip().lower()
            if label in {"tp", "fp"}:
                tally[row["rule"]][row.get("seed", "1233") or "1233"][
                    0 if label == "tp" else 1
                ] += 1
    return tally


def decide(
    stats: dict[str, Any], labels: Path, rule_ids: set[str]
) -> dict[str, dict]:
    """Apply the section 5 thresholds in order and return a decision per rule.

    Seed-1233 rows judge the rule as first measured. A rule in ALREADY_TIGHTENED that the
    first pass sends to "tighten" is not tightened again: its seed-1234 rows decide it,
    keep at 70% (85% where its line share is over 25%), otherwise prune.
    """
    tally = _tally(labels)
    out: dict[str, dict] = {}
    for rule_id in sorted(rule_ids):
        entries = {
            repo: d["per_rule"].get(rule_id) for repo, d in stats.items()
        }
        live = [e for e in entries.values() if e]
        hits = sum(e["hits"] for e in live)
        rate = max((e["file_hit_rate"] for e in live), default=0.0)
        rates = {
            repo: (e["file_hit_rate"] if e else 0.0)
            for repo, e in entries.items()
        }
        share = max((e["line_share"] for e in live), default=0.0)
        span = (
            sum(e["mean_span"] * e["hits"] for e in live) / hits
            if hits
            else 0.0
        )
        tp, fp = tally[rule_id]["1233"]
        precision = tp / (tp + fp) if tp + fp else None
        decision, reason = verdict(hits, rate, share, span, precision)
        tp2, fp2 = tally[rule_id]["1234"]
        if decision == "tighten" and rule_id in ALREADY_TIGHTENED:
            p2 = tp2 / (tp2 + fp2) if tp2 + fp2 else None
            need = (
                LINE_SHARE_PRECISION
                if share > LINE_SHARE_LIMIT
                else KEEP_PRECISION
            )
            if p2 is not None and p2 >= need:
                decision, reason = (
                    "keep",
                    f"tightened once; resample precision {p2:.0%}",
                )
            else:
                decision, reason = (
                    "prune",
                    "tightened once; resample under threshold or missing",
                )
        out[rule_id] = {
            "hits": hits,
            "max_file_hit_rate": rate,
            "file_hit_rate_by_repo": rates,
            "max_line_share": share,
            "mean_span": span,
            "tp": tp,
            "fp": fp,
            "precision": precision,
            "decision": decision,
            "reason": reason,
        }
    return out


def main(argv: list[str] | None = None) -> int:
    """Run the measure phase, or decide with --labels."""
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus", action="append", default=[], help="NAME=PATH:SCAN[,SCAN]"
    )
    ap.add_argument("--seed", type=int, default=1233)
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--labels-dir", type=Path)
    ap.add_argument(
        "--labels", type=Path, help="filled labels.csv; prints decisions"
    )
    ap.add_argument(
        "--only",
        help="comma-separated rule ids to sample (resample after tightening)",
    )
    ap.add_argument("--todo-name", default="labels.todo.csv")
    ap.add_argument(
        "--measurements",
        type=Path,
        help="with --labels: decide from this preserved measurement file; nothing is re-measured or written",
    )
    args = ap.parse_args(argv)
    messages, rule_ids = rule_messages()
    if args.labels and args.measurements:
        saved: dict[str, Any] = json.loads(args.measurements.read_text())
        ids = set(rule_ids)
        for repo_stats in saved.values():
            ids |= set(repo_stats["per_rule"])
        with args.labels.open() as handle:
            ids |= {row["rule"] for row in csv.DictReader(handle)}
        print(json.dumps(decide(saved, args.labels, ids), indent=1, sort_keys=True))
        return 0
    if not (args.corpus and args.out_json and args.labels_dir):
        ap.error("--corpus, --out-json and --labels-dir are required unless deciding with --measurements")
    corpora = [parse_corpus(c) for c in args.corpus]
    stats: dict[str, Any] = {}
    for name, repo, scans in corpora:
        stats[name], _ = measure_corpus(repo, scans)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(stats, indent=1, sort_keys=True))
    if args.labels:
        decisions = decide(stats, args.labels, rule_ids)
        print(json.dumps(decisions, indent=1, sort_keys=True))
        return 0
    only = set(args.only.split(",")) if args.only else None
    rows = sample_hits(stats, only, args.seed, rule_ids)
    write_todo(
        rows,
        {n: r for n, r, _ in corpora},
        messages,
        args.labels_dir / args.todo_name,
        args.seed,
    )
    for name, data in stats.items():
        print(
            name,
            "files",
            data["files_scanned"],
            "ast_share",
            f"{data['ast_share']:.4f}",
        )
    print(f"{len(rows)} samples -> {args.labels_dir / args.todo_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
