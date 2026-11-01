"""Agent-worked union of clone and ast-grep flags, not computed from the tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.config import PROFILES
from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report

_SAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "hand" / "rules_union.ts"
)


@pytest.mark.integration
def test_rules_union_counts_once() -> None:
    """A line flagged by a clone and by a rule counts once."""
    result = analyze_files((_SAMPLE,), rule_sets=PROFILES["ts"].rule_sets)
    report = compute_report(result.flags).to_dict()
    # SLOC: copyA 4 + copyB 4 + solo 3 = 11
    assert report["total_loc"] == 11
    # copyA and copyB are clones: lines 1-4 and 7-10 = 8 lines
    assert report["clone_loc"] == 8
    # ts-json-clone fires on lines 2, 8 and 14 = 3 lines
    assert report["ast_grep_flagged_loc"] == 3
    # Union: 8 clone lines + line 14 = 9 flagged (a sum would give 11)
    assert report["verbosity_flagged_loc"] == 9
    # verbosity is 9 over 11 SLOC
    assert report["verbosity"] == pytest.approx(0.818181818, abs=1e-9)
    assert report["erosion"] == 0
    assert report["cog_erosion"] == 0
