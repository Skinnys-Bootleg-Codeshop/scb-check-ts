"""Pin the behaviour of each profile clone filter on named inputs."""

from __future__ import annotations

from pathlib import Path

import pytest

from scb_check.analysis import clones
from scb_check.config import PROFILES
from scb_check.config import CloneFilter
from scb_check.pipeline import analyze_files

TWO_ARROWS = "xs.map((x) => x.id);\nys.map((y) => y.name);\n"
BLOCK_ARROWS = """\
export const sumA = (xs: number[]) => {
  let total = 0;
  for (const x of xs) { total += x; }
  return total;
};

export const sumB = (ys: number[]) => {
  let sum = 0;
  for (const y of ys) { sum += y; }
  return sum;
};
"""
SETTERS = (
    "const a = <b onClick={() => setA(true)} />;\n"
    "const c = <d onClick={() => setC(true)} />;\n"
)
MARKUP_A = """\
export function A() {
  const x = 1;
  return (
    <div><span><b><i>a</i></b></span><ul><li><b>one</b></li><li><b>two</b></li></ul><p><u>t</u></p></div>
  );
}
"""
MARKUP_B = MARKUP_A.replace("function A", "function B")
LOGIC_A = """\
export function A(xs: number[]) {
  let total = 0;
  for (const x of xs) { total += x; }
  return <b>{total}</b>;
}
"""
LOGIC_B = LOGIC_A.replace("function A", "function B").replace("total", "sum")


def clone_loc(tmp_path: Path, files: dict[str, str], clone_filter: CloneFilter) -> int:
    """Return the clone SLOC count for `files` under `clone_filter`."""
    paths = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text)
        paths.append(path)
    result = analyze_files(tuple(paths), disable_sg=True, clone_filter=clone_filter)
    return sum(len(item.lines) for item in result.flags.lines.clone_sloc_lines_by_file)


def test_upstream_expression_arrows_are_candidates(tmp_path: Path) -> None:
    """Upstream expression arrows are candidates."""
    assert clone_loc(tmp_path, {"a.ts": TWO_ARROWS}, "upstream") == 2


@pytest.mark.parametrize("name", ["a.ts", "a.tsx"])
def test_no_expression_bodies_drops_them(tmp_path: Path, name: str) -> None:
    """No expression bodies drops them."""
    assert clone_loc(tmp_path, {name: TWO_ARROWS}, "no-expression-bodies") == 0


def test_no_expression_bodies_keeps_block_arrows(tmp_path: Path) -> None:
    """No expression bodies keeps block arrows."""
    assert clone_loc(tmp_path, {"a.ts": BLOCK_ARROWS}, "no-expression-bodies") > 0


def test_setter_handlers_not_clones(tmp_path: Path) -> None:
    """Setter handlers not clones."""
    assert clone_loc(tmp_path, {"a.tsx": SETTERS}, "no-expression-bodies") == 0


def test_no_jsx_dominated_equals_v1_at_the_specified_share(tmp_path: Path) -> None:
    """No jsx dominated equals v1 at the specified share."""
    # Pins the finding: counting every node, tokens included, a markup-heavy
    # component reaches about 30% jsx_* nodes, so the 50% cut never fires.
    files = {"a.tsx": MARKUP_A, "b.tsx": MARKUP_B}
    assert clone_loc(tmp_path, files, "no-jsx-dominated") == clone_loc(
        tmp_path, files, "no-expression-bodies"
    )


def test_no_jsx_dominated_drops_markup_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No jsx dominated drops markup components."""
    monkeypatch.setattr(clones, "_JSX_DOMINANCE_SHARE", 0.25)
    files = {"a.tsx": MARKUP_A, "b.tsx": MARKUP_B}
    assert clone_loc(tmp_path, files, "no-expression-bodies") > 0
    assert clone_loc(tmp_path, files, "no-jsx-dominated") == 0


def test_no_jsx_dominated_keeps_logic_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No jsx dominated keeps logic components."""
    monkeypatch.setattr(clones, "_JSX_DOMINANCE_SHARE", 0.25)
    files = {"a.tsx": LOGIC_A, "b.tsx": LOGIC_B}
    assert clone_loc(tmp_path, files, "no-jsx-dominated") > 0


@pytest.mark.parametrize("clone_filter", ["no-expression-bodies", "no-jsx-dominated"])
def test_filter_ignored_for_python(tmp_path: Path, clone_filter: CloneFilter) -> None:
    """Filter ignored for python."""
    body = "def f(a):\n    x = a + 1\n    return x\n"
    files = {"a.py": body, "b.py": body}
    assert clone_loc(tmp_path, files, clone_filter) == clone_loc(tmp_path, files, "upstream")


def test_ts_profile_uses_selected_filter() -> None:
    """Ts profile uses selected filter."""
    # Outcome of gate G-clones in docs/spikes/2026-11-tsx-spike.md: none passed.
    assert PROFILES["ts"].clone_filter == "no-jsx-dominated"
