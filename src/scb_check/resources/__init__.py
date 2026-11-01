"""Load bundled and extra ast-grep rule resources."""

from __future__ import annotations

import os
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import contextmanager
from enum import StrEnum
from importlib import resources
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

import yaml

_RULES_PACKAGE = "scb_check.resources"
_RULES_DIR_NAME = "slop_rules"
_TS_RULES_DIR_NAME = "slop_rules_typescript"
_EXTRA_RULES_ENV = "SCB_CHECK_EXTRA_SLOP_RULES"
_TS_LANGUAGES = frozenset({"typescript", "ts", "tsx"})
type RuleSeverity = Literal["info", "warning", "critical"]
type RuleDocument = dict[str, object]


class RuleSet(StrEnum):
    """Bundled ast-grep rule sets, each run in its own `sg` process."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"


def _rule_file_names() -> tuple[str, ...]:
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    return tuple(
        sorted(
            entry.name
            for entry in rules_dir.iterdir()
            if entry.name.endswith(".yaml")
        ),
    )


def _env_rules() -> tuple[Path, ...]:
    raw_paths = os.environ.get(_EXTRA_RULES_ENV, "")
    if not raw_paths.strip():
        return ()

    paths: list[Path] = []
    for raw_path in raw_paths.split(os.pathsep):
        clean_path = raw_path.strip()
        if not clean_path:
            continue

        path = Path(clean_path).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        paths.append(path)

    return tuple(paths)


def _extra_rules() -> tuple[Path, ...]:
    candidates = _env_rules()

    existing: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        existing.append(resolved)

    return tuple(existing)


def rule_texts(rule_set: RuleSet = RuleSet.PYTHON) -> Iterator[tuple[str, str]]:
    """Yield bundled and environment-provided ast-grep rule text for `rule_set`."""
    if rule_set is RuleSet.TYPESCRIPT:
        yield from _typescript_rule_texts()
        return

    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_RULES_DIR_NAME)
    for name in _rule_file_names():
        yield name, rules_dir.joinpath(name).read_text(encoding="utf-8")

    for path in _extra_rules():
        text = path.read_text(encoding="utf-8")
        try:
            documents = _rule_documents_from_text(text)
        except yaml.YAMLError:
            # Unclassifiable: keep upstream behaviour (sg reports the error).
            yield path.name, text
            continue
        kept = tuple(
            document for document in documents if not _is_typescript_rule(document)
        )
        # TypeScript extras run in their own `sg` process, so a broken one
        # cannot silence the Python rules.
        if len(kept) == len(documents):
            yield path.name, text
        elif kept:
            yield path.name, _dump(kept)


def _is_typescript_rule(document: RuleDocument) -> bool:
    return str(document.get("language", "")).lower() in _TS_LANGUAGES


def _dump(documents: tuple[RuleDocument, ...]) -> str:
    return "".join(
        "---\n" + yaml.safe_dump(document, sort_keys=False) for document in documents
    )


def is_clean_rule_text(text: str) -> bool:
    """Return whether `text` parses as YAML mappings only."""
    try:
        return all(
            isinstance(document, Mapping) or document is None
            for document in yaml.safe_load_all(text)
        )
    except yaml.YAMLError:
        return False


def _typescript_rule_texts() -> Iterator[tuple[str, str]]:
    rules_dir = resources.files(_RULES_PACKAGE).joinpath(_TS_RULES_DIR_NAME)
    if rules_dir.is_dir():
        for name in sorted(
            entry.name for entry in rules_dir.iterdir() if entry.name.endswith(".yaml")
        ):
            text = rules_dir.joinpath(name).read_text(encoding="utf-8")
            if not is_clean_rule_text(text):
                # Verbatim, so ast-grep rejects it and `--strict-sg` exits 2.
                yield name, text
                continue
            rendered = _with_tsx_twins(_rule_documents_from_text(text))
            if rendered:
                yield name, rendered

    for path in _extra_rules():
        try:
            all_documents = _rule_documents_from_text(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        documents = tuple(
            document for document in all_documents if _is_typescript_rule(document)
        )
        rendered = _with_tsx_twins(documents)
        if rendered:
            yield path.name, rendered


def _with_tsx_twins(documents: tuple[RuleDocument, ...]) -> str:
    emitted: list[RuleDocument] = []
    for document in documents:
        emitted.append(document)
        metadata = _rule_document(document.get("metadata")) or {}
        if (
            str(document.get("language", "")).lower() in {"typescript", "ts"}
            and metadata.get("no_tsx_twin") is not True
        ):
            emitted.append({**document, "language": "tsx"})

    return _dump(tuple(emitted))


def find_rule_document(rule_id: str) -> RuleDocument | None:
    """Return the first active ast-grep rule document matching `rule_id`."""
    return next(
        (
            document
            for rule_set in RuleSet
            for _, text in rule_texts(rule_set)
            for document in _rule_documents_from_text(text)
            if document.get("id") == rule_id
        ),
        None,
    )


def load_rule_ids(rules_path: Path) -> frozenset[str]:
    """Load ast-grep rule IDs from `rules_path`."""
    return frozenset(
        rule_id
        for document in _rule_documents(rules_path)
        for rule_id in [document.get("id")]
        if isinstance(rule_id, str)
    )


def load_thresholds(rules_path: Path) -> dict[str, int]:
    """Load per-rule minimum file-count thresholds from `rules_path`."""
    return _load_rule_entries(rules_path, _threshold)


def load_rule_severities(rules_path: Path) -> dict[str, RuleSeverity]:
    """Load ast-grep rule severities from `rules_path`."""
    return _load_rule_entries(rules_path, _severity)


def _load_rule_entries[T](
    rules_path: Path,
    extractor: Callable[[RuleDocument], tuple[str, T] | None],
) -> dict[str, T]:
    return dict(
        entry
        for document in _rule_documents(rules_path)
        if (entry := extractor(document)) is not None
    )


def _rule_documents(rules_path: Path) -> tuple[RuleDocument, ...]:
    with rules_path.open("r", encoding="utf-8") as rules_file:
        return tuple(_normalized_rule_documents(yaml.safe_load_all(rules_file)))


def _rule_documents_from_text(text: str) -> tuple[RuleDocument, ...]:
    return tuple(_normalized_rule_documents(yaml.safe_load_all(text)))


def _normalized_rule_documents(documents: Iterator[object]) -> Iterator[RuleDocument]:
    for document in documents:
        normalized = _rule_document(document)
        if normalized is not None:
            yield normalized


def _rule_document(document: object) -> RuleDocument | None:  # scbc ignore[object-type-annotation]
    # scbc boundary: normalize rule metadata loaded from YAML.
    if not isinstance(document, Mapping):
        return None
    return {
        key: value
        for key, value in document.items()
        if isinstance(key, str)
    }


def _severity(document: RuleDocument) -> tuple[str, RuleSeverity] | None:
    rule_id = document.get("id")
    severity = _rule_severity(document.get("severity"))
    if isinstance(rule_id, str) and severity is not None:
        return (rule_id, severity)
    return None


def _rule_severity(value: object) -> RuleSeverity | None:  # scbc ignore[object-type-annotation]
    match value:
        case "info":
            return "info"
        case "warning":
            return "warning"
        case "critical":
            return "critical"
        case _:
            return None


def _threshold(document: RuleDocument) -> tuple[str, int] | None:
    rule_id = document.get("id")
    metadata = _rule_document(document.get("metadata"))
    if not isinstance(rule_id, str) or metadata is None:
        return None

    min_count = metadata.get("min_file_count")
    if isinstance(min_count, int) and min_count > 1:
        return (rule_id, min_count)
    return None


@contextmanager
def rules_file(rule_set: RuleSet = RuleSet.PYTHON) -> Iterator[Path]:
    """Write all active ast-grep rules of `rule_set` to a temporary YAML file."""
    with NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        for _, text in rule_texts(rule_set):
            tmp.write(text)
            if not text.endswith("\n"):
                tmp.write("\n")
        tmp_path = Path(tmp.name)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)
