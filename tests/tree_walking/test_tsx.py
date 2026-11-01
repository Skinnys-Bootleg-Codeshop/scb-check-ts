from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scb_check.pipeline import analyze_files
from scb_check.tree_walking.artifacts import LanguageParseError
from scb_check.tree_walking.dispatch import ProjectParseError
from scb_check.tree_walking.dispatch import dispatch_parse
from scb_check.tree_walking.dispatch import parse_source_file
from scb_check.tree_walking.languages.typescript import TypeScriptParser
from scb_check.tree_walking.models import Language
from scb_check.tree_walking.models import SymbolIR

_COMPONENT = dedent(
    """
    export const Badge = ({ n }: { n: number }) => {
      if (n > 1) {
        return <b>{n > 2 && <i>x</i>}</b>;
      }
      return <b>0</b>;
    };
    """,
)


def _symbols(source: str, name: str = "sample.tsx") -> dict[str, SymbolIR]:
    module = parse_source_file(Path(name), source).module
    return {symbol.name: symbol for symbol in module.symbols}


def test_tsx_emits_complexity_symbols() -> None:
    """Tsx emits complexity symbols."""
    symbols = _symbols(_COMPONENT)
    assert symbols["Badge"].cyc_complexity == 3
    assert parse_source_file(Path("a.tsx"), _COMPONENT).module.language is Language.TSX


def test_tsx_arrow_component_is_symbol() -> None:
    """Tsx arrow component is symbol."""
    assert "Badge" in _symbols(_COMPONENT)


def test_tsx_hook_callback_folds_into_component() -> None:
    """Tsx hook callback folds into component."""
    source = dedent(
        """
        export function Panel({ xs }: { xs: number[] }) {
          const total = useMemo(() => {
            if (xs.length > 3) {
              return 1;
            }
            return 0;
          }, [xs]);
          return <p>{total}</p>;
        }
        """,
    )
    assert _symbols(source)["Panel"].cyc_complexity == 2


def test_tsx_jsx_conditionals_count() -> None:
    """Tsx jsx conditionals count."""
    source = dedent(
        """
        export function C({ a, b }: { a: boolean; b: boolean }) {
          return <p>{a && <i>x</i>}{b ? <b>y</b> : null}</p>;
        }
        """,
    )
    assert _symbols(source)["C"].cyc_complexity == 3


def test_tsx_jsx_comment_not_sloc() -> None:
    """Tsx jsx comment not sloc."""
    source = "export function C() {\n  return (\n    <p>\n      {/* note */}\n      <i>x</i>\n    </p>\n  );\n}\n"
    module = parse_source_file(Path("c.tsx"), source).module
    assert 4 not in module.sloc_lines


def test_tsx_closer_lines_are_sloc() -> None:
    """Tsx closer lines are sloc."""
    source = 'export function C() {\n  return (\n    <input\n      id="a"\n    />\n  );\n}\n'
    module = parse_source_file(Path("c.tsx"), source).module
    assert 5 in module.sloc_lines


def test_tsx_generic_arrow_parses() -> None:
    """Tsx generic arrow parses."""
    source = "export const id = <T,>(value: T): T => {\n  return value;\n};\n"
    assert "id" in _symbols(source)


def test_ts_grammar_rejects_jsx_tsx_accepts() -> None:
    """Ts grammar rejects jsx tsx accepts."""
    source = "export const a = <div>hello</div>;\n"
    with pytest.raises(LanguageParseError):
        TypeScriptParser().parse(Path("a.ts"), source)
    assert parse_source_file(Path("a.tsx"), source).module.language is Language.TSX


def test_tsx_syntax_error_is_skipped(tmp_path: Path) -> None:
    """Tsx syntax error is skipped."""
    bad = tmp_path / "bad.tsx"
    bad.write_text("export const a = <div>;\nfunction (((\n")
    with pytest.raises(ProjectParseError):
        dispatch_parse(bad, bad.read_text())
    good = tmp_path / "good.tsx"
    good.write_text(_COMPONENT)
    result = analyze_files((bad, good), disable_sg=True)
    assert result.skipped_files == (bad,)
