"""tuiwright — Playwright-style end-to-end testing for TUI applications.

Drives any TUI binary under a real PTY + terminal emulator, with cell-grid
and PNG snapshot regression.

Quick start:

    async def test_app(tui, snapshot):
        await tui.start("myapp")
        await tui.wait_for_text("Ready")
        await tui.type("hello")
        await tui.press("enter")
        assert tui.screen == snapshot
"""

from tuiwright.screen import Cell, Color, Cursor, Position, Region, Screen
from tuiwright.session import TuiSession, TuiTimeoutError

__all__ = [
    "Cell",
    "Color",
    "Cursor",
    "Position",
    "Region",
    "Screen",
    "TuiSession",
    "TuiTimeoutError",
    "__version__",
]

__version__ = "0.2.0"
