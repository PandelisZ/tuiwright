"""End-to-end tests for TuiSession against the demo fixture app."""

from __future__ import annotations

import pytest

from tuiwright import TuiSession, TuiTimeoutError
from tuiwright.session import TuiConfig

pytestmark = pytest.mark.asyncio


async def test_start_and_ready_banner(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd, cols=80, rows=24)
    await tui.wait_for_text("Ready", timeout=3)
    assert tui.alive
    assert "Ready" in tui.screen.text


async def test_type_appears_in_echo(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    await tui.type("hello")
    await tui.wait_for_text("hello", region=tui.region(rows=(3, 5), cols=(0, 80)))


async def test_ctrl_s_sets_saved_status(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")


async def test_backspace_removes_char(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    await tui.type("abc")
    await tui.wait_for_text("abc")
    await tui.press("backspace")
    await tui.wait_for_stable(quiet_ms=80)
    # 'ab' is a substring of 'abc'; check the row directly.
    assert tui.screen.row(3).startswith("ab")
    assert not tui.screen.row(3).startswith("abc")


async def test_q_quits_cleanly(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    await tui.press("q")
    # Wait for the process to exit.
    await tui.wait_for_predicate(lambda s: not tui.alive, timeout=2, description="exit")
    assert not tui.alive


async def test_wait_for_text_timeout(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    with pytest.raises(TuiTimeoutError):
        await tui.wait_for_text("nope-never-appears", timeout=0.3)


async def test_wait_for_stable(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd)
    await tui.wait_for_text("Ready")
    await tui.wait_for_stable(quiet_ms=100, timeout=2)


async def test_screen_dimensions_match_pty(tui: TuiSession, demo_cmd: list[str]) -> None:
    await tui.start(demo_cmd, cols=100, rows=30)
    await tui.wait_for_text("Ready")
    assert tui.screen.cols == 100
    assert tui.screen.rows == 30


async def test_context_manager(demo_cmd: list[str]) -> None:
    async with TuiSession(TuiConfig(cols=80, rows=24)) as t:
        await t.start(demo_cmd)
        await t.wait_for_text("Ready")
    # No assertion needed; reaching here without hang or error proves cleanup.
