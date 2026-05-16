"""High-level smoke tests for the gode TUI."""

from __future__ import annotations

import pytest

from tuiwright import TuiSession

pytestmark = pytest.mark.asyncio


async def test_startup_ready(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=120, rows=40)
    # gode renders its border/status as soon as the app loop starts.
    # Wait for any of the well-known status strings.
    await tui.wait_for_predicate(
        lambda s: any(t in s.text for t in ("gode", "Ready", ">", "tab to")),
        timeout=8,
        description="gode startup",
    )
    assert tui.alive


async def test_composer_echo(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=120, rows=40)
    await tui.wait_for_predicate(
        lambda s: any(t in s.text for t in ("gode", ">", "tab to")),
        timeout=8,
        description="composer ready",
    )
    await tui.type("hello tuiwright")
    await tui.wait_for_text("hello tuiwright", timeout=3)


async def test_settings_modal_opens(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    """ctrl+p in gode toggles the Settings modal."""
    await tui.start([gode_bin], env=gode_env, cols=120, rows=40)
    await tui.wait_for_predicate(
        lambda s: any(t in s.text for t in ("gode", ">", "tab to")),
        timeout=8,
        description="ready",
    )
    await tui.press("ctrl+p")
    await tui.wait_for_text("Settings", timeout=3)
    # Status line shows "settings" while the modal is open.
    await tui.wait_for_text("settings")
    await tui.press("escape")
    await tui.wait_for_stable(quiet_ms=120)
    # After escape, "Settings" header should no longer be visible.
    assert "Settings" not in tui.screen.text or "settings" not in tui.screen.row(tui.screen.rows - 1)


async def test_resize_no_panic(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=120, rows=40)
    await tui.wait_for_predicate(
        lambda s: any(t in s.text for t in ("gode", ">", "tab to")),
        timeout=8,
        description="ready",
    )
    await tui.resize(80, 24)
    await tui.wait_for_stable(quiet_ms=150)
    assert tui.alive, "gode should not have crashed on resize"
    assert tui.screen.cols == 80
    assert tui.screen.rows == 24


async def test_bracketed_paste(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=120, rows=40)
    await tui.wait_for_predicate(
        lambda s: any(t in s.text for t in ("gode", ">", "tab to")),
        timeout=8,
        description="ready",
    )
    await tui.paste("line one and line two pasted as one block")
    await tui.wait_for_text("line one", timeout=3)
    assert "line two pasted" in tui.screen.text
