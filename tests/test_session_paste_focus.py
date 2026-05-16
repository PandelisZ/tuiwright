"""Bracketed paste, focus events, and resize integration tests."""

from __future__ import annotations

import pytest

from tuiwright import TuiSession

pytestmark = pytest.mark.asyncio


async def _ready(tui: TuiSession, cmd: list[str]) -> None:
    await tui.start(cmd, cols=80, rows=24)
    await tui.wait_for_text("Ready")
    # Wait for the app to fully enable its modes.
    await tui.wait_for_predicate(
        lambda _: (
            tui._emu.is_bracketed_paste()  # type: ignore[attr-defined]
            and tui._emu.is_focus_events()  # type: ignore[attr-defined]
        ),
        timeout=2,
        description="modes enabled",
    )


async def test_bracketed_paste_logs_count(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.paste("hello world!")
    await tui.wait_for_text("paste N=12")
    # The pasted text also lands in the echo buffer.
    await tui.wait_for_text("hello world!")


async def test_paste_collision_raises(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    with pytest.raises(ValueError, match="end marker"):
        await tui.paste("safe \x1b[201~ unsafe")


async def test_focus_in_out(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.focus(in_=False)
    await tui.wait_for_text("focus out")
    await tui.focus(in_=True)
    await tui.wait_for_text("focus in")


async def test_resize_updates_displayed_dimensions(
    tui: TuiSession, demo_cmd: list[str]
) -> None:
    await _ready(tui, demo_cmd)
    await tui.resize(60, 18)
    await tui.wait_for_text("size=60x18")
    assert tui.screen.cols == 60
    assert tui.screen.rows == 18
