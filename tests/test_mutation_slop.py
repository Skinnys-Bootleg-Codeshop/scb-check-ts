"""Mutation test: adding known slop raises verbosity step by step, undoing lowers it."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from scb_check.config import PROFILES
from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report

_CLEAN = Path(__file__).resolve().parent / "fixtures" / "mutation" / "clean_orders.ts"

_M2_OLD = "  return orders.filter(isOpen).map(toId);\n"
_M2_NEW = (
    "  const ids: string[] = [];\n"
    "  for (const order of orders) {\n"
    "    ids.push(order.id);\n"
    "  }\n"
    "  return ids;\n"
)
_M3_OLD = "    reportError(error);\n"
_M3_NEW = (
    "    const message = error instanceof Error ? error.message : String(error);\n"
    "    reportError(message);\n"
)
_M4_OLD = "  return orders.reduce((sum, order) => sum + order.total, 0);\n"
_M4_NEW = (
    "  const copy = JSON.parse(JSON.stringify(orders));\n"
    "  return copy.reduce((sum, order) => sum + order.total, 0);\n"
)
_M5_TAIL = """
export function tallyA(xs: number[]): number {
  let total = 0;
  for (const x of xs) {
    total += x;
  }
  return total;
}

export function tallyB(ys: number[]): number {
  let sum = 0;
  for (const y of ys) {
    sum += y;
  }
  return sum;
}
"""

# (step, flagged SLOC, total SLOC, verbosity), agent-worked, independent of the tool's output.
_TABLE = (
    ("clean", 0, 15, 0.0),
    ("M1", 1, 15, 1 / 15),
    ("M2", 3, 18, 3 / 18),
    ("M3", 4, 19, 4 / 19),
    ("M4", 5, 20, 5 / 20),
    ("M5", 15, 30, 15 / 30),
)


def _mutations(text: str) -> list[str]:
    """Return the file text after each cumulative mutation, clean first."""
    steps = [text]
    steps.append(steps[-1].replace("as Order;", "as any;"))
    steps.append(steps[-1].replace(_M2_OLD, _M2_NEW))
    steps.append(steps[-1].replace(_M3_OLD, _M3_NEW))
    steps.append(steps[-1].replace(_M4_OLD, _M4_NEW))
    steps.append(steps[-1] + _M5_TAIL)
    for before, after in pairwise(steps):
        assert before != after, "a mutation did not apply"
    return steps


def _score(tmp_path: Path, text: str, name: str) -> dict[str, Any]:
    target = tmp_path / f"{name}.ts"
    target.write_text(text)
    result = analyze_files(
        (target,),
        clone_filter=PROFILES["ts"].clone_filter,
        rule_sets=PROFILES["ts"].rule_sets,
        strict_sg=True,
    )
    return compute_report(result.flags).to_dict()


@pytest.mark.integration
def test_clean_file_has_no_flags(tmp_path: Path) -> None:
    """The clean file has 15 SLOC and nothing flagged."""
    report = _score(tmp_path, _CLEAN.read_text(), "clean")
    assert report["total_loc"] == 15
    assert report["verbosity_flagged_loc"] == 0
    assert report["verbosity"] == 0


@pytest.mark.integration
def test_each_mutation_raises_verbosity(tmp_path: Path) -> None:
    """Flagged SLOC goes 0, 1, 3, 4, 5, 15 and verbosity rises strictly."""
    steps = _mutations(_CLEAN.read_text())
    previous = -1.0
    for (label, flagged, sloc, verbosity), text in zip(_TABLE, steps, strict=True):
        report = _score(tmp_path, text, label)
        assert report["total_loc"] == sloc, label
        assert report["verbosity_flagged_loc"] == flagged, label
        assert report["verbosity"] == pytest.approx(verbosity, abs=1e-9), label
        assert report["verbosity"] > previous, label
        previous = report["verbosity"]


@pytest.mark.integration
def test_undoing_each_mutation_lowers_verbosity(tmp_path: Path) -> None:
    """Walking the steps back lowers verbosity strictly, ending at 0."""
    steps = _mutations(_CLEAN.read_text())
    scores = [_score(tmp_path, text, f"undo{i}")["verbosity"] for i, text in enumerate(reversed(steps))]
    for earlier, later in pairwise(scores):
        assert later < earlier
    assert scores[-1] == 0
