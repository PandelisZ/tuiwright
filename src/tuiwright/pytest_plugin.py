"""pytest integration: ``tui`` fixture, CLI flags, and marker support.

Registered via the ``pytest11`` entry-point in ``pyproject.toml``, so
installing the package is enough — no ``conftest.py`` boilerplate needed.

Usage in tests::

    async def test_thing(tui, snapshot):
        await tui.start("myapp")
        await tui.wait_for_text("Ready")
        assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)

The ``snapshot`` fixture comes from syrupy; pass ``extension_class``
explicitly to choose between cell-grid (``ScreenSnapshotExtension``) and
PNG (``PNGSnapshotExtension``).

CLI flags:
  --tui-trace=on|retain-on-failure|off  (default: retain-on-failure)
      Keep the asciinema cast file after the test.
  --tui-cols, --tui-rows
      Default terminal dimensions for every session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

from tuiwright._snapshot import PNGSnapshotExtension, ScreenSnapshotExtension
from tuiwright.session import TuiConfig, TuiSession

if TYPE_CHECKING:
    pass


_TRACE_MODES = ("on", "retain-on-failure", "off")


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("tuiwright")
    group.addoption(
        "--tui-trace",
        action="store",
        default="retain-on-failure",
        choices=_TRACE_MODES,
        help="When to retain the asciinema cast file: on | retain-on-failure | off.",
    )
    group.addoption(
        "--tui-cols",
        action="store",
        type=int,
        default=80,
        help="Default terminal columns for sessions.",
    )
    group.addoption(
        "--tui-rows",
        action="store",
        type=int,
        default=24,
        help="Default terminal rows for sessions.",
    )
    group.addoption(
        "--tui-timeout",
        action="store",
        type=float,
        default=5.0,
        help="Default timeout (s) for wait_for_* calls.",
    )
    group.addoption(
        "--tui-trace-dir",
        action="store",
        default=None,
        help="Directory for retained cast files (defaults to ./trace).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "tui(cols=80, rows=24, timeout=5.0, strict_mouse=False): "
        "configure the tui session for this test",
    )


# -----------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------


@pytest.fixture
def tui_config(request: pytest.FixtureRequest) -> TuiConfig:
    """Per-test ``TuiConfig`` derived from CLI flags and the ``tui`` marker."""
    cfg = TuiConfig(
        cols=request.config.getoption("--tui-cols"),
        rows=request.config.getoption("--tui-rows"),
        default_timeout=request.config.getoption("--tui-timeout"),
    )
    marker = request.node.get_closest_marker("tui")
    if marker is not None:
        for key in ("cols", "rows", "default_timeout", "strict_mouse"):
            marker_key = "timeout" if key == "default_timeout" else key
            if marker_key in marker.kwargs:
                setattr(cfg, key, marker.kwargs[marker_key])
    return cfg


@pytest_asyncio.fixture
async def tui(
    request: pytest.FixtureRequest,
    tui_config: TuiConfig,
    tmp_path: Path,
) -> AsyncIterator[TuiSession]:
    """The primary fixture: a single ``TuiSession`` per test."""
    trace_mode = request.config.getoption("--tui-trace")
    trace_dir = request.config.getoption("--tui-trace-dir")
    cast_target = Path(trace_dir) if trace_dir else tmp_path
    tui_config.cast_dir = cast_target
    session = TuiSession(tui_config)
    try:
        yield session
    finally:
        await session.stop()
        _handle_cast_retention(request, session, trace_mode)


@pytest_asyncio.fixture
async def tui_factory(
    request: pytest.FixtureRequest,
    tui_config: TuiConfig,
    tmp_path: Path,
) -> AsyncIterator[Callable[[], TuiSession]]:
    """For tests that need multiple sessions (e.g. multi-pane scenarios)."""
    trace_mode = request.config.getoption("--tui-trace")
    trace_dir = request.config.getoption("--tui-trace-dir")
    cast_target = Path(trace_dir) if trace_dir else tmp_path
    tui_config.cast_dir = cast_target
    sessions: list[TuiSession] = []

    def make() -> TuiSession:
        s = TuiSession(TuiConfig(**vars(tui_config)))
        sessions.append(s)
        return s

    try:
        yield make
    finally:
        for s in sessions:
            await s.stop()
            _handle_cast_retention(request, s, trace_mode)


# -----------------------------------------------------------------------
# Internals
# -----------------------------------------------------------------------


def _handle_cast_retention(
    request: pytest.FixtureRequest, session: TuiSession, mode: str
) -> None:
    if mode == "off":
        _safe_unlink(session._cast_path)  # type: ignore[attr-defined]
        return
    if mode == "on":
        return  # leave wherever it was written
    # retain-on-failure (default)
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        return
    _safe_unlink(session._cast_path)  # type: ignore[attr-defined]


def _safe_unlink(p: Path | None) -> None:
    if p is None:
        return
    try:
        p.unlink()
    except (FileNotFoundError, OSError):
        pass


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# -----------------------------------------------------------------------
# Re-exports — convenience so users can `from tuiwright.pytest_plugin import ...`
# -----------------------------------------------------------------------

__all__ = [
    "PNGSnapshotExtension",
    "ScreenSnapshotExtension",
    "TuiConfig",
    "TuiSession",
    "tui",
    "tui_config",
    "tui_factory",
]
