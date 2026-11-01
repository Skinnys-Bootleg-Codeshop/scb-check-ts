"""Measure how a repo scores under the TS profile, for the A2 spike.

Measures M1 to M7 from the plan. The alternative readings in M2 and M5 are local to
this script and are never imported back into scb-check.

Phases:
  measure (default)  write --out-json and the clone samples in --sample-dir
  --labels FILE      read a filled labels CSV (group_hash,label) and add precision
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import resource
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from scb_check.analysis.clones import detect_clones
from scb_check.config import PROFILES
from scb_check.config import CloneFilter
from scb_check.config import Config
from scb_check.pipeline import analyze_paths
from scb_check.tree_walking.dispatch import parse_source_file
from scb_check.tree_walking.languages.generic import (
    _ASSIGNMENT_PARENT_NODE_TYPES,
)
from scb_check.tree_walking.languages.generic import _is_boolean_operation
from scb_check.tree_walking.languages.registry import LANGUAGE_CONFIGS
from scb_check.tree_walking.models import Language
from scb_check.walker import is_scannable
from scb_check.walker import walk_source_files

if TYPE_CHECKING:
    from tree_sitter import Node
    from tree_sitter import Tree

    from scb_check.tree_walking.artifacts import ParsedFile
    from scb_check.tree_walking.models import SymbolIR

VARIANTS: tuple[CloneFilter, ...] = ("upstream", "no-expression-bodies", "no-jsx-dominated")
HIGH = 10


type _Key = tuple[Path, int, int, int, int]


def _node_key(file: Path, node: Node) -> _Key:
    """Identify a function node by file and full start/end position."""
    return (file, *node.start_point, *node.end_point)


def _sym_key(symbol: SymbolIR) -> _Key:
    """Identify a symbol by file and full span, as `_node_key` does for nodes."""
    span = symbol.span
    return (span.file, span.start_line - 1, span.start_col, span.end_line - 1, span.end_col)


def scan_files(repo: Path, paths: list[str]) -> tuple[Path, ...]:
    """Return the files `check --profile ts` would scan, as `analyze_paths` does."""
    profile = PROFILES["ts"]
    config = Config(exclude=profile.exclude, base_dir=repo, max_file_bytes=profile.max_file_bytes)
    files = {
        f
        for p in paths
        for f in walk_source_files(repo / p, config)
        if is_scannable(f, config)
    }
    return tuple(sorted(files))


def m1_parse(files: tuple[Path, ...]) -> tuple[dict[str, Any], list[ParsedFile], dict[str, float]]:
    """Parse every file, counting successes and failures per language."""
    parsed: list[ParsedFile] = []
    seen: Counter[str] = Counter()
    ok: Counter[str] = Counter()
    skipped: list[dict[str, str]] = []
    times: dict[str, float] = {}
    for f in files:
        lang = "tsx" if f.suffix == ".tsx" else f.suffix.lstrip(".")
        seen[lang] += 1
        started = time.perf_counter()
        try:
            pf = parse_source_file(f, f.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 - spike records any parse failure
            skipped.append({"file": str(f), "reason": f"{type(exc).__name__}: {str(exc)[:120]}"})
            continue
        times[str(f)] = time.perf_counter() - started
        ok[lang] += 1
        parsed.append(pf)
    tsx_seen, tsx_ok = seen["tsx"], ok["tsx"]
    return (
        {
            "seen": dict(seen),
            "parsed": dict(ok),
            "skipped": skipped,
            "tsx_parse_rate": (tsx_ok / tsx_seen) if tsx_seen else None,
        },
        parsed,
        times,
    )


def _walk(node: Node, ancestors: tuple[Node, ...] = ()):  # noqa: ANN202
    """Yield (node, ancestors) iteratively."""
    stack = [(node, ancestors)]
    while stack:
        current, anc = stack.pop()
        yield current, anc
        child_anc = (*anc, current)
        stack.extend((child, child_anc) for child in reversed(current.children))


def _erosion(symbols: list[tuple[int, int, int]]) -> float:
    """Return high-cc mass share over (cc, cog, sloc) triples."""
    total = sum(cc * math.sqrt(sloc) for cc, _, sloc in symbols)
    high = sum(cc * math.sqrt(sloc) for cc, _, sloc in symbols if cc > HIGH)
    return high / total if total else 0.0


def m2_callables(parsed: list[ParsedFile], symbols: tuple[SymbolIR, ...]) -> dict[str, Any]:
    """Count symbols that take their name across a function boundary."""
    crossing: set[_Key] = set()
    for pf in parsed:
        if pf.module.language not in {Language.TSX, Language.TYPESCRIPT}:
            continue
        cfg = LANGUAGE_CONFIGS[pf.module.language]
        for node, anc in _walk(cast("Tree", pf.native_tree).root_node):
            if node.type not in cfg.anonymous_function_node_types:
                continue
            idx = next(
                (
                    i
                    for i in range(len(anc) - 1, -1, -1)
                    if anc[i].type in _ASSIGNMENT_PARENT_NODE_TYPES
                    and any(c.type in cfg.identifier_node_types for c in anc[i].children)
                ),
                None,
            )
            if idx is None:
                continue
            if any(a.type in cfg.function_node_types for a in anc[idx + 1 :]):
                crossing.add(_node_key(pf.file, node))
    triples = [(s.cyc_complexity, s.cog_complexity, s.sloc) for s in symbols]
    kept = [
        (s.cyc_complexity, s.cog_complexity, s.sloc)
        for s in symbols
        if _sym_key(s) not in crossing
    ]
    cross_n = sum(1 for s in symbols if _sym_key(s) in crossing)
    return {
        "symbols_upstream": len(symbols),
        "named_across_function_boundary": cross_n,
        "symbols_if_nearest_parent_only": len(kept),
        "erosion_upstream": _erosion(triples),
        "erosion_nearest_parent_only": _erosion(kept),
    }


def m5_nested(parsed: list[ParsedFile], symbols: tuple[SymbolIR, ...]) -> dict[str, Any]:
    """Compare inclusive (folded) and exclusive cyclomatic for `.tsx` functions."""
    cfg = LANGUAGE_CONFIGS[Language.TSX]
    fn_types = cfg.function_node_types
    exclusive: dict[_Key, int] = {}
    for pf in parsed:
        if pf.module.language is not Language.TSX:
            continue
        for node, _ in _walk(cast("Tree", pf.native_tree).root_node):
            if node.type not in fn_types:
                continue
            count = 1
            stack = list(node.children)
            while stack:
                cur = stack.pop()
                if cur.type in fn_types:
                    continue
                if cur.type in cfg.complexity_node_types or _is_boolean_operation(cur, cfg):
                    count += 1
                stack.extend(cur.children)
            exclusive[_node_key(pf.file, node)] = count
    tsx = [s for s in symbols if s.language is Language.TSX]
    high_inclusive = [s for s in tsx if s.cyc_complexity > HIGH]
    keys = [_sym_key(s) for s in high_inclusive]
    high_only_by_folding = sum(1 for s, k in zip(high_inclusive, keys, strict=True) if exclusive.get(k, s.cyc_complexity) <= HIGH)
    inc = [(s.cyc_complexity, s.cog_complexity, s.sloc) for s in tsx]
    exc = [(exclusive.get(_sym_key(s), s.cyc_complexity), s.cog_complexity, s.sloc) for s in tsx]
    return {
        "tsx_symbols": len(tsx),
        "tsx_high_cc_inclusive": len(high_inclusive),
        "tsx_high_cc_only_by_folding": high_only_by_folding,
        "tsx_erosion_inclusive": _erosion(inc),
        "tsx_erosion_exclusive": _erosion(exc),
        "note": "exclusive keeps the inclusive SLOC; information only, no gate",
    }


def m6_closers(parsed: list[ParsedFile]) -> dict[str, Any]:
    """Share of `.tsx` SLOC that is only `/>` or `>`."""
    sloc = closers = 0
    for pf in parsed:
        if pf.module.language is not Language.TSX:
            continue
        lines = pf.source.splitlines()
        for ln in pf.module.sloc_lines:
            sloc += 1
            if lines[ln - 1].strip() in {"/>", ">"}:
                closers += 1
    return {"tsx_sloc": sloc, "closer_lines": closers, "share": (closers / sloc) if sloc else 0.0}


def _clone_lines(blocks, parsed_by_file) -> dict[Path, set[int]]:  # noqa: ANN001
    out: dict[Path, set[int]] = {}
    for b in blocks:
        sloc = parsed_by_file[b.file].module.sloc_lines
        out.setdefault(b.file, set()).update(ln for ln in range(b.start_line, b.end_line + 1) if ln in sloc)
    return out


def m3_clones(parsed: list[ParsedFile]) -> tuple[dict[str, Any], Mapping[str, list[dict[str, Any]]]]:
    """Clone lines per variant, and V0's `.tsx` lines by candidate kind."""
    by_file = {p.file: p for p in parsed}
    result: dict[str, Any] = {}
    blocks_by_variant = {}
    for variant in VARIANTS:
        blocks = detect_clones(tuple(parsed), clone_filter=variant)
        blocks_by_variant[variant] = blocks
        lines = _clone_lines(blocks, by_file)
        tsx = sum(len(v) for f, v in lines.items() if f.suffix == ".tsx")
        result[variant] = {
            "groups": len({b.group_hash for b in blocks}),
            "clone_sloc_lines": sum(len(v) for v in lines.values()),
            "tsx_clone_sloc_lines": tsx,
        }
    # Share of V0 .tsx clone lines that exist only because of expression-bodied
    # arrow candidates: exactly the lines V1 removes (V1 drops only those candidates).
    v0 = result["upstream"]["tsx_clone_sloc_lines"]
    v1 = result["no-expression-bodies"]["tsx_clone_sloc_lines"]
    result["v0_tsx_clone_lines"] = v0
    result["arrow_only_lines_removed_by_v1"] = v0 - v1
    result["arrow_only_share"] = ((v0 - v1) / v0) if v0 else 0.0
    groups: dict[str, list[dict[str, Any]]] = {v: _group_table(blocks_by_variant[v]) for v in VARIANTS}
    return result, groups


def _group_table(blocks) -> list[dict[str, Any]]:  # noqa: ANN001
    groups: dict[str, list] = {}
    for b in blocks:
        groups.setdefault(b.group_hash, []).append(b)
    return [
        {"hash": h, "instances": [(str(b.file), b.start_line, b.end_line) for b in bs]}
        for h, bs in sorted(groups.items())
    ]


def m4_sample(groups: Mapping[str, list[dict[str, Any]]], repo: Path, sample_dir: Path, seed: int, label: str) -> dict[str, list[str]]:
    """Sample 30 groups per variant; write source to the machine-local dir."""
    sample_dir.mkdir(parents=True, exist_ok=True)
    sampled: dict[str, list[str]] = {}  # keyed by variant name
    texts: dict[str, dict[str, Any]] = {}
    for variant in VARIANTS:
        table = groups[variant]
        rng = random.Random(seed)  # noqa: S311 - sampling, not security
        picked = rng.sample(table, min(30, len(table)))
        sampled[variant] = [g["hash"] for g in picked]
        for g in picked:
            if g["hash"] in texts:
                continue
            insts = []
            for file, start, end in g["instances"][:3]:
                src = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
                insts.append({"at": f"{Path(file).relative_to(repo)}:{start}-{end}", "text": "\n".join(src[start - 1 : min(end, start + 24)])})
            texts[g["hash"]] = {"instances": insts, "total_instances": len(g["instances"])}
    (sample_dir / "groups.json").write_text(json.dumps(texts, indent=1, sort_keys=True))
    with (sample_dir / "labels.todo.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["group_hash", "file:line", "label"])
        for h, info in sorted(texts.items()):
            w.writerow([f"{label}:{h}", info["instances"][0]["at"], ""])
    return sampled


def m7_time(repo: Path, paths: list[str]) -> dict[str, Any]:
    """Wall time and peak RSS of the real CLI under the ts profile."""
    cmd = ["uv", "run", "--project", str(Path(__file__).resolve().parent.parent), "--frozen",
           "scb-check", "check", *paths, "--profile", "ts", "--report"]
    started = time.perf_counter()
    proc = subprocess.run(["/usr/bin/time", "-l", *cmd], cwd=repo, capture_output=True, text=True, check=False)
    wall = time.perf_counter() - started
    rss = next((int(line.split()[0]) for line in proc.stderr.splitlines() if "maximum resident set size" in line), None)
    return {"command": "scb-check check " + " ".join(paths) + " --profile ts", "wall_seconds": wall,
            "peak_rss_bytes": rss, "exit_code": proc.returncode,
            "stderr_tail": [ln for ln in proc.stderr.splitlines() if ln.startswith("skipped")]}


def score_labels(out: dict, labels_path: Path, label_prefix: str) -> None:
    """Add per-variant precision from a filled labels CSV."""
    labels = {}
    with labels_path.open() as fh:
        for row in csv.DictReader(fh):
            labels[row["group_hash"]] = row["label"].strip().lower()
    prec = {}
    for variant, hashes in out["m4_sampled"].items():
        got = [labels.get(f"{label_prefix}:{h}") for h in hashes]
        real = sum(1 for g in got if g == "real")
        judged = sum(1 for g in got if g in {"real", "noise"})
        prec[variant] = {"sampled": len(hashes), "judged": judged, "real": real, "precision": (real / judged) if judged else None}
    out["m4_precision"] = prec


def main(argv: list[str] | None = None) -> int:
    """Run the measure phase, or score labels with --labels."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--paths", nargs="+", required=True)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--sample-dir", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=1233)
    ap.add_argument("--label", default="repo")
    ap.add_argument("--labels", type=Path, help="filled labels CSV; adds precision to --out-json")
    ap.add_argument("--skip-time", action="store_true")
    args = ap.parse_args(argv)
    repo = args.repo.resolve()
    if args.labels:
        out = json.loads(args.out_json.read_text())
        score_labels(out, args.labels, args.label)
        args.out_json.write_text(json.dumps(out, indent=1, sort_keys=True))
        print(json.dumps(out["m4_precision"], indent=1))
        return 0
    files = scan_files(repo, args.paths)
    m1, parsed, times = m1_parse(files)
    config = Config(exclude=(), base_dir=repo)
    result = analyze_paths(tuple(repo / p for p in args.paths), config, profile=PROFILES["ts"], disable_sg=True)
    symbols = result.flags.findings.all_functions
    m3, groups = m3_clones(parsed)
    out = {
        "repo": str(repo), "files_in_scope": len(files), "m1": m1,
        "m2": m2_callables(parsed, symbols), "m3": m3,
        "m4_sampled": m4_sample(groups, repo, args.sample_dir, args.seed, args.label),
        "m5": m5_nested(parsed, symbols), "m6": m6_closers(parsed),
        "m7_slowest_parse": sorted(times.items(), key=lambda kv: -kv[1])[:5],
        "skipped_by_pipeline": [str(p) for p in result.skipped_files],
    }
    if not args.skip_time:
        out["m7"] = m7_time(repo, args.paths)
    out["spike_peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    print(json.dumps({k: out[k] for k in ("files_in_scope", "m1", "m2", "m3", "m5", "m6")}, indent=1, default=str)[:6000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
