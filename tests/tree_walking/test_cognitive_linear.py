from __future__ import annotations

import signal
from collections.abc import Iterator
from pathlib import Path

import pytest

from scb_check.tree_walking.dispatch import parse_source_file


def _ladder(rungs: int) -> str:
    lines = ["export function f(x: number): number {"]
    for index in range(rungs):
        keyword = "if" if index == 0 else "} else if"
        lines.append(f"  {keyword} (x === {index}) {{")
        lines.append(f"    return {index};")
    lines.append("  }")
    lines.append("  return -1;")
    lines.append("}")
    return "\n".join(lines) + "\n"


@pytest.fixture
def alarm() -> Iterator[None]:
    """Fail the test if it runs longer than ten seconds."""
    def _raise(_signum: int, _frame: object) -> None:
        raise TimeoutError("cognitive complexity too slow")

    previous = signal.signal(signal.SIGALRM, _raise)
    signal.alarm(10)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.mark.usefixtures("alarm")
def test_else_if_ladder_60_rungs() -> None:
    """Else if ladder 60 rungs."""
    symbol = next(
        s
        for s in parse_source_file(Path("l.ts"), _ladder(60)).module.symbols
        if s.name == "f"
    )
    # else-if nests: rung k costs 1 + (k - 1) -> sum k = 60 * 61 / 2
    assert symbol.cog_complexity == 1830
    assert symbol.cyc_complexity == 61


def test_cognitive_values_match_upstream_shapes() -> None:
    """Cognitive values match upstream shapes."""
    source = (
        "export function g(a: boolean, b: boolean, xs: number[]) {\n"
        "  if (a && b) {\n"
        "    for (const x of xs) {\n"
        "      if (x) {\n"
        "        continue;\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  return a ? 1 : 2;\n"
        "}\n"
    )
    symbol = next(
        s for s in parse_source_file(Path("g.ts"), source).module.symbols if s.name == "g"
    )
    # if 1 + && 1; for 1+1=2; inner if 1+2=3; continue 1; ternary 1
    assert symbol.cog_complexity == 9
