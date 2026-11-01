"""Coordinate file walking, analysis, filtering, and flag building."""

from __future__ import annotations

from collections import Counter
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace
from pathlib import Path

import yaml
from tree_sitter import Tree

from scb_check.analysis.astgrep import run_sg
from scb_check.analysis.astgrep import run_sg_strict
from scb_check.analysis.clones import detect_clones_with_skips
from scb_check.config import PROFILES
from scb_check.config import CloneFilter
from scb_check.config import Config
from scb_check.config import ScanProfile
from scb_check.logging import get_logger
from scb_check.models import AstGrepHit
from scb_check.models import CloneBlock
from scb_check.models import FileLineSet
from scb_check.models import FindingGroups
from scb_check.models import Flags
from scb_check.models import LanguageSyntaxSummary
from scb_check.models import LineGroups
from scb_check.resources import RuleSet
from scb_check.resources import RuleSeverity
from scb_check.resources import load_rule_severities
from scb_check.resources import load_thresholds
from scb_check.resources import rules_file
from scb_check.rules.registry import structural_rule_ids
from scb_check.rules.runner import run_rules
from scb_check.rules.settings import LowUseShortFunctionSettings
from scb_check.tree_walking.directives import BoundaryDirective
from scb_check.tree_walking.directives import IgnoreDirective
from scb_check.tree_walking.directives import IgnoreDirectiveError
from scb_check.tree_walking.directives import load_ast_grep_rule_ids
from scb_check.tree_walking.directives import parse_boundary_directives
from scb_check.tree_walking.directives import parse_ignore_directives
from scb_check.tree_walking.dispatch import ParsedFile
from scb_check.tree_walking.dispatch import ProjectParseError
from scb_check.tree_walking.dispatch import (
    parse_source_file as dispatch_parse_source_file,
)
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import RuleFinding
from scb_check.tree_walking.models import SymbolIR
from scb_check.tree_walking.models import SymbolKind
from scb_check.tree_walking.semantic import build_project
from scb_check.walker import is_scannable
from scb_check.walker import walk_source_files

logger = get_logger(__name__)

_RULE_SET_LANGUAGES = {
    RuleSet.PYTHON: (Language.PYTHON,),
    RuleSet.TYPESCRIPT: (Language.TYPESCRIPT, Language.TSX),
}

__all__ = [
    "AnalysisResult",
    "IgnoreDirectiveError",
    "analyze",
    "analyze_files",
    "analyze_paths",
]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Complete analysis output for CLI reporting."""

    flags: Flags
    source_lines_by_file: dict[Path, tuple[str, ...]]
    skipped_files: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class ParsedSources:
    """Parsed files and source indexes collected from input paths."""

    parsed_files: tuple[ParsedFile, ...]
    total_loc_by_file: tuple[tuple[Path, int], ...]
    sloc_lines_by_file: dict[Path, frozenset[int]]
    source_by_file: dict[Path, str]
    source_lines_by_file: dict[Path, tuple[str, ...]]
    language_by_file: dict[Path, Language]
    syntax_by_language: tuple[LanguageSyntaxSummary, ...]
    skipped_files: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class Findings:
    """Collected findings before sorting and line-set projection."""

    clones: tuple[CloneBlock, ...]
    ast_hits: tuple[AstGrepHit, ...]
    structural_findings: tuple[RuleFinding, ...]
    functions: tuple[SymbolIR, ...]
    total_loc_by_file: tuple[tuple[Path, int], ...]
    sloc_lines_by_file: dict[Path, frozenset[int]]
    source_lines_by_file: dict[Path, tuple[str, ...]]
    syntax_by_language: tuple[LanguageSyntaxSummary, ...]
    skipped_files: tuple[Path, ...] = ()


def analyze(
    path: Path,
    config: Config,
    *,
    include_all: bool = False,
    disable_sg: bool = False,
) -> AnalysisResult:
    """Analyze supported source files under `path` using `config`."""
    files = tuple(sorted(walk_source_files(path, config, include_ignored=include_all)))
    if not files:
        raise FileNotFoundError(f"no supported source files found at {path}")
    return analyze_files(
        files,
        include_all=include_all,
        disable_sg=disable_sg,
        low_use_short_function=config.low_use_short_function,
    )


def analyze_paths(  # noqa: PLR0913
    paths: tuple[Path, ...],
    config: Config,
    *,
    profile: ScanProfile = PROFILES["upstream"],
    include_all: bool = False,
    disable_sg: bool = False,
    strict_sg: bool = False,
) -> AnalysisResult:
    """Analyze the union of supported files under `paths` using `profile`."""
    scan_config = replace(
        config,
        exclude=(*config.exclude, *profile.exclude),
        max_file_bytes=profile.max_file_bytes,
    )
    files = tuple(
        sorted(
            {
                file
                for path in paths
                for file in walk_source_files(
                    path,
                    scan_config,
                    include_ignored=include_all,
                )
                if is_scannable(file, scan_config)
            },
        ),
    )
    if not files:
        joined = ", ".join(str(path) for path in paths)
        raise FileNotFoundError(f"no supported source files found at {joined}")
    return analyze_files(
        files,
        include_all=include_all,
        disable_sg=disable_sg,
        low_use_short_function=config.low_use_short_function,
        clone_filter=profile.clone_filter,
        rule_sets=profile.rule_sets,
        strict_sg=strict_sg,
    )


def analyze_files(  # noqa: PLR0913
    files: tuple[Path, ...],
    *,
    include_all: bool = False,
    disable_sg: bool = False,
    low_use_short_function: LowUseShortFunctionSettings | None = None,
    clone_filter: CloneFilter = "upstream",
    rule_sets: tuple[RuleSet, ...] = (RuleSet.PYTHON,),
    strict_sg: bool = False,
) -> AnalysisResult:
    """Analyze an explicit tuple of supported source `files`."""
    findings = _collect_findings(
        files,
        include_all=include_all,
        disable_sg=disable_sg,
        low_use_short_function=(
            low_use_short_function or LowUseShortFunctionSettings()
        ),
        clone_filter=clone_filter,
        rule_sets=rule_sets,
        strict_sg=strict_sg,
    )
    flags = _build_flags(findings)
    return AnalysisResult(
        flags=flags,
        source_lines_by_file=findings.source_lines_by_file,
        skipped_files=findings.skipped_files,
    )


def _collect_findings(  # noqa: PLR0913
    files: tuple[Path, ...],
    *,
    include_all: bool,
    disable_sg: bool,
    low_use_short_function: LowUseShortFunctionSettings,
    clone_filter: CloneFilter,
    rule_sets: tuple[RuleSet, ...],
    strict_sg: bool,
) -> Findings:
    sources = _parse_sources(files)
    clones, overflowed = detect_clones_with_skips(
        sources.parsed_files,
        clone_filter=clone_filter,
    )
    if overflowed:
        sources = _parse_sources(tuple(f for f in files if f not in overflowed))
        clones, _ = detect_clones_with_skips(
            sources.parsed_files,
            clone_filter=clone_filter,
        )
    skipped_files = tuple(sorted({*sources.skipped_files, *overflowed}))
    project = build_project(tuple(parsed.module for parsed in sources.parsed_files))
    functions = _function_symbols(tuple(project.symbols_by_qualified_name.values()))
    structural_findings = run_rules(
        project,
        low_use_short_function=low_use_short_function,
    )
    ast_hits, filtered_structural_findings = _run_and_filter_rules(
        sources,
        functions,
        structural_findings,
        include_all=include_all,
        disable_sg=disable_sg,
        rule_sets=rule_sets,
        strict_sg=strict_sg,
    )
    return Findings(
        clones=clones,
        ast_hits=ast_hits,
        structural_findings=filtered_structural_findings,
        functions=functions,
        total_loc_by_file=sources.total_loc_by_file,
        sloc_lines_by_file=sources.sloc_lines_by_file,
        source_lines_by_file=sources.source_lines_by_file,
        syntax_by_language=sources.syntax_by_language,
        skipped_files=skipped_files,
    )


def _parse_sources(files: tuple[Path, ...]) -> ParsedSources:
    parsed_files: list[ParsedFile] = []
    total_loc_by_file: list[tuple[Path, int]] = []
    sloc_lines_by_file: dict[Path, frozenset[int]] = {}
    source_by_file: dict[Path, str] = {}
    source_lines_by_file: dict[Path, tuple[str, ...]] = {}
    language_by_file: dict[Path, Language] = {}
    skipped_files: list[Path] = []
    tree_counts: Counter[Language] = Counter()
    node_counts: Counter[Language] = Counter()

    for file_path in files:
        if (parsed_source := _parse_source_file(file_path)) is None:
            skipped_files.append(file_path)
            continue
        source, parsed = parsed_source
        language = parsed.module.language
        parsed_files.append(parsed)
        source_by_file[file_path] = source
        source_lines_by_file[file_path] = tuple(source.splitlines())
        sloc_lines_by_file[file_path] = parsed.module.sloc_lines
        language_by_file[file_path] = language
        total_loc_by_file.append((file_path, len(parsed.module.sloc_lines)))
        if isinstance(parsed.native_tree, Tree):
            tree_counts[language] += 1
            node_counts[language] += _count_tree_nodes(parsed.native_tree)

    return ParsedSources(
        parsed_files=tuple(parsed_files),
        total_loc_by_file=tuple(total_loc_by_file),
        sloc_lines_by_file=sloc_lines_by_file,
        source_by_file=source_by_file,
        source_lines_by_file=source_lines_by_file,
        language_by_file=language_by_file,
        syntax_by_language=_syntax_summaries(tree_counts, node_counts),
        skipped_files=tuple(skipped_files),
    )


def _syntax_summaries(
    tree_counts: Counter[Language],
    node_counts: Counter[Language],
) -> tuple[LanguageSyntaxSummary, ...]:
    return tuple(
        LanguageSyntaxSummary(
            language=language,
            tree_count=tree_counts[language],
            node_count=node_counts[language],
        )
        for language in sorted(tree_counts, key=lambda item: item.value)
    )


def _count_tree_nodes(tree: Tree) -> int:
    count = 0
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        count += 1
        stack.extend(node.children)
    return count


def _parse_source_file(file_path: Path) -> tuple[str, ParsedFile] | None:
    try:
        source = _read_source(file_path)
        return (source, dispatch_parse_source_file(file_path, source))
    except ProjectParseError as exc:
        logger.warning(
            "failed to parse file",
            file=str(file_path),
            error=str(exc),
        )
        return None
    except RecursionError:
        logger.warning(
            "file overflowed recursion while parsing, skipping",
            file=str(file_path),
        )
        return None


def _run_and_filter_rules(  # noqa: PLR0913
    sources: ParsedSources,
    functions: tuple[SymbolIR, ...],
    structural_findings: tuple[RuleFinding, ...],
    *,
    include_all: bool,
    disable_sg: bool,
    rule_sets: tuple[RuleSet, ...],
    strict_sg: bool,
) -> tuple[tuple[AstGrepHit, ...], tuple[RuleFinding, ...]]:
    with rules_file() as rules_path:
        ast_hits, thresholds = _run_ast_grep(
            sources,
            rules_path,
            disable_sg=disable_sg,
            strict_sg=strict_sg,
        )
        extra_hits, extra_thresholds = _run_extra_rule_sets(
            sources,
            rule_sets,
            disable_sg=disable_sg,
            strict_sg=strict_sg,
        )
        if extra_hits:
            ast_hits = _sorted_ast_hits((*ast_hits, *extra_hits))
        thresholds = {**thresholds, **extra_thresholds}
        if include_all:
            return ast_hits, structural_findings

        python_source_by_file = _source_by_language(sources, Language.PYTHON)
        ignore_directives = parse_ignore_directives(
            python_source_by_file,
            valid_rule_ids=_valid_rule_ids(rules_path),
        )
        boundary_ranges = _boundary_function_ranges(
            parse_boundary_directives(python_source_by_file),
            functions,
        )
        return (
            _filter_ast_hits(
                ast_hits,
                ignore_directives,
                boundary_ranges,
                thresholds,
            ),
            _filter_ignored_items(
                structural_findings,
                ignore_directives,
                lambda finding: (
                    finding.file,
                    finding.start_line,
                    finding.rule_id,
                ),
            ),
        )


def _run_ast_grep(
    sources: ParsedSources,
    rules_path: Path,
    *,
    disable_sg: bool,
    strict_sg: bool = False,
) -> tuple[tuple[AstGrepHit, ...], dict[str, int]]:
    python_files = _files_by_language(sources, Language.PYTHON)
    if disable_sg or not python_files:
        return (), {}

    thresholds = load_thresholds(rules_path)
    rule_severities = load_rule_severities(rules_path)
    runner = run_sg_strict if strict_sg else run_sg
    ast_hits = _with_ast_hit_severities(
        runner(python_files, rules_path),
        rule_severities,
    )
    return ast_hits, thresholds


def _run_extra_rule_sets(
    sources: ParsedSources,
    rule_sets: tuple[RuleSet, ...],
    *,
    disable_sg: bool,
    strict_sg: bool,
) -> tuple[tuple[AstGrepHit, ...], dict[str, int]]:
    """Run each non-Python rule set in its own `sg` process."""
    hits: tuple[AstGrepHit, ...] = ()
    thresholds: dict[str, int] = {}
    for rule_set in rule_sets:
        if rule_set is RuleSet.PYTHON or disable_sg:
            continue

        languages = _RULE_SET_LANGUAGES[rule_set]
        files = tuple(
            file_path
            for file_path in sources.source_lines_by_file
            if sources.language_by_file.get(file_path) in languages
        )
        if not files:
            continue

        with rules_file(rule_set) as rules_path:
            if rules_path.stat().st_size == 0:
                continue

            runner = run_sg_strict if strict_sg else run_sg
            raw_hits = runner(files, rules_path)
            try:
                severities = load_rule_severities(rules_path)
                set_thresholds = load_thresholds(rules_path)
            except yaml.YAMLError:
                # Malformed rule text: sg already failed (and warned, or raised
                # under strict mode), so there are no hits to classify.
                continue
            hits = (*hits, *_with_ast_hit_severities(raw_hits, severities))
            thresholds.update(set_thresholds)

    return hits, thresholds


def _sorted_ast_hits(hits: tuple[AstGrepHit, ...]) -> tuple[AstGrepHit, ...]:
    return tuple(
        sorted(
            hits,
            key=lambda hit: (hit.file.as_posix(), hit.line, hit.col, hit.rule_id),
        ),
    )


def _files_by_language(
    sources: ParsedSources,
    language: Language,
) -> tuple[Path, ...]:
    return tuple(
        file_path
        for file_path in sources.source_lines_by_file
        if sources.language_by_file.get(file_path) is language
    )


def _source_by_language(
    sources: ParsedSources,
    language: Language,
) -> dict[Path, str]:
    return {
        file_path: source
        for file_path, source in sources.source_by_file.items()
        if sources.language_by_file.get(file_path) is language
    }


def _filter_ast_hits(
    ast_hits: tuple[AstGrepHit, ...],
    ignore_directives: tuple[IgnoreDirective, ...],
    boundary_ranges: tuple[tuple[Path, int, int], ...],
    thresholds: dict[str, int],
) -> tuple[AstGrepHit, ...]:
    filtered = _filter_info_ast_hits(ast_hits)
    filtered = _filter_ignored_items(
        filtered,
        ignore_directives,
        lambda hit: (hit.file, hit.line, hit.rule_id),
    )
    filtered = _filter_boundary_ast_hits(filtered, boundary_ranges)
    return _apply_count_thresholds(filtered, thresholds)


def _read_source(file_path: Path) -> str:
    try:
        return file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "file is not valid UTF-8, reading with replacement characters",
            file=str(file_path),
        )
        return file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ProjectParseError(
            f"failed to read source file: `{file_path}`",
            file_path=file_path,
        ) from exc


def _valid_rule_ids(rules_path: Path) -> frozenset[str]:
    ast_rule_ids = load_ast_grep_rule_ids(rules_path)
    structural_ids = structural_rule_ids()
    duplicate_ids = ast_rule_ids & structural_ids
    if duplicate_ids:
        duplicate = min(duplicate_ids)
        raise IgnoreDirectiveError(f"duplicate rule id: {duplicate}")
    return ast_rule_ids | structural_ids


def _function_symbols(symbols: tuple[SymbolIR, ...]) -> tuple[SymbolIR, ...]:
    return tuple(
        symbol
        for symbol in symbols
        if symbol.kind in {SymbolKind.FUNCTION, SymbolKind.METHOD}
    )


def _boundary_function_ranges(
    directives: tuple[BoundaryDirective, ...],
    functions: tuple[SymbolIR, ...],
) -> tuple[tuple[Path, int, int], ...]:
    ranges: list[tuple[Path, int, int]] = []
    errors: list[str] = []
    for directive in directives:
        function = _containing_function(directive, functions)
        if function is None:
            errors.append(
                f"{directive.file.as_posix()}:{directive.directive_line}: "
                "scbc boundary must be inside a function body",
            )
            continue
        ranges.append((function.file, function.start_line, function.end_line))

    if errors:
        raise IgnoreDirectiveError("\n".join(errors))
    return tuple(ranges)


def _containing_function(
    directive: BoundaryDirective,
    functions: tuple[SymbolIR, ...],
) -> SymbolIR | None:
    containing = tuple(
        function
        for function in functions
        if function.file == directive.file
        and function.start_line < directive.directive_line <= function.end_line
    )
    return (
        min(containing, key=lambda function: function.end_line)
        if containing
        else None
    )


def _with_ast_hit_severities(
    ast_hits: tuple[AstGrepHit, ...],
    rule_severities: dict[str, RuleSeverity],
) -> tuple[AstGrepHit, ...]:
    return tuple(
        replace(hit, severity=rule_severities.get(hit.rule_id, hit.severity))
        for hit in ast_hits
    )


def _filter_info_ast_hits(
    ast_hits: tuple[AstGrepHit, ...],
) -> tuple[AstGrepHit, ...]:
    return tuple(hit for hit in ast_hits if hit.severity != "info")


def _filter_boundary_ast_hits(
    ast_hits: tuple[AstGrepHit, ...],
    boundary_ranges: tuple[tuple[Path, int, int], ...],
) -> tuple[AstGrepHit, ...]:
    return tuple(
        hit
        for hit in ast_hits
        if not any(
            hit.file == path and start_line <= hit.line <= end_line
            for path, start_line, end_line in boundary_ranges
        )
    )


def _apply_count_thresholds(
    ast_hits: tuple[AstGrepHit, ...],
    thresholds: dict[str, int],
) -> tuple[AstGrepHit, ...]:
    if not thresholds:
        return ast_hits

    counts = Counter(
        (hit.rule_id, hit.file) for hit in ast_hits if hit.rule_id in thresholds
    )

    return tuple(
        hit
        for hit in ast_hits
        if hit.rule_id not in thresholds
        or counts[(hit.rule_id, hit.file)] >= thresholds[hit.rule_id]
    )


def _filter_ignored_items[T](
    items: tuple[T, ...],
    ignore_directives: tuple[IgnoreDirective, ...],
    key: Callable[[T], tuple[Path, int, str]],
) -> tuple[T, ...]:
    ignored = _ignored_rule_keys(ignore_directives)
    return tuple(item for item in items if key(item) not in ignored)


def _ignored_rule_keys(
    ignore_directives: tuple[IgnoreDirective, ...],
) -> frozenset[tuple[Path, int, str]]:
    return frozenset(
        (directive.file, directive.target_line, rule_id)
        for directive in ignore_directives
        for rule_id in directive.rule_ids
    )


def _build_flags(findings: Findings) -> Flags:
    sorted_clones = sorted(
        findings.clones,
        key=lambda clone: (
            clone.file.as_posix(),
            clone.start_line,
            clone.end_line,
        ),
    )
    sorted_ast_hits = sorted(
        findings.ast_hits,
        key=lambda hit: (
            hit.file.as_posix(),
            hit.line,
            hit.col,
            hit.rule_id,
        ),
    )
    sorted_structural_findings = sorted(
        findings.structural_findings,
        key=lambda finding: (
            finding.file.as_posix(),
            finding.start_line,
            finding.span.start_col,
            finding.rule_id,
            finding.subject_name,
        ),
    )
    sorted_functions = sorted(
        findings.functions,
        key=lambda symbol: (
            symbol.file.as_posix(),
            symbol.start_line,
            symbol.name,
        ),
    )
    high_cc = [symbol for symbol in sorted_functions if symbol.is_high_cc()]
    high_cog = [symbol for symbol in sorted_functions if symbol.is_high_cog()]

    clone_sloc_lines = _collect_sloc_lines(
        sorted_clones,
        findings.sloc_lines_by_file,
        lambda clone: (clone.file, clone.start_line, clone.end_line),
    )
    ast_sloc_lines = _collect_sloc_lines(
        sorted_ast_hits,
        findings.sloc_lines_by_file,
        lambda hit: (hit.file, hit.line, hit.end_line),
    )
    structural_sloc_lines = _collect_sloc_lines(
        sorted_structural_findings,
        findings.sloc_lines_by_file,
        lambda finding: (finding.file, finding.start_line, finding.end_line),
    )

    return Flags(
        findings=FindingGroups(
            clones=tuple(sorted_clones),
            ast_grep_hits=tuple(sorted_ast_hits),
            structural_findings=tuple(sorted_structural_findings),
            high_cc_functions=tuple(high_cc),
            high_cog_functions=tuple(high_cog),
            all_functions=tuple(sorted_functions),
        ),
        syntax_by_language=findings.syntax_by_language,
        lines=LineGroups(
            total_loc_by_file=tuple(
                sorted(
                    findings.total_loc_by_file,
                    key=lambda item: item[0].as_posix(),
                ),
            ),
            clone_sloc_lines_by_file=tuple(clone_sloc_lines),
            ast_sloc_lines_by_file=tuple(ast_sloc_lines),
            structural_sloc_lines_by_file=tuple(structural_sloc_lines),
        ),
    )


def _collect_sloc_lines[T](
    items: list[T],
    sloc_lines_by_file: dict[Path, frozenset[int]],
    span: Callable[[T], tuple[Path, int, int]],
) -> list[FileLineSet]:
    lines_by_file: defaultdict[Path, set[int]] = defaultdict(set)

    for item in items:
        path, start, end = span(item)
        sloc_lines = sloc_lines_by_file.get(path, frozenset())
        lines_by_file[path].update(
            line for line in range(start, end + 1) if line in sloc_lines
        )

    return [
        FileLineSet(path, frozenset(lines))
        for path, lines in sorted(
            lines_by_file.items(),
            key=lambda item: item[0].as_posix(),
        )
    ]
