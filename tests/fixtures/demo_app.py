"""A small self-contained TUI used by the tuiwright self-test suite.

Why hand-rolled instead of urwid/textual? The fixture app should be
fully deterministic, free of third-party rendering quirks, and small
enough to read in one screen. We talk to stdin/stdout directly via
ANSI escape sequences.

Behaviour:

- On start: enters alt screen, enables mouse SGR (1006), bracketed
  paste (2004), focus events (1004), hides cursor. Renders "Ready"
  banner and an empty echo buffer.
- Typed text accumulates in the echo buffer (line 3).
- Enter inserts a newline into the buffer.
- Backspace removes the last character.
- Ctrl-S sets status to "Saved".
- Ctrl-R triggers a refresh (no visible change; useful for stability).
- 'q' quits (without modifiers).
- Mouse clicks log to line 6 as "click R=<row> C=<col>".
- Mouse wheel logs as "wheel up/down".
- Bracketed paste appends as one chunk and logs "paste N=<bytes>".
- Focus events log "focus in/out".
- Resize triggers re-render to new dimensions.

Run directly: ``python demo_app.py``.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import signal
import sys
import termios
import tty
from dataclasses import dataclass, field

# -- ANSI helpers ------------------------------------------------------

ESC = "\x1b"
CSI = ESC + "["


def write(*parts: str) -> None:
    sys.stdout.write("".join(parts))
    sys.stdout.flush()


def cls() -> None:
    write(CSI + "2J", CSI + "H")


def move(row: int, col: int) -> None:
    # 1-based
    write(CSI + f"{row};{col}H")


def setup_terminal() -> None:
    write(
        CSI + "?1049h",   # alt screen
        CSI + "?25l",     # hide cursor
        CSI + "?1006h",   # SGR mouse
        CSI + "?1002h",   # button-event mouse (motion while pressed)
        CSI + "?2004h",   # bracketed paste
        CSI + "?1004h",   # focus events
    )
    cls()


def teardown_terminal() -> None:
    write(
        CSI + "?1004l",
        CSI + "?2004l",
        CSI + "?1002l",
        CSI + "?1006l",
        CSI + "?25h",
        CSI + "?1049l",
    )


def get_size() -> tuple[int, int]:
    size = shutil.get_terminal_size((80, 24))
    return size.columns, size.lines


# -- State -------------------------------------------------------------


@dataclass
class State:
    cols: int = 80
    rows: int = 24
    status: str = "Ready"
    buffer: str = ""
    events: list[str] = field(default_factory=list)
    quitting: bool = False


def render(s: State) -> None:
    cls()
    # Status line (line 1).
    move(1, 1)
    write(s.status.ljust(s.cols))
    # Hint line (line 2).
    move(2, 1)
    write("Press 'q' to quit. Ctrl-S to save. " + f"size={s.cols}x{s.rows}")
    # Echo buffer header (line 3).
    move(3, 1)
    write("Echo:")
    # Buffer contents (lines 4-5; wraps after first line).
    move(4, 1)
    write(s.buffer[: s.cols])
    if len(s.buffer) > s.cols:
        move(5, 1)
        write(s.buffer[s.cols : 2 * s.cols])
    # Event log header (line 6).
    move(6, 1)
    write("Events:")
    # Last 5 events (lines 7-11).
    recent = s.events[-5:]
    for i, ev in enumerate(recent):
        move(7 + i, 1)
        write(ev[: s.cols])


# -- Input parsing ----------------------------------------------------

# SGR mouse: ESC [ < Cb ; Cx ; Cy (M|m)
_MOUSE_SGR_RE = re.compile(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
_PASTE_START = b"\x1b[200~"
_PASTE_END = b"\x1b[201~"
_FOCUS_IN = b"\x1b[I"
_FOCUS_OUT = b"\x1b[O"


def parse_chunk(buf: bytes, s: State) -> bytes:
    """Consume parseable prefixes of ``buf`` into state; return leftover."""
    i = 0
    while i < len(buf):
        b = buf[i : i + 1]
        # Bracketed paste
        if buf[i:].startswith(_PASTE_START):
            end = buf.find(_PASTE_END, i + len(_PASTE_START))
            if end == -1:
                return buf[i:]
            payload = buf[i + len(_PASTE_START) : end]
            s.buffer += payload.decode("utf-8", "replace")
            s.events.append(f"paste N={len(payload)}")
            i = end + len(_PASTE_END)
            continue
        # Focus
        if buf[i:].startswith(_FOCUS_IN):
            s.events.append("focus in")
            i += len(_FOCUS_IN)
            continue
        if buf[i:].startswith(_FOCUS_OUT):
            s.events.append("focus out")
            i += len(_FOCUS_OUT)
            continue
        # Mouse SGR
        m = _MOUSE_SGR_RE.match(buf, i)
        if m:
            cb, cx, cy, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
            if kind == b"M":
                if cb == 64:
                    s.events.append("wheel up")
                elif cb == 65:
                    s.events.append("wheel down")
                elif cb & ~0x1F == 0 and cb in (0, 1, 2):  # normal press
                    names = {0: "left", 1: "middle", 2: "right"}
                    s.events.append(f"click {names[cb]} R={cy} C={cx}")
            i = m.end()
            continue
        # Other CSI escape — consume until letter / ~ to avoid partial garbage.
        if buf[i:].startswith(b"\x1b["):
            j = i + 2
            while j < len(buf) and not (0x40 <= buf[j] <= 0x7E):
                j += 1
            if j < len(buf):
                i = j + 1
                continue
            return buf[i:]
        # Plain control / printable byte
        if b == b"q":
            s.quitting = True
            return b""
        if b == b"\x13":  # Ctrl-S
            s.status = "Saved"
            i += 1
            continue
        if b == b"\x12":  # Ctrl-R
            i += 1
            continue
        if b == b"\r" or b == b"\n":
            s.buffer += "\n"
            i += 1
            continue
        if b == b"\x7f":  # Backspace
            if s.buffer:
                s.buffer = s.buffer[:-1]
            i += 1
            continue
        if b == b"\x1b":
            # Lone ESC; skip.
            i += 1
            continue
        # Printable
        try:
            ch = b.decode("utf-8")
            if ch.isprintable() or ch == " ":
                s.buffer += ch
        except UnicodeDecodeError:
            pass
        i += 1
    return b""


# -- Main loop --------------------------------------------------------


def main() -> None:
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    # Disable software flow control so Ctrl-S and Ctrl-Q reach the app.
    attrs = termios.tcgetattr(fd)
    attrs[0] &= ~(termios.IXON | termios.IXOFF | termios.IXANY)  # iflag
    attrs[0] &= ~termios.ICRNL  # don't translate CR→NL on input
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    try:
        setup_terminal()
        cols, rows = get_size()
        state = State(cols=cols, rows=rows)

        def on_resize(_sig: int, _frame: object) -> None:
            c, r = get_size()
            state.cols = c
            state.rows = r
            render(state)

        signal.signal(signal.SIGWINCH, on_resize)

        render(state)
        leftover = b""
        while not state.quitting:
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
                leftover = parse_chunk(leftover + chunk, state)
                render(state)
    finally:
        teardown_terminal()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
