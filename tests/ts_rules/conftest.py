"""Fixtures for the TypeScript rule tests."""

from __future__ import annotations

import pytest
from rule_helpers import RuleCase
from rule_helpers import load_rule_cases


@pytest.fixture(scope="session")
def rule_cases() -> tuple[RuleCase, ...]:
    """All bundled TypeScript rule documents."""
    return load_rule_cases()
