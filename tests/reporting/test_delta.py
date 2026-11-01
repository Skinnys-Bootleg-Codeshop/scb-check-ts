"""Pure delta computation and rendering."""

from __future__ import annotations

from scb_check.commands.delta_git import ChangedFile
from scb_check.commands.delta_git import LineMap
from scb_check.models import FunctionMassSummary
from scb_check.models import Report
from scb_check.models import ReportScores
from scb_check.models import VerbositySummary
from scb_check.reporting.delta import DeltaMeta
from scb_check.reporting.delta import ScanSnapshot
from scb_check.reporting.delta import compute_delta
from scb_check.reporting.delta import delta_to_dict
from scb_check.reporting.delta import render_markdown

_NO_LINES = LineMap(frozenset(), frozenset(), ())
_META = DeltaMeta(
    tool_sha="abc1234",
    profile="ts",
    rule_count=36,
    base_ref="origin/main",
    base_sha="a" * 40,
    head_ref="HEAD",
    head_sha="b" * 40,
    paths=("app", "lib"),
)


def _report(sloc: int, flagged: int, *, erosion: float = 0.5) -> Report:
    return Report(
        scores=ReportScores(
            verbosity=flagged / sloc if sloc else 0.0,
            erosion=erosion,
            cog_erosion=0.25,
        ),
        verbosity_summary=VerbositySummary(
            files_scanned=1,
            total_loc=sloc,
            verbosity_flagged_loc=flagged,
            clone_loc=0,
            ast_grep_flagged_loc=flagged,
            structural_rule_loc=0,
            structural_rule_findings=0,
        ),
        function_summary=FunctionMassSummary(0, 0, 0, 0.0, 0.0, 0.0, 0.0),
    )


def _snap(
    flagged: dict[str, dict[int, tuple[str, ...]]],
    *,
    sloc: int = 40,
    text: str = "const a = b as any;",
    skipped: tuple[str, ...] = (),
) -> ScanSnapshot:
    paths = set(flagged) | {"app/x.ts"}
    return ScanSnapshot(
        report=_report(sloc, sum(len(v) for v in flagged.values())),
        flagged=flagged,
        source_lines=dict.fromkeys(paths, (text,) * 30),
        functions=(("app/x.ts", "f", 3, 1, 0),),
        skipped_files=skipped,
    )


def test_compute_new_flagged_lines() -> None:
    """Flagged lines inside the added set are new."""
    base = _snap({})
    head = _snap({"app/x.ts": {12: ("ts-as-any",)}})
    added = LineMap(frozenset({12}), frozenset(), ((11, 0, 12, 1),))
    result = compute_delta(base, head, ((ChangedFile("M", None, "app/x.ts"), added),))
    assert [(i.path, i.line) for i in result.new_lines] == [("app/x.ts", 12)]
    assert not result.newly_flagged
    assert result.cleared == 0


def test_compute_newly_flagged_existing() -> None:
    """An old line flagged only at head, such as a clone partner, is reported."""
    base = _snap({})
    head = _snap({"app/x.ts": {5: ("clone",)}})
    result = compute_delta(base, head, ())
    assert not result.new_lines
    assert [(i.path, i.line) for i in result.newly_flagged] == [("app/x.ts", 5)]


def test_compute_cleared() -> None:
    """Base flagged lines that vanished or were deleted are cleared."""
    base = _snap({"app/x.ts": {3: ("clone",), 4: ("clone",), 9: ("clone",)}})
    head = _snap({"app/x.ts": {7: ("clone",)}})
    # Lines 3-4 deleted; old line 9 is new line 7 and stays flagged.
    change = LineMap(frozenset(), frozenset({3, 4}), ((3, 2, 2, 0),))
    result = compute_delta(base, head, ((ChangedFile("M", None, "app/x.ts"), change),))
    assert result.cleared == 2
    assert not result.new_lines
    assert not result.newly_flagged


def test_render_markdown_table() -> None:
    """The block carries base, head and delta for every metric."""
    base = _snap({}, sloc=40)
    head = _snap({"app/x.ts": {12: ("ts-as-any",)}}, sloc=58)
    added = LineMap(frozenset({12}), frozenset(), ((11, 0, 12, 1),))
    result = compute_delta(base, head, ((ChangedFile("M", None, "app/x.ts"), added),))
    text = render_markdown(result, _META, max_lines=50)
    assert text.startswith("### Slop delta (scb-check abc1234, profile ts, 36 rules)")
    assert "| SLOC | 40 | 58 | +18 |" in text
    assert "| flagged SLOC | 0 | 1 | +1 |" in text
    assert "| cog_erosion | 0.2500 | 0.2500 | 0.0000 |" in text
    assert "New flagged lines: 1. Existing lines newly flagged: 0." in text
    assert "- `app/x.ts:12` ts-as-any: `const a = b as any;`" in text


def test_render_caps_list() -> None:
    """The listing stops at max_lines and says how many it left out."""
    lines: dict[int, tuple[str, ...]] = dict.fromkeys(range(1, 6), ("ts-as-any",))
    head = _snap({"app/x.ts": lines})
    added = LineMap(frozenset(lines), frozenset(), ((0, 0, 1, 5),))
    result = compute_delta(_snap({}), head, ((ChangedFile("M", None, "app/x.ts"), added),))
    text = render_markdown(result, _META, max_lines=2)
    assert text.count("- `app/x.ts:") == 2
    assert "- ... and 3 more" in text


def test_render_escapes_source_text() -> None:
    """Backticks and pipes are escaped, controls dropped, long lines cut."""
    hostile = "a`b|c\x1b[31m\x00" + "z" * 300
    head = _snap({"app/we`ird|.ts": {1: ("ts-as-any",)}}, text=hostile)
    added = LineMap(frozenset({1}), frozenset(), ((0, 0, 1, 1),))
    result = compute_delta(
        _snap({}),
        head,
        ((ChangedFile("A", None, "app/we`ird|.ts"), added),),
    )
    entry = next(
        line
        for line in render_markdown(result, _META, max_lines=5).splitlines()
        if line.startswith("- `app")
    )
    assert "\x1b" not in entry
    assert "\x00" not in entry
    assert "we'ird\\|.ts" in entry
    assert "a'b\\|c[31m" in entry
    assert entry.count("z") == 120 - len("a`b|c[31m")
    assert entry.count("`") == 4  # nothing can close the two code spans early


def test_render_cannot_inject_links() -> None:
    """Backticks in a snippet cannot break out of the code span."""
    attack = "x`[approve](https://evil.example)`<b>"
    head = _snap({"app/x.ts": {1: ("ts-as-any",)}}, text=attack)
    added = LineMap(frozenset({1}), frozenset(), ((0, 0, 1, 1),))
    result = compute_delta(
        _snap({}),
        head,
        ((ChangedFile("A", None, "app/x.ts"), added),),
    )
    entry = next(
        line
        for line in render_markdown(result, _META, max_lines=5).splitlines()
        if line.startswith("- `app")
    )
    assert entry.count("`") == 4
    assert entry.endswith("`")


def test_delta_to_dict_stable_keys() -> None:
    """The JSON form keeps its documented keys."""
    result = compute_delta(_snap({}), _snap({}), ())
    payload = delta_to_dict(result, _META)
    assert sorted(payload) == [
        "base",
        "changed_functions",
        "cleared",
        "comparable",
        "delta",
        "head",
        "incomparable",
        "meta",
        "new_flagged",
        "newly_flagged_existing",
        "skipped_files",
    ]
    assert payload["comparable"] is True
    assert payload["delta"] == {
        "verbosity": 0.0,
        "erosion": 0.0,
        "cog_erosion": 0.0,
        "sloc": 0,
        "flagged_sloc": 0,
        "clone_loc": 0,
    }


def test_zero_sloc_renders_na() -> None:
    """A side with no SLOC shows n/a rather than a misleading zero."""
    empty = ScanSnapshot(_report(0, 0), {}, {}, (), ())
    result = compute_delta(empty, _snap({}), ())
    text = render_markdown(result, _META, max_lines=5)
    assert "| SLOC | n/a | 40 | n/a |" in text
    both = render_markdown(compute_delta(empty, empty, ()), _META, max_lines=5)
    assert "no scanned source on either side" in both
