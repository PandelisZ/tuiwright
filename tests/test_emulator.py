"""Tests for the pyte-wrapping emulator and its DEC mode tracking."""

from __future__ import annotations

from tuiwright._emulator import (
    MODE_BRACKETED_PASTE,
    MODE_FOCUS,
    MODE_MOUSE_SGR,
    Emulator,
)


def feed_modes(emu: Emulator, *modes: int, set_: bool = True) -> None:
    op = b"h" if set_ else b"l"
    for m in modes:
        emu.feed(b"\x1b[?" + str(m).encode() + op)


class TestDECMode:
    def test_set_mouse_sgr(self) -> None:
        emu = Emulator(cols=10, rows=5)
        feed_modes(emu, 1000, 1006)
        assert emu.is_mouse_tracking()
        assert MODE_MOUSE_SGR in emu.private_modes

    def test_reset_mouse(self) -> None:
        emu = Emulator(cols=10, rows=5)
        feed_modes(emu, 1000, 1006)
        feed_modes(emu, 1000, set_=False)
        # SGR still on, but tracking flag (1000) is off; emulator considers
        # any of 1000/1002/1003 as "mouse tracking on".
        assert not emu.is_mouse_tracking()
        assert MODE_MOUSE_SGR in emu.private_modes

    def test_bracketed_paste(self) -> None:
        emu = Emulator(cols=5, rows=2)
        assert not emu.is_bracketed_paste()
        feed_modes(emu, 2004)
        assert emu.is_bracketed_paste()
        feed_modes(emu, 2004, set_=False)
        assert not emu.is_bracketed_paste()
        assert MODE_BRACKETED_PASTE not in emu.private_modes

    def test_focus_events(self) -> None:
        emu = Emulator(cols=5, rows=2)
        feed_modes(emu, 1004)
        assert emu.is_focus_events()
        assert MODE_FOCUS in emu.private_modes


class TestResize:
    def test_resize_grows(self) -> None:
        emu = Emulator(cols=10, rows=3)
        emu.feed(b"hi")
        emu.resize(20, 5)
        assert emu.cols == 20
        assert emu.rows == 5
        # Existing content survives.
        cells = emu.cells()
        assert len(cells) == 5
        assert len(cells[0]) == 20
        assert cells[0][0].data == "h"

    def test_revision_bumps_on_feed_and_resize(self) -> None:
        emu = Emulator(cols=10, rows=3)
        r0 = emu.revision
        emu.feed(b"x")
        assert emu.revision > r0
        r1 = emu.revision
        emu.resize(20, 5)
        assert emu.revision > r1
