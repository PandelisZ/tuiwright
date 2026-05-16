"""Layer 3: encoders that turn high-level intent into PTY bytes.

The goal is parity with what a real terminal emulator (alacritty,
ghostty, xterm in xterm-262color mode) sends when the user presses a
key, clicks the mouse, pastes, or changes focus. This is what apps
written against crossterm / termion / ncurses expect.

References:
- xterm ctlseqs: https://invisible-island.net/xterm/ctlseqs/ctlseqs.html
- vt sequences: https://vt100.net/docs/vt510-rm/chapter4.html
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
from typing import Final

ESC: Final[bytes] = b"\x1b"
CSI: Final[bytes] = b"\x1b["
SS3: Final[bytes] = b"\x1bO"


class Mod(IntFlag):
    NONE = 0
    SHIFT = 1
    ALT = 2
    CTRL = 4
    META = 8  # Super / Cmd. Mapped only when explicitly requested.


_MOD_ALIASES: Final[dict[str, Mod]] = {
    "shift": Mod.SHIFT,
    "s": Mod.SHIFT,
    "alt": Mod.ALT,
    "a": Mod.ALT,
    "opt": Mod.ALT,
    "option": Mod.ALT,
    "ctrl": Mod.CTRL,
    "control": Mod.CTRL,
    "c": Mod.CTRL,
    "cmd": Mod.META,
    "meta": Mod.META,
    "super": Mod.META,
    "win": Mod.META,
}


# Canonical names → un-modified byte sequence.
# For named keys, we apply CSI modifier params when modifiers are present.
_NAMED_KEYS: Final[dict[str, bytes]] = {
    # Whitespace / control
    "enter": b"\r",
    "return": b"\r",
    "tab": b"\t",
    "backtab": CSI + b"Z",
    "space": b" ",
    "escape": ESC,
    "esc": ESC,
    "backspace": b"\x7f",
    "delete": CSI + b"3~",
    "insert": CSI + b"2~",
    # Arrows
    "up": CSI + b"A",
    "down": CSI + b"B",
    "right": CSI + b"C",
    "left": CSI + b"D",
    # Navigation
    "home": CSI + b"H",
    "end": CSI + b"F",
    "pageup": CSI + b"5~",
    "pagedown": CSI + b"6~",
    "pgup": CSI + b"5~",
    "pgdn": CSI + b"6~",
    # Function keys (xterm/vt-style - F1-F4 use SS3, F5+ use CSI ~)
    "f1": SS3 + b"P",
    "f2": SS3 + b"Q",
    "f3": SS3 + b"R",
    "f4": SS3 + b"S",
    "f5": CSI + b"15~",
    "f6": CSI + b"17~",
    "f7": CSI + b"18~",
    "f8": CSI + b"19~",
    "f9": CSI + b"20~",
    "f10": CSI + b"21~",
    "f11": CSI + b"23~",
    "f12": CSI + b"24~",
}

# Keys whose unmodified form is a CSI sequence ending in a single final
# letter (arrows, home, end). With modifiers they take ``CSI 1 ; M X``.
_CSI_LETTER_FINALS: Final[dict[str, bytes]] = {
    "up": b"A",
    "down": b"B",
    "right": b"C",
    "left": b"D",
    "home": b"H",
    "end": b"F",
}

# Keys whose unmodified form is ``CSI N ~``. With modifiers they become
# ``CSI N ; M ~``.
_CSI_TILDE_NUMS: Final[dict[str, int]] = {
    "insert": 2,
    "delete": 3,
    "pageup": 5,
    "pgup": 5,
    "pagedown": 6,
    "pgdn": 6,
    "f5": 15,
    "f6": 17,
    "f7": 18,
    "f8": 19,
    "f9": 20,
    "f10": 21,
    "f11": 23,
    "f12": 24,
}

# F1-F4 with modifiers use ``CSI 1 ; M X`` (X is P/Q/R/S).
_CSI_F1_F4_FINALS: Final[dict[str, bytes]] = {
    "f1": b"P",
    "f2": b"Q",
    "f3": b"R",
    "f4": b"S",
}


# -----------------------------------------------------------------------
# Key parser
# -----------------------------------------------------------------------


def _parse_combo(spec: str) -> tuple[Mod, str]:
    parts = [p.strip() for p in spec.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"empty key spec: {spec!r}")
    mods = Mod.NONE
    *mod_parts, key = parts
    for mp in mod_parts:
        m = _MOD_ALIASES.get(mp.lower())
        if m is None:
            raise ValueError(f"unknown modifier {mp!r} in {spec!r}")
        mods |= m
    # Named keys are case-insensitive ("Enter" == "enter"); single chars
    # preserve case so "A" works as the shifted form of "a".
    if len(key) != 1:
        key = key.lower()
    return mods, key


def encode_key(spec: str) -> bytes:
    """Encode a single key spec like ``"ctrl+shift+f5"`` or ``"enter"``.

    For single printable characters with no modifiers, returns the UTF-8
    bytes of the character. With ``ctrl``, maps to the corresponding
    control byte (``ctrl+a`` → ``\\x01``). With ``alt``, prefixes ESC.
    """
    mods, key = _parse_combo(spec)
    # Single printable character — common case for ctrl+letter, alt+letter.
    if len(key) == 1:
        ch = key
        if mods == Mod.NONE:
            return ch.encode("utf-8")
        if mods == Mod.SHIFT:
            return ch.upper().encode("utf-8")
        if mods == Mod.CTRL and "a" <= ch <= "z":
            return bytes([ord(ch) - ord("a") + 1])
        if mods == (Mod.CTRL | Mod.SHIFT) and "a" <= ch <= "z":
            # Most terminals collapse ctrl+shift+letter to ctrl+letter; we
            # follow that convention since the disambiguating kitty
            # protocol is out of scope for v0.1.
            return bytes([ord(ch) - ord("a") + 1])
        if mods == Mod.ALT:
            return ESC + ch.encode("utf-8")
        if mods == (Mod.ALT | Mod.SHIFT):
            return ESC + ch.upper().encode("utf-8")
        if mods == (Mod.ALT | Mod.CTRL) and "a" <= ch <= "z":
            return ESC + bytes([ord(ch) - ord("a") + 1])
        raise ValueError(f"unsupported modifier combo for char {ch!r}: {mods!r}")

    if key not in _NAMED_KEYS:
        raise ValueError(f"unknown key name: {key!r}")

    base = _NAMED_KEYS[key]
    if mods == Mod.NONE:
        return base

    # Apply xterm-style modifier encoding to named keys.
    param = _xterm_modifier_param(mods)
    if key in _CSI_LETTER_FINALS:
        return CSI + b"1;" + str(param).encode() + _CSI_LETTER_FINALS[key]
    if key in _CSI_TILDE_NUMS:
        n = _CSI_TILDE_NUMS[key]
        return CSI + str(n).encode() + b";" + str(param).encode() + b"~"
    if key in _CSI_F1_F4_FINALS:
        return CSI + b"1;" + str(param).encode() + _CSI_F1_F4_FINALS[key]
    # Fallback for things like ctrl+enter, ctrl+tab, ctrl+space — terminals
    # disagree. We mirror crossterm's defaults: ctrl+space → NUL, ctrl+enter
    # is sent as plain CR by most terminals (so just emit base).
    if key == "space" and mods == Mod.CTRL:
        return b"\x00"
    if key == "backspace" and mods == Mod.CTRL:
        return b"\x08"
    if key == "tab" and mods == Mod.SHIFT:
        return CSI + b"Z"
    return base


def _xterm_modifier_param(mods: Mod) -> int:
    bits = 0
    if Mod.SHIFT in mods:
        bits |= 1
    if Mod.ALT in mods:
        bits |= 2
    if Mod.CTRL in mods:
        bits |= 4
    if Mod.META in mods:
        bits |= 8
    return bits + 1


# -----------------------------------------------------------------------
# Mouse (SGR 1006)
# -----------------------------------------------------------------------


@dataclass(frozen=True)
class MouseButton:
    code: int


LEFT = MouseButton(0)
MIDDLE = MouseButton(1)
RIGHT = MouseButton(2)
WHEEL_UP = MouseButton(64)
WHEEL_DOWN = MouseButton(65)
WHEEL_LEFT = MouseButton(66)
WHEEL_RIGHT = MouseButton(67)

_BUTTON_ALIASES: Final[dict[str, MouseButton]] = {
    "left": LEFT,
    "middle": MIDDLE,
    "right": RIGHT,
    "wheel_up": WHEEL_UP,
    "wheelup": WHEEL_UP,
    "wheel_down": WHEEL_DOWN,
    "wheeldown": WHEEL_DOWN,
    "wheel_left": WHEEL_LEFT,
    "wheel_right": WHEEL_RIGHT,
}


def resolve_button(button: str | MouseButton) -> MouseButton:
    if isinstance(button, MouseButton):
        return button
    b = _BUTTON_ALIASES.get(button.lower())
    if b is None:
        raise ValueError(f"unknown mouse button: {button!r}")
    return b


def _mouse_modifier_bits(mods: Mod) -> int:
    bits = 0
    if Mod.SHIFT in mods:
        bits |= 4
    if Mod.ALT in mods:
        bits |= 8
    if Mod.CTRL in mods:
        bits |= 16
    return bits


def encode_mouse(
    *,
    button: str | MouseButton,
    row: int,
    col: int,
    pressed: bool = True,
    modifiers: Mod | tuple[str, ...] = Mod.NONE,
    motion: bool = False,
) -> bytes:
    """Encode a single SGR 1006 mouse event.

    Rows and columns are 1-based, matching the wire format. The session
    layer accepts 0-based coordinates and adds 1 before calling here.
    """
    btn = resolve_button(button)
    if isinstance(modifiers, tuple):
        mods = Mod.NONE
        for m in modifiers:
            mods |= _parse_combo(m)[0] if "+" in m else (_MOD_ALIASES.get(m.lower()) or Mod.NONE)
    else:
        mods = modifiers
    cb = btn.code | _mouse_modifier_bits(mods)
    if motion:
        cb |= 32
    final = b"M" if pressed else b"m"
    return CSI + b"<" + str(cb).encode() + b";" + str(col).encode() + b";" + str(row).encode() + final


# -----------------------------------------------------------------------
# Bracketed paste
# -----------------------------------------------------------------------

PASTE_START: Final[bytes] = CSI + b"200~"
PASTE_END: Final[bytes] = CSI + b"201~"


def encode_paste(text: str) -> bytes:
    payload = text.encode("utf-8")
    if PASTE_END in payload:
        raise ValueError(
            "paste payload contains the bracketed-paste end marker; "
            "this would break out of the paste and be a security smell. "
            "Use type() to send mixed content instead."
        )
    return PASTE_START + payload + PASTE_END


# -----------------------------------------------------------------------
# Focus events
# -----------------------------------------------------------------------

FOCUS_IN: Final[bytes] = CSI + b"I"
FOCUS_OUT: Final[bytes] = CSI + b"O"


def encode_focus(in_: bool) -> bytes:
    return FOCUS_IN if in_ else FOCUS_OUT
