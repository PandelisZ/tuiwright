"""Layer 4: the public screen model.

These types are what users of tuiwright write assertions against. The
emulator (``_emulator.py``) is internal; ``Screen`` is the stable
contract.

Cells are addressed ``(row, col)`` with 0-based indices. Rows count
from the top of the visible viewport; cols count from the left.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from tuiwright._emulator import Emulator


# -----------------------------------------------------------------------
# Primitives
# -----------------------------------------------------------------------


class Position(NamedTuple):
    row: int
    col: int


@dataclass(frozen=True, slots=True)
class Color:
    """A foreground or background colour.

    ``name`` is one of ``"default"``, ``"black"``, ``"red"`` … or the empty
    string if ``rgb`` is set. ``rgb`` is a hex triple ``"ff8800"`` (no
    leading ``#``) for true-colour cells, or ``None`` otherwise.
    """

    name: str = "default"
    rgb: str | None = None

    @classmethod
    def from_pyte(cls, value: str) -> Color:
        # pyte uses "default" sentinel and 6-char hex for true colour.
        if value == "default":
            return _DEFAULT_COLOR
        if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
            return cls(name="", rgb=value.lower())
        return cls(name=value)

    @property
    def is_default(self) -> bool:
        return self.name == "default" and self.rgb is None


_DEFAULT_COLOR = Color()


@dataclass(frozen=True, slots=True)
class Cell:
    """A single rendered terminal cell."""

    char: str = " "
    fg: Color = _DEFAULT_COLOR
    bg: Color = _DEFAULT_COLOR
    bold: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False
    strike: bool = False
    blink: bool = False

    def has_default_attrs(self) -> bool:
        return (
            self.fg.is_default
            and self.bg.is_default
            and not (self.bold or self.italic or self.underline or self.reverse or self.strike or self.blink)
        )


_DEFAULT_CELL = Cell()


@dataclass(frozen=True, slots=True)
class Cursor:
    row: int
    col: int
    hidden: bool = False


# -----------------------------------------------------------------------
# Screen
# -----------------------------------------------------------------------


@dataclass(frozen=True)
class Screen:
    """An immutable snapshot of the terminal grid."""

    rows: int
    cols: int
    cells: tuple[tuple[Cell, ...], ...]
    cursor: Cursor
    modes: frozenset[int] = field(default_factory=frozenset)

    # -- construction --------------------------------------------------

    @classmethod
    def from_emulator(cls, emu: Emulator) -> Screen:
        from tuiwright._emulator import Emulator as _Emu  # noqa: F401

        pyte_cells = emu.cells()
        rows = tuple(
            tuple(
                Cell(
                    char=pc.data or " ",
                    fg=Color.from_pyte(pc.fg),
                    bg=Color.from_pyte(pc.bg),
                    bold=bool(pc.bold),
                    italic=bool(pc.italics),
                    underline=bool(pc.underscore),
                    reverse=bool(pc.reverse),
                    strike=bool(pc.strikethrough),
                    blink=bool(pc.blink),
                )
                for pc in row
            )
            for row in pyte_cells
        )
        pyte_cursor = emu.screen.cursor
        cursor = Cursor(row=pyte_cursor.y, col=pyte_cursor.x, hidden=bool(pyte_cursor.hidden))
        return cls(
            rows=emu.rows,
            cols=emu.cols,
            cells=rows,
            cursor=cursor,
            modes=emu.private_modes,
        )

    # -- text views ----------------------------------------------------

    @property
    def text(self) -> str:
        """All rows joined with ``\\n``, trailing spaces stripped per row."""
        return "\n".join(self.row(i) for i in range(self.rows))

    def row(self, i: int) -> str:
        return "".join(c.char for c in self.cells[i]).rstrip()

    def row_padded(self, i: int) -> str:
        return "".join(c.char for c in self.cells[i])

    def cell(self, row: int, col: int) -> Cell:
        return self.cells[row][col]

    # -- search --------------------------------------------------------

    def find(self, needle: str | re.Pattern[str], *, regex: bool = False) -> list[Position]:
        pattern = needle if isinstance(needle, re.Pattern) else (
            re.compile(needle) if regex else re.compile(re.escape(needle))
        )
        out: list[Position] = []
        for r in range(self.rows):
            for m in pattern.finditer(self.row_padded(r)):
                out.append(Position(r, m.start()))
        return out

    def row_containing(
        self, needle: str | re.Pattern[str], *, regex: bool = False
    ) -> int | None:
        hits = self.find(needle, regex=regex)
        return hits[0].row if hits else None

    def contains(self, needle: str | re.Pattern[str], *, regex: bool = False) -> bool:
        return bool(self.find(needle, regex=regex))

    # -- regions -------------------------------------------------------

    def region(
        self,
        *,
        title: str | None = None,
        rows: tuple[int, int] | None = None,
        cols: tuple[int, int] | None = None,
    ) -> Region:
        if title is not None:
            found = _find_titled_region(self, title)
            if found is None:
                raise LookupError(f"no titled region matching {title!r}")
            return found
        if rows is None or cols is None:
            raise ValueError("either title= or both rows= and cols= must be given")
        r0, r1 = rows
        c0, c1 = cols
        return Region(screen=self, top=r0, bottom=r1, left=c0, right=c1, title=None)


# -----------------------------------------------------------------------
# Region
# -----------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """A rectangular sub-view of a :class:`Screen`.

    Bounds are *inclusive* on top/left and *exclusive* on bottom/right
    (standard Python slice convention).
    """

    screen: Screen
    top: int
    bottom: int
    left: int
    right: int
    title: str | None = None

    @property
    def rows(self) -> int:
        return self.bottom - self.top

    @property
    def cols(self) -> int:
        return self.right - self.left

    @property
    def text(self) -> str:
        return "\n".join(self.row(i) for i in range(self.rows))

    def row(self, i: int) -> str:
        cells = self.screen.cells[self.top + i][self.left : self.right]
        return "".join(c.char for c in cells).rstrip()

    def contains(self, needle: str | re.Pattern[str], *, regex: bool = False) -> bool:
        pat = needle if isinstance(needle, re.Pattern) else (
            re.compile(needle) if regex else re.compile(re.escape(needle))
        )
        return any(pat.search(self.row(i)) for i in range(self.rows))


# -----------------------------------------------------------------------
# Titled-region detection (heuristic)
# -----------------------------------------------------------------------

# Single-line box drawing — what ratatui's Block uses by default.
_TL, _TR, _BL, _BR = "┌", "┐", "└", "┘"
_HORIZ, _VERT = "─", "│"
# Double-line variant just in case.
_DBL_CHARS = {"╔", "╗", "╚", "╝", "═", "║"}


def _find_titled_region(screen: Screen, title: str) -> Region | None:
    """Find the inside of a box whose top border contains ``title``.

    ratatui's typical border row looks like ``┌─ Title ─┐``. We:

    1. Find a row whose padded text contains both the title and at least
       one box-drawing char to the left.
    2. Walk left from the title until we hit ``┌`` (or ``╔``).
    3. Walk right from the title until we hit ``┐`` (or ``╗``).
    4. Walk the left column downward until we hit ``└`` (or ``╚``).

    Returns the rectangle *inside* the borders.
    """
    for top in range(screen.rows):
        row_text = screen.row_padded(top)
        if title not in row_text:
            continue
        title_col = row_text.index(title)
        left = _walk_left_for_corner(row_text, title_col)
        if left is None:
            continue
        right = _walk_right_for_corner(row_text, title_col + len(title))
        if right is None or right <= left:
            continue
        bottom = _walk_down_for_corner(screen, top, left)
        if bottom is None or bottom <= top:
            continue
        return Region(
            screen=screen,
            top=top + 1,
            bottom=bottom,
            left=left + 1,
            right=right,
            title=title,
        )
    return None


def _walk_left_for_corner(row_text: str, start: int) -> int | None:
    for i in range(start, -1, -1):
        ch = row_text[i]
        if ch in (_TL, "╔"):
            return i
        if ch not in (_HORIZ, "═", " ", _VERT) and ch != "":
            # Ran into non-border content; abort.
            if i < start - 1:
                return None
    return None


def _walk_right_for_corner(row_text: str, start: int) -> int | None:
    for i in range(start, len(row_text)):
        ch = row_text[i]
        if ch in (_TR, "╗"):
            return i
        if ch not in (_HORIZ, "═", " ") and ch != "":
            if i > start + 1:
                return None
    return None


def _walk_down_for_corner(screen: Screen, top: int, left: int) -> int | None:
    for r in range(top + 1, screen.rows):
        ch = screen.cells[r][left].char
        if ch in (_BL, "╚"):
            return r
        if ch not in (_VERT, "║"):
            return None
    return None
