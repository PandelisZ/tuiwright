"""syrupy extension that serializes a :class:`Screen` to a reviewable form.

The on-disk format has two parts in one file:

1. An ASCII-art frame showing the rendered text (one line per row,
   columns padded), wrapped in a box made of ASCII dashes so diffs are
   easy to read in a PR review.
2. A JSON sidecar listing every cell whose attributes differ from the
   default (fg/bg/bold/etc), keyed by ``"row,col"``. Most cells default,
   so the JSON stays tiny.

Snapshot file format::

    # tuiwright screen snapshot v1
    # cols=80 rows=24 cursor=(2,5) modes=[1006,2004]
    +────────────────────────────...────────────────────────────+
    | Row 0 text padded to cols                                 |
    | Row 1 text                                                |
    ...
    +────────────────────────────...────────────────────────────+
    {
      "0,3": {"fg": "red", "bold": true},
      "1,10": {"bg": "blue"}
    }
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

from tuiwright.screen import Cell, Screen

if TYPE_CHECKING:
    from syrupy.types import (
        PropertyFilter,
        PropertyMatcher,
        SerializableData,
        SerializedData,
    )

_FORMAT_VERSION = 1


class ScreenSnapshotExtension(SingleFileSnapshotExtension):
    """Snapshots :class:`Screen` values to a reviewable text+JSON file."""

    file_extension = "screen"
    _write_mode = WriteMode.TEXT

    def serialize(  # type: ignore[override]
        self,
        data: SerializableData,
        *,
        exclude: PropertyFilter | None = None,
        include: PropertyFilter | None = None,
        matcher: PropertyMatcher | None = None,
    ) -> SerializedData:
        if not isinstance(data, Screen):
            raise TypeError(
                f"ScreenSnapshotExtension only accepts Screen values, got {type(data).__name__}"
            )
        return _serialize_screen(data)


def _serialize_screen(s: Screen) -> str:
    header = (
        f"# tuiwright screen snapshot v{_FORMAT_VERSION}\n"
        f"# cols={s.cols} rows={s.rows} cursor=({s.cursor.row},{s.cursor.col})"
        f"{' hidden' if s.cursor.hidden else ''}"
        f" modes={sorted(s.modes)}\n"
    )
    border = "+" + ("─" * s.cols) + "+\n"
    lines = [header, border]
    for r in range(s.rows):
        row_chars = "".join(c.char for c in s.cells[r]).ljust(s.cols)
        lines.append("|" + row_chars + "|\n")
    lines.append(border)

    attrs: dict[str, dict[str, Any]] = {}
    for r in range(s.rows):
        for c in range(s.cols):
            cell = s.cells[r][c]
            if cell.has_default_attrs():
                continue
            attrs[f"{r},{c}"] = _cell_attrs(cell)
    lines.append(json.dumps(attrs, indent=2, sort_keys=True))
    lines.append("\n")
    return "".join(lines)


def _cell_attrs(cell: Cell) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not cell.fg.is_default:
        out["fg"] = cell.fg.rgb if cell.fg.rgb else cell.fg.name
    if not cell.bg.is_default:
        out["bg"] = cell.bg.rgb if cell.bg.rgb else cell.bg.name
    for flag in ("bold", "italic", "underline", "reverse", "strike", "blink"):
        if getattr(cell, flag):
            out[flag] = True
    return out
