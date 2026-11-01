"""The calibration script applies its thresholds without re-tightening, on synthetic data."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

_SPEC = importlib.util.spec_from_file_location(
    "calibrate_rules",
    Path(__file__).resolve().parents[1] / "scripts" / "calibrate_rules.py",
)
assert _SPEC is not None
assert _SPEC.loader is not None
cal = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cal)


def _stats(hits: int) -> dict:
    rule = {
        "hits": hits,
        "file_hit_rate": 0.05,
        "line_share": 0.05,
        "flagged_sloc": hits,
        "mean_span": 1.0,
    }
    return {"a": {"per_rule": {"ts-x": rule}}}


def _labels(path: Path, rows: list[tuple[str, str]]) -> Path:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rule", "label", "seed"])
        w.writerows([("ts-x", label, seed) for seed, label in rows])
    return path


def test_mid_precision_is_tighten_first_time(tmp_path: Path) -> None:
    """60% on the first sample sends an untightened rule to tighten."""
    rows = [("1233", "tp")] * 6 + [("1233", "fp")] * 4
    out = cal.decide(_stats(10), _labels(tmp_path / "l.csv", rows), {"ts-x"})
    assert out["ts-x"]["decision"] == "tighten"


def test_already_tightened_rule_is_pruned_not_tightened_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rule already tightened once is pruned when its resample is under 70%."""
    monkeypatch.setattr(cal, "ALREADY_TIGHTENED", frozenset({"ts-x"}))
    rows = (
        [("1233", "tp")] * 6
        + [("1233", "fp")] * 4
        + [("1234", "tp")] * 4
        + [("1234", "fp")] * 2
    )
    out = cal.decide(_stats(10), _labels(tmp_path / "l.csv", rows), {"ts-x"})
    assert out["ts-x"]["decision"] == "prune"


def test_already_tightened_rule_is_kept_on_good_resample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resample precision at 70% keeps it, and seeds are not pooled."""
    monkeypatch.setattr(cal, "ALREADY_TIGHTENED", frozenset({"ts-x"}))
    rows = (
        [("1233", "tp")] * 6
        + [("1233", "fp")] * 4
        + [("1234", "tp")] * 7
        + [("1234", "fp")] * 3
    )
    out = cal.decide(_stats(10), _labels(tmp_path / "l.csv", rows), {"ts-x"})
    assert out["ts-x"]["decision"] == "keep"


def test_todo_sheet_carries_the_seed(tmp_path: Path) -> None:
    """Every sampled row is written with its seed, so resample sheets are not read as seed 1233."""
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "a.ts").write_text("x\ny\nz\n")
    sheet = tmp_path / "t.csv"
    cal.write_todo(
        [("ts-x", "r", "a.ts", 2)], {"r": repo}, {"ts-x": "m"}, sheet, 1234
    )
    row = next(csv.DictReader(sheet.open()))
    assert row["seed"] == "1234"

