"""Agent-worked numbers for a TSX sample, not computed from the tool."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from scb_check.pipeline import analyze_files
from scb_check.reporting.score import compute_report

_SAMPLE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "hand" / "hand_sample.tsx"
)


@pytest.mark.integration
def test_hand_sample_tsx() -> None:
    """Agent-worked scores for hand_sample.tsx, default profile, sg disabled."""
    result = analyze_files((_SAMPLE,), disable_sg=True)
    report = compute_report(result.flags).to_dict()
    # SLOC: import 1 + First 9 + Second 9 + Badge 13 + Gate 9 = 41
    assert report["total_loc"] == 41
    # Clones: First and Second, 9 lines each = 18 flagged lines; 18 / 41
    assert report["verbosity_flagged_loc"] == 18
    assert report["verbosity"] == pytest.approx(0.439024390, abs=1e-9)
    # mass_cc = 4*3 + 4*3 + 11*sqrt(13) + 6*3 = 81.661064
    # erosion: high-CC mass 11*sqrt(13) = 39.661064, over mass_cc
    assert report["erosion"] == pytest.approx(0.485679001, abs=1e-9)
    # mass_cog = 3*3 + 3*3 + 10*sqrt(13) + 11*3 = 87.055513
    # cog_erosion: high-cog mass 11*3 = 33, over mass_cog
    assert report["cog_erosion"] == pytest.approx(0.379068470, abs=1e-9)
    assert "tsx" in cast("dict[str, object]", report["syntax_by_language"])
    badge = [
        fn
        for fn in result.flags.findings.all_functions
        if fn.name == "Badge"
    ]
    assert len(badge) == 1
    assert badge[0].cyc_complexity == 11
