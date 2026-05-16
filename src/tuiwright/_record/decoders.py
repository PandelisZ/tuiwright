"""Reverse of ``tuiwright._input``: bytes → high-level actions.

Used by codegen to turn a recorded byte stream back into the
``TuiSession`` calls a human would have written by hand.

The decoder is *lossy* on purpose: a long ``\\x1b[<...M\\x1b[<...m`` mouse
press+release pair becomes a single ``click(row, col)`` action; a run of
printable bytes becomes one ``type("hello world")``. The goal is a
readable test, not an exact byte-for-byte replay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

# ---------------------------------------------------------------------------
# Action representation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecordedAction:
    """One decoded high-level action.

    ``kind`` is one of: ``"type"``, ``"press"``, ``"click"``,
    ``"double_click"``, ``"scroll"``, ``"drag"``, ``"paste"``,
    ``"focus"``, ``"unknown"``. ``data`` holds the kwargs each kind
    needs; the renderer in ``codegen.py`` knows how to format them.
    """

    kind: str
    data: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Decoder tables (reverse lookups from _input.py)
# ---------------------------------------------------------------------------

# Sequences that decode to a single named key with no modifiers. Ordered
# by length descending so the matcher tries the longest possible match
# first.
_NAMED_SEQUENCES: Final[list[tuple[bytes, str]]] = sorted(
    [
        (b"\x1b[15~", "f5"),
        (b"\x1b[17~", "f6"),
        (b"\x1b[18~", "f7"),
        (b"\x1b[19~", "f8"),
        (b"\x1b[20~", "f9"),
        (b"\x1b[21~", "f10"),
        (b"\x1b[23~", "f11"),
        (b"\x1b[24~", "f12"),
        (b"\x1bOP", "f1"),
        (b"\x1bOQ", "f2"),
        (b"\x1bOR", "f3"),
        (b"\x1bOS", "f4"),
        (b"\x1b[2~", "insert"),
        (b"\x1b[3~", "delete"),
        (b"\x1b[5~", "pageup"),
        (b"\x1b[6~", "pagedown"),
        (b"\x1b[A", "up"),
        (b"\x1b[B", "down"),
        (b"\x1b[C", "right"),
        (b"\x1b[D", "left"),
        (b"\x1b[H", "home"),
        (b"\x1b[F", "end"),
        (b"\x1b[Z", "shift+tab"),
        (b"\r", "enter"),
        (b"\n", "enter"),
        (b"\t", "tab"),
        (b" ", None),  # space is more readably part of a type() run
        (b"\x7f", "backspace"),
        (b"\x08", "ctrl+h"),  # Ctrl-H — explicit form, not "backspace"
        # NOTE: bare ``\x1b`` (escape) is handled in the main loop *after*
        # the alt+letter check, so ``\x1bf`` decodes as ``alt+f`` not
        # ``escape`` + ``type("f")``.
    ],
    key=lambda kv: -len(kv[0]),
)

# CSI with modifier param: ``\x1b[1;MX`` or ``\x1b[N;M~``.
# No ``^`` anchor — ``Pattern.match(data, pos)`` already requires
# the match to start at ``pos``; ``^`` would force it to start at
# position 0 of the whole bytes object, which breaks mid-stream matches.
_CSI_MOD_LETTER_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"\x1b\[1;(\d+)([A-HPQRS])"
)
_CSI_MOD_TILDE_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"\x1b\[(\d+);(\d+)~"
)

# Reverse of _CSI_LETTER_FINALS in _input.py.
_LETTER_TO_NAME: Final[dict[bytes, str]] = {
    b"A": "up",
    b"B": "down",
    b"C": "right",
    b"D": "left",
    b"H": "home",
    b"F": "end",
    b"P": "f1",
    b"Q": "f2",
    b"R": "f3",
    b"S": "f4",
}

# Reverse of _CSI_TILDE_NUMS in _input.py.
_TILDE_NUM_TO_NAME: Final[dict[int, str]] = {
    2: "insert",
    3: "delete",
    5: "pageup",
    6: "pagedown",
    15: "f5",
    17: "f6",
    18: "f7",
    19: "f8",
    20: "f9",
    21: "f10",
    23: "f11",
    24: "f12",
}

# Mouse SGR 1006: ``\x1b[<Cb;Cx;Cy(M|m)``
_MOUSE_SGR_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])"
)

# Bracketed paste sentinels.
_PASTE_START: Final[bytes] = b"\x1b[200~"
_PASTE_END: Final[bytes] = b"\x1b[201~"

# Focus events.
_FOCUS_IN: Final[bytes] = b"\x1b[I"
_FOCUS_OUT: Final[bytes] = b"\x1b[O"

# Mouse button bits.
_MOUSE_BUTTON_NAMES: Final[dict[int, str]] = {
    0: "left",
    1: "middle",
    2: "right",
}
_MOUSE_WHEEL_NAMES: Final[dict[int, str]] = {
    64: "wheel_up",
    65: "wheel_down",
    66: "wheel_left",
    67: "wheel_right",
}


# ---------------------------------------------------------------------------
# Modifier helpers
# ---------------------------------------------------------------------------


def _modifier_string(xterm_param: int) -> str:
    """Convert an xterm modifier param (2-16) into a ``ctrl+shift+...`` prefix.

    Returns ``""`` for param 1 (no modifiers).
    """
    bits = xterm_param - 1
    parts = []
    if bits & 4:
        parts.append("ctrl")
    if bits & 2:
        parts.append("alt")
    if bits & 1:
        parts.append("shift")
    if bits & 8:
        parts.append("meta")
    return "+".join(parts) + ("+" if parts else "")


def _mouse_modifiers(cb: int) -> tuple[str, ...]:
    out = []
    if cb & 16:
        out.append("ctrl")
    if cb & 8:
        out.append("alt")
    if cb & 4:
        out.append("shift")
    return tuple(out)


# ---------------------------------------------------------------------------
# Mouse event aggregation
# ---------------------------------------------------------------------------


@dataclass
class _MouseEvent:
    cb: int          # raw button code with modifier/motion bits stripped after parsing
    raw_cb: int
    col: int         # 1-based on the wire
    row: int
    pressed: bool
    motion: bool


def _parse_mouse(match: re.Match[bytes]) -> _MouseEvent:
    raw_cb = int(match.group(1))
    col = int(match.group(2))
    row = int(match.group(3))
    pressed = match.group(4) == b"M"
    motion = bool(raw_cb & 32)
    base = raw_cb & ~(32 | 4 | 8 | 16)  # strip motion + modifier bits
    return _MouseEvent(cb=base, raw_cb=raw_cb, col=col, row=row, pressed=pressed, motion=motion)


def _coalesce_mouse(events: list[_MouseEvent]) -> RecordedAction:
    """Turn a press[+motion]*+release sequence into one click/drag/scroll."""
    first = events[0]
    last = events[-1]
    # Wheel events arrive as a single "M" press with no release.
    if first.cb in _MOUSE_WHEEL_NAMES and len(events) == 1:
        direction = "down" if first.cb == 65 else "up"
        return RecordedAction(
            "scroll",
            {
                "row": first.row - 1,
                "col": first.col - 1,
                "direction": direction,
                "lines": 1,
            },
        )
    # Pure motion (no press/release) — uncommon, decode as hover.
    if all(ev.motion and ev.cb == 3 for ev in events) and len(events) == 1:
        return RecordedAction(
            "hover", {"row": first.row - 1, "col": first.col - 1}
        )
    # Drag: press + motion(s) + release at a different cell.
    if any(ev.motion for ev in events) and (first.row != last.row or first.col != last.col):
        button = _MOUSE_BUTTON_NAMES.get(first.cb, "left")
        return RecordedAction(
            "drag",
            {
                "from_row": first.row - 1,
                "from_col": first.col - 1,
                "to_row": last.row - 1,
                "to_col": last.col - 1,
                "button": button,
            },
        )
    # Click: press + release at the same cell.
    button = _MOUSE_BUTTON_NAMES.get(first.cb, "left")
    modifiers = _mouse_modifiers(first.raw_cb)
    data: dict[str, object] = {
        "row": first.row - 1,
        "col": first.col - 1,
    }
    if button != "left":
        data["button"] = button
    if modifiers:
        data["modifiers"] = list(modifiers)
    return RecordedAction("click", data)


# ---------------------------------------------------------------------------
# Main decoder
# ---------------------------------------------------------------------------


def decode_input_stream(data: bytes) -> list[RecordedAction]:
    """Decode a contiguous chunk of user input into high-level actions.

    Collapses runs of printable bytes into one ``type(...)`` action.
    Groups mouse press+release into a single ``click``; press+motion+release
    into ``drag``. Recognises paste, focus, function keys, navigation
    keys, and ctrl/alt/shift combinations.
    """
    out: list[RecordedAction] = []
    text_buf: list[str] = []
    mouse_buf: list[_MouseEvent] = []
    i = 0

    def flush_text() -> None:
        if text_buf:
            out.append(RecordedAction("type", {"text": "".join(text_buf)}))
            text_buf.clear()

    def flush_mouse() -> None:
        if mouse_buf:
            out.append(_coalesce_mouse(mouse_buf))
            mouse_buf.clear()

    while i < len(data):
        # --- Bracketed paste -------------------------------------------------
        if data[i:].startswith(_PASTE_START):
            flush_text()
            flush_mouse()
            end = data.find(_PASTE_END, i + len(_PASTE_START))
            if end == -1:
                # Truncated paste — fall back to consuming the rest as text.
                text_buf.append(data[i + len(_PASTE_START) :].decode("utf-8", "replace"))
                i = len(data)
                continue
            payload = data[i + len(_PASTE_START) : end]
            out.append(RecordedAction("paste", {"text": payload.decode("utf-8", "replace")}))
            i = end + len(_PASTE_END)
            continue

        # --- Focus events ----------------------------------------------------
        if data[i:].startswith(_FOCUS_IN):
            flush_text()
            flush_mouse()
            out.append(RecordedAction("focus", {"in_": True}))
            i += len(_FOCUS_IN)
            continue
        if data[i:].startswith(_FOCUS_OUT):
            flush_text()
            flush_mouse()
            out.append(RecordedAction("focus", {"in_": False}))
            i += len(_FOCUS_OUT)
            continue

        # --- Mouse SGR -------------------------------------------------------
        m = _MOUSE_SGR_RE.match(data, i)
        if m:
            flush_text()
            ev = _parse_mouse(m)
            # Wheel events: each is independent (no release pair).
            if ev.raw_cb in _MOUSE_WHEEL_NAMES:
                flush_mouse()
                mouse_buf.append(ev)
                flush_mouse()
            else:
                mouse_buf.append(ev)
                # A release closes the sequence.
                if not ev.pressed:
                    flush_mouse()
            i = m.end()
            continue

        # --- CSI with modifier param ----------------------------------------
        mcsi = _CSI_MOD_LETTER_RE.match(data, i)
        if mcsi:
            flush_text()
            flush_mouse()
            param = int(mcsi.group(1))
            letter = mcsi.group(2)
            name = _LETTER_TO_NAME.get(letter)
            if name:
                out.append(RecordedAction("press", {"key": _modifier_string(param) + name}))
            else:
                out.append(RecordedAction("unknown", {"bytes": bytes(mcsi.group(0))}))
            i = mcsi.end()
            continue
        mtilde = _CSI_MOD_TILDE_RE.match(data, i)
        if mtilde:
            flush_text()
            flush_mouse()
            num = int(mtilde.group(1))
            param = int(mtilde.group(2))
            name = _TILDE_NUM_TO_NAME.get(num)
            if name:
                out.append(RecordedAction("press", {"key": _modifier_string(param) + name}))
            else:
                out.append(RecordedAction("unknown", {"bytes": bytes(mtilde.group(0))}))
            i = mtilde.end()
            continue

        # --- Plain named sequences ------------------------------------------
        matched = False
        for seq, name in _NAMED_SEQUENCES:
            if name is None:
                continue
            if data[i:].startswith(seq):
                flush_text()
                flush_mouse()
                out.append(RecordedAction("press", {"key": name}))
                i += len(seq)
                matched = True
                break
        if matched:
            continue

        # --- Ctrl + letter --------------------------------------------------
        if 1 <= data[i] <= 26 and data[i] not in (9, 10, 13):  # exclude tab/lf/cr
            flush_text()
            flush_mouse()
            letter = chr(data[i] - 1 + ord("a"))
            out.append(RecordedAction("press", {"key": f"ctrl+{letter}"}))
            i += 1
            continue

        # --- Alt + letter (ESC + printable) --------------------------------
        if (
            data[i] == 0x1B
            and i + 1 < len(data)
            and 0x20 <= data[i + 1] <= 0x7E
        ):
            flush_text()
            flush_mouse()
            out.append(RecordedAction("press", {"key": f"alt+{chr(data[i + 1])}"}))
            i += 2
            continue

        # --- Lone ESC ------------------------------------------------------
        # Must come *after* the alt+letter check so ``\x1bf`` decodes as
        # ``alt+f`` instead of ``escape`` then ``f``.
        if data[i] == 0x1B:
            flush_text()
            flush_mouse()
            out.append(RecordedAction("press", {"key": "escape"}))
            i += 1
            continue

        # --- Printable ASCII ------------------------------------------------
        byte = data[i]
        if 0x20 <= byte <= 0x7E:
            text_buf.append(chr(byte))
            i += 1
            continue

        # --- UTF-8 multi-byte continuation (lead byte 0x80+) ---------------
        if byte >= 0xC0:
            # UTF-8 lead byte. Determine expected length from the high bits.
            if byte >= 0xF0:
                length = 4
            elif byte >= 0xE0:
                length = 3
            else:
                length = 2
            if i + length <= len(data):
                try:
                    text_buf.append(data[i : i + length].decode("utf-8"))
                    i += length
                    continue
                except UnicodeDecodeError:
                    pass
            # Malformed sequence — skip the lead byte and let recovery happen.
            i += 1
            continue

        # --- Unknown control byte -------------------------------------------
        flush_text()
        flush_mouse()
        out.append(RecordedAction("unknown", {"bytes": bytes([byte])}))
        i += 1

    flush_text()
    flush_mouse()
    return out
