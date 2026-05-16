"""Fixtures for the gode example suite."""

from __future__ import annotations

import os
import shutil

import pytest


@pytest.fixture
def gode_bin() -> str:
    """Resolve the path to a gode binary, skipping if not available."""
    candidates = [os.environ.get("GODE_BIN"), shutil.which("gode")]
    for c in candidates:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    pytest.skip("set GODE_BIN or put `gode` on PATH to run gode integration tests")


@pytest.fixture
def gode_env() -> dict[str, str]:
    """Environment for gode runs — provides a dummy key so startup succeeds."""
    return {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", "sk-test"),
        "RUST_BACKTRACE": "1",
        # Disable any persistent state writes during tests.
        "GODE_TEST_MODE": "1",
    }
