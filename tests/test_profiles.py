from __future__ import annotations

from pathlib import Path

from scb_check.config import PROFILES
from scb_check.config import Config
from scb_check.config import ScanProfile
from scb_check.pipeline import analyze_paths
from scb_check.walker import walk_source_files

_BODY = "export function f(x: number) {\n  const a = x + 1;\n  return a;\n}\n"

_EXCLUDED = (
    "tests/a.ts",
    "test/a.ts",
    "src/__tests__/a.ts",
    "src/__mocks__/a.ts",
    "e2e/a.ts",
    "playwright/a.ts",
    "fixtures/a.ts",
    "src/__fixtures__/a.ts",
    "app/dash-fixture/a.tsx",
    "app/demo-fixtures/a.tsx",
    "src/a.test.ts",
    "src/a.test.tsx",
    "src/a.spec.ts",
    "src/a.spec.tsx",
    "src/a.stories.ts",
    "src/a.stories.tsx",
    "src/types.d.ts",
    ".next/a.ts",
    ".contentlayer/a.ts",
    "out/a.ts",
    "coverage/a.ts",
    "src/generated/a.ts",
    "src/__generated__/a.ts",
    "src/_generated/a.ts",
    "src/a.generated.ts",
    "src/a.generated.tsx",
    "src/a.gen.ts",
    "src/a.gen.tsx",
)


def _write(root: Path, rel: str, body: str = _BODY) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _config(root: Path) -> Config:
    return Config(exclude=(), base_dir=root)


def _scanned(root: Path, profile: ScanProfile) -> set[str]:
    config = Config(
        exclude=profile.exclude,
        base_dir=root,
        max_file_bytes=profile.max_file_bytes,
    )
    return {
        path.relative_to(root.resolve()).as_posix()
        for path in walk_source_files(root, config)
    }


def test_ts_excludes_each_class(tmp_path: Path) -> None:
    """Ts excludes each class."""
    for rel in _EXCLUDED:
        _write(tmp_path, rel)
    keep = _write(tmp_path, "lib/keep.ts")
    scanned = _scanned(tmp_path, PROFILES["ts"])
    assert scanned == {keep.relative_to(tmp_path).as_posix()}


def test_ts_excludes_keep_app_route_paths(tmp_path: Path) -> None:
    """Ts excludes keep app route paths."""
    _write(tmp_path, "app/(shop)/[sku]/page.tsx")
    assert _scanned(tmp_path, PROFILES["ts"]) == {"app/(shop)/[sku]/page.tsx"}


def test_upstream_profile_excludes_nothing(tmp_path: Path) -> None:
    """Upstream profile excludes nothing."""
    for rel in _EXCLUDED:
        _write(tmp_path, rel)
    assert len(_scanned(tmp_path, PROFILES["upstream"])) == len(_EXCLUDED)


def test_max_file_bytes_skips_large_file(tmp_path: Path) -> None:
    """Max file bytes skips large file."""
    _write(tmp_path, "big.ts", _BODY + "// " + "x" * 2_000_000 + "\n")
    small = _write(tmp_path, "small.ts")
    result = analyze_paths((tmp_path,), _config(tmp_path), profile=PROFILES["ts"], disable_sg=True)
    assert set(result.source_lines_by_file) == {small.resolve()}


def test_explicit_file_obeys_profile_excludes(tmp_path: Path) -> None:
    """A file named on the command line still honours the profile."""
    fixture = _write(tmp_path, "tests/a.tsx")
    keep = _write(tmp_path, "lib/keep.ts")
    big = _write(tmp_path, "lib/big.ts", _BODY + "// " + "x" * 2_000_000 + "\n")
    result = analyze_paths(
        (fixture, keep, big),
        _config(tmp_path),
        profile=PROFILES["ts"],
        disable_sg=True,
    )
    assert set(result.source_lines_by_file) == {keep.resolve()}
