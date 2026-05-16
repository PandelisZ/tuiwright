"""Layer 2: terminal emulator wrapping pyte with DEC mode tracking.

Parses bytes emitted by the child process into a 2D ``Screen``, and
exposes which private DEC modes (mouse, bracketed paste, focus) the app
has enabled. The session layer uses these flags to (1) decide whether
mouse input is meaningful and (2) wrap pasted text in the right brackets.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

import pyte
from pyte.screens import Char as PyteChar

# DEC private modes we care about. See xterm ctlseqs for the full set.
MODE_MOUSE_X10: Final[int] = 1000
MODE_MOUSE_BUTTON: Final[int] = 1002
MODE_MOUSE_ANY: Final[int] = 1003
MODE_MOUSE_SGR: Final[int] = 1006
MODE_FOCUS: Final[int] = 1004
MODE_BRACKETED_PASTE: Final[int] = 2004
MODE_ALT_SCREEN: Final[int] = 1049

MOUSE_TRACKING_MODES: Final[frozenset[int]] = frozenset(
    {MODE_MOUSE_X10, MODE_MOUSE_BUTTON, MODE_MOUSE_ANY}
)


class TrackedScreen(pyte.Screen):
    """pyte.Screen that exposes the set of private DEC modes currently on.

    pyte handles a few private modes internally (origin mode, autowrap,
    etc.) but doesn't expose mouse / bracketed-paste / focus modes in a
    queryable way. We override ``set_mode`` / ``reset_mode`` to keep a
    side-table.
    """

    private_modes: set[int]

    def __init__(self, columns: int, lines: int) -> None:
        super().__init__(columns, lines)
        # Don't rely on subclass __dict__ ordering; set after super init.
        self.private_modes = set()

    def set_mode(self, *modes: int, **kwargs: bool) -> None:  # type: ignore[override]
        super().set_mode(*modes, **kwargs)
        if kwargs.get("private"):
            self.private_modes.update(modes)

    def reset_mode(self, *modes: int, **kwargs: bool) -> None:  # type: ignore[override]
        super().reset_mode(*modes, **kwargs)
        if kwargs.get("private"):
            self.private_modes.difference_update(modes)

    def reset(self) -> None:  # type: ignore[override]
        super().reset()
        self.private_modes = set()


class Emulator:
    """Holds the screen, feeds bytes into it, and exposes mode state.

    Resize is *active* — call :meth:`resize` to change the simulated
    terminal dimensions; the wrapped pyte screen and stream are reset
    consistently.
    """

    def __init__(self, *, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows
        self._screen = TrackedScreen(cols, rows)
        self._stream = pyte.ByteStream(self._screen)
        self._revision = 0  # bumped on every feed; used for stable-screen waits

    # -- feeding --------------------------------------------------------

    def feed(self, chunk: bytes) -> None:
        if not chunk:
            return
        self._stream.feed(chunk)
        self._revision += 1

    # -- query ----------------------------------------------------------

    @property
    def screen(self) -> TrackedScreen:
        return self._screen

    @property
    def cols(self) -> int:
        return self._cols

    @property
    def rows(self) -> int:
        return self._rows

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def private_modes(self) -> frozenset[int]:
        return frozenset(self._screen.private_modes)

    def is_mouse_tracking(self) -> bool:
        return bool(self._screen.private_modes & MOUSE_TRACKING_MODES)

    def is_bracketed_paste(self) -> bool:
        return MODE_BRACKETED_PASTE in self._screen.private_modes

    def is_focus_events(self) -> bool:
        return MODE_FOCUS in self._screen.private_modes

    # -- mutation -------------------------------------------------------

    def resize(self, cols: int, rows: int) -> None:
        self._cols = cols
        self._rows = rows
        self._screen.resize(rows, cols)
        self._revision += 1

    # -- cell access ---------------------------------------------------

    def cells(self) -> list[list[PyteChar]]:
        """Materialise the full grid as a 2D list, including empty cells."""
        buf = self._screen.buffer
        default = self._screen.default_char
        out: list[list[PyteChar]] = []
        for y in range(self._rows):
            row_buf = buf.get(y, {})
            out.append([row_buf.get(x, default) for x in range(self._cols)])
        return out

    def cell_rows_text(self) -> Iterable[str]:
        """Yield each row as a string, padded to the column count."""
        buf = self._screen.buffer
        default_char = self._screen.default_char.data
        for y in range(self._rows):
            row_buf = buf.get(y, {})
            chars: list[str] = []
            for x in range(self._cols):
                ch = row_buf.get(x)
                chars.append(ch.data if ch is not None else default_char)
            yield "".join(chars).rstrip()
