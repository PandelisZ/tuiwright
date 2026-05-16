# Hello, TUI

A complete walkthrough: build a tiny TUI, then write a test suite that
exercises every input type tuiwright supports. No external TUI library
needed.

## The app

```python title="hello_tui.py" linenums="1"
import os
import select
import signal
import shutil
import sys
import termios
import tty

ESC = "\x1b"
CSI = ESC + "["


def write(*parts):
    sys.stdout.write("".join(parts))
    sys.stdout.flush()


def setup():
    write(
        CSI + "?1049h",   # alt screen
        CSI + "?25l",     # hide cursor
        CSI + "?1006h",   # SGR mouse
        CSI + "?2004h",   # bracketed paste
        CSI + "?1004h",   # focus events
    )


def teardown():
    write(CSI + "?1004l", CSI + "?2004l", CSI + "?1006l",
          CSI + "?25h", CSI + "?1049l")


def render(state):
    write(CSI + "2J", CSI + "H")           # clear + home
    write(state["status"], "\r\n")
    write("typed: " + state["buf"], "\r\n")
    write("last: " + state["last"], "\r\n")


def main():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    setup()
    state = {"status": "Ready (q to quit)", "buf": "", "last": ""}
    try:
        render(state)
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.05)
            if not r:
                continue
            chunk = os.read(fd, 4096)
            if b"q" in chunk:
                break
            if chunk == b"\x13":            # ctrl+s
                state["status"] = "Saved"
            elif chunk.startswith(b"\x1b[<"):
                state["last"] = f"mouse {chunk[3:].decode(errors='replace')!r}"
            elif chunk.startswith(b"\x1b[200~"):
                state["last"] = f"paste {len(chunk)} bytes"
            elif chunk == b"\x1b[I":
                state["last"] = "focus in"
            elif chunk == b"\x1b[O":
                state["last"] = "focus out"
            else:
                state["buf"] += chunk.decode(errors="replace")
                state["last"] = "typed"
            render(state)
    finally:
        teardown()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    main()
```

## The test suite

```python title="tests/test_hello.py" linenums="1"
import sys
from pathlib import Path

import pytest
from tuiwright import TuiSession

APP = [sys.executable, str(Path(__file__).parent.parent / "hello_tui.py")]
pytestmark = pytest.mark.asyncio


async def test_startup_banner(tui: TuiSession):
    await tui.start(APP, cols=60, rows=12)
    await tui.wait_for_text("Ready")


async def test_typing(tui: TuiSession):
    await tui.start(APP)
    await tui.wait_for_text("Ready")
    await tui.type("hello")
    await tui.wait_for_text("typed: hello")


async def test_ctrl_s_saves(tui: TuiSession):
    await tui.start(APP)
    await tui.wait_for_text("Ready")
    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")


async def test_mouse_click(tui: TuiSession):
    await tui.start(APP)
    await tui.wait_for_text("Ready")
    await tui.wait_for_predicate(
        lambda _: tui._emu.is_mouse_tracking(),
        timeout=2,
    )
    await tui.click(row=5, col=10)
    await tui.wait_for_text("mouse")


async def test_paste(tui: TuiSession):
    await tui.start(APP)
    await tui.wait_for_text("Ready")
    await tui.wait_for_predicate(
        lambda _: tui._emu.is_bracketed_paste(),
        timeout=2,
    )
    await tui.paste("from clipboard")
    await tui.wait_for_text("paste")


async def test_resize(tui: TuiSession):
    await tui.start(APP, cols=80, rows=24)
    await tui.wait_for_text("Ready")
    await tui.resize(120, 40)
    await tui.wait_for_stable(quiet_ms=100)
    assert tui.alive
```

## Run it

```bash
uv run pytest tests/ -v
```

All six tests should pass in under five seconds. Now you have a
template for testing your own TUI: the same `tui.start` → `wait_for_*`
→ `press` / `click` / `paste` pattern applies to any binary that
talks to a terminal.

## Where to go next

- The [Concepts](concepts/architecture.md) section explains how the
  six layers fit together.
- The [Input](input/keys.md) section has the full reference for every
  key, mouse button, and modifier combination.
- The [Guides](guides/writing-tests.md) cover the patterns that scale
  to real-world test suites.
