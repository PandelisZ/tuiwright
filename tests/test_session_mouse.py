"""Mouse-input integration tests against the demo fixture app."""

from __future__ import annotations

import pytest

from tuiwright import TuiSession

pytestmark = pytest.mark.asyncio


async def _ready(tui: TuiSession, cmd: list[str]) -> None:
    await tui.start(cmd, cols=80, rows=24)
    await tui.wait_for_text("Ready")
    # Wait for the app to enable mouse tracking so the encoder doesn't warn.
    await tui.wait_for_predicate(
        lambda _: tui._emu.is_mouse_tracking(),  # type: ignore[attr-defined]
        timeout=2,
        description="mouse mode enabled",
    )


async def test_left_click_logs_coordinates(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.click(row=8, col=15)
    await tui.wait_for_text("click left R=9 C=16")


async def test_right_click(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.click(row=4, col=4, button="right")
    await tui.wait_for_text("click right R=5 C=5")


async def test_wheel_scroll(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.scroll(row=10, col=10, direction="down", lines=2)
    await tui.wait_for_text("wheel down")


async def test_wheel_up(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.scroll(row=10, col=10, direction="up")
    await tui.wait_for_text("wheel up")


async def test_double_click(tui: TuiSession, demo_cmd: list[str]) -> None:
    await _ready(tui, demo_cmd)
    await tui.double_click(row=5, col=5)
    # Both clicks land in the event log; the most recent is the second.
    await tui.wait_for_text("click left R=6 C=6")
