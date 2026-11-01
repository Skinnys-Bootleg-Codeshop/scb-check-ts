"""The scoring formulas are frozen to upstream."""

from __future__ import annotations

import hashlib
import inspect
import textwrap
from pathlib import Path

from scb_check.reporting import score
from scb_check.tree_walking import models
from scb_check.tree_walking.models import SymbolIR

_SCORE_SHA256 = (
    "8e2a1b6fffa928ac55ff4e644273411594e25852b01736592980c69691560fe1"
)

_UPSTREAM_METHODS = {
    "cc_mass": '''
def cc_mass(self) -> float:
    """Return the cyclomatic complexity mass."""
    return self.cyc_complexity * math.sqrt(self.sloc)
''',
    "cog_mass": '''
def cog_mass(self) -> float:
    """Return the cognitive complexity mass."""
    return self.cog_complexity * math.sqrt(self.sloc)
''',
    "is_high_cc": '''
def is_high_cc(self) -> bool:
    """Return True if the symbol exceeds the cyclomatic cutoff."""
    return self.cyc_complexity > HIGH_COMPLEXITY_THRESHOLD
''',
    "is_high_cog": '''
def is_high_cog(self) -> bool:
    """Return True if the symbol exceeds the cognitive cutoff."""
    return self.cog_complexity > HIGH_COMPLEXITY_THRESHOLD
''',
}


def test_score_py_hash() -> None:
    """score.py is byte-identical to upstream."""
    data = Path(score.__file__).read_bytes()
    assert hashlib.sha256(data).hexdigest() == _SCORE_SHA256


def test_mass_methods_upstream() -> None:
    """The four mass methods read as upstream."""
    for name, expected in _UPSTREAM_METHODS.items():
        source = textwrap.dedent(inspect.getsource(getattr(SymbolIR, name)))
        assert source.strip() == expected.strip(), name


def test_high_complexity_threshold_is_10() -> None:
    """The cutoff is 10."""
    assert models.HIGH_COMPLEXITY_THRESHOLD == 10
