"""Agent-worked numbers for a TypeScript sample, not computed from the tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report

_SAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "hand" / "hand_sample.ts"
)


@pytest.mark.integration
def test_hand_sample_ts() -> None:
    """Agent-worked scores for hand_sample.ts."""
    result = analyze_files((_SAMPLE,))
    report = compute_report(result.flags).to_dict()
    # SLOC: grade 13 + sumA 5 + sumB 5 + deep 9 = 32
    assert report["total_loc"] == 32
    # Clones: sumA and sumB, 5 lines each = 10 flagged lines; 10 / 32
    assert report["verbosity_flagged_loc"] == 10
    assert report["verbosity"] == pytest.approx(0.3125, abs=1e-12)
    # mass_cc = 11*sqrt(13) + 2*sqrt(5) + 2*sqrt(5) + 6*sqrt(9) = 66.605336
    # erosion: high-CC mass 11*sqrt(13) = 39.661064, over mass_cc
    assert report["erosion"] == pytest.approx(0.595463764, abs=1e-9)
    # mass_cog = 10*sqrt(13) + sqrt(5) + sqrt(5) + 11*sqrt(9) = 73.527649
    # cog_erosion: high-cog mass 11*sqrt(9) = 33, over mass_cog
    assert report["cog_erosion"] == pytest.approx(0.448810761, abs=1e-9)
