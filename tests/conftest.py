"""Shared test fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
DEMO_APP = FIXTURES / "demo_app.py"


@pytest.fixture
def demo_cmd() -> list[str]:
    """argv for the demo TUI used by most session tests."""
    return [sys.executable, str(DEMO_APP)]
