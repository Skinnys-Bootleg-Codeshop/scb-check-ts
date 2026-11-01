"""Full-run goldens: current code must equal what pristine upstream produced."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _ROOT / "tests" / "fixtures" / "golden"
_EXPECTED = _FIXTURES / "expected"
_SPEC = importlib.util.spec_from_file_location(
    "golden_dump", _ROOT / "scripts" / "golden_dump.py"
)
assert _SPEC is not None
assert _SPEC.loader is not None
_DUMP = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DUMP)

_CASES = {
    "scb_src": (_FIXTURES / "python" / "scb_src", ".py", "python_scb_src"),
    "corpus": (_FIXTURES / "python" / "corpus", ".py", "python_corpus"),
    "ts": (_FIXTURES / "ts", ".ts", "ts"),
}


def _assert_equal(actual: object, expected: object, where: str) -> None:
    if isinstance(expected, float) or isinstance(actual, float):
        assert isinstance(actual, (int, float)), where
        assert isinstance(expected, (int, float)), where
        assert math.isclose(actual, expected, rel_tol=0, abs_tol=1e-12), where
    elif isinstance(expected, dict):
        assert isinstance(actual, dict), where
        assert actual.keys() == expected.keys(), where
        for key, value in expected.items():
            _assert_equal(dict(actual)[key], value, f"{where}.{key}")
    elif isinstance(expected, list):
        assert isinstance(actual, list), where
        assert len(actual) == len(expected), where
        for index, value in enumerate(expected):
            _assert_equal(actual[index], value, f"{where}[{index}]")
    else:
        assert actual == expected, where


def _check(case: str) -> None:
    root, suffix, name = _CASES[case]
    actual = json.loads(json.dumps(_DUMP.dump(root, (suffix,))))
    expected = json.loads((_EXPECTED / f"{name}.json").read_text("utf-8"))
    for key in expected:
        _assert_equal(actual[key], expected[key], key)
    assert actual.keys() == expected.keys()


def test_golden_inputs_present() -> None:
    """Every golden input and expected file exists."""
    for root, suffix, name in _CASES.values():
        assert any(root.rglob(f"*{suffix}")), root
        assert (_EXPECTED / f"{name}.json").is_file(), name
    assert len(list(_CASES["ts"][0].glob("*.ts"))) == 9


@pytest.mark.integration
@pytest.mark.parametrize("case", ["corpus", "scb_src"])
def test_python_golden(case: str) -> None:
    """Python goldens equal pristine output."""
    _check(case)


@pytest.mark.integration
def test_ts_golden() -> None:
    """TypeScript golden equals pristine output."""
    _check("ts")
