"""Interactive recorder bridge.

Spawns a TUI under a PTY sized to match the user's real terminal, then
transparently forwards stdin and stdout between the user and the child
while teeing everything to an asciinema v2 cast file.

A reserved hotkey (default Ctrl+], the telnet escape) drops into a tiny
menu mode where the user can:

- ``s`` — insert a snapshot marker at this point in the cast
- ``q`` — stop recording (graceful child shutdown)
- ``l`` — insert a labeled marker (label = next line until Enter)

Anything else cancels menu mode silently.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import sys
import termios
import time
import tty
from collections.abc import Sequence
from pathlib import Path

from tuiwright._pty import PtyTransport
from tuiwright._trace.recorder import CastRecorder

# Telnet escape — unlikely to clash with normal TUI use.
DEFAULT_HOTKEY: int = 0x1D

_MENU_SNAPSHOT = ord("s")
_MENU_QUIT = ord("q")
_MENU_LABEL = ord("l")
_MENU_HELP = ord("?")


# ANSI for the help banner shown at the bottom of the user's terminal.
_HELP_BANNER = (
    "\x1b[7m tuiwright record \x1b[0m  "
    "hotkey \x1b[1mCtrl+]\x1b[0m then \x1b[1ms\x1b[0m snapshot · "
    "\x1b[1ml\x1b[0m label · \x1b[1mq\x1b[0m stop · \x1b[1m?\x1b[0m help"
)


async def record_session(
    argv: Sequence[str],
    cast_path: Path | str,
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    cols: int | None = None,
    rows: int | None = None,
    hotkey: int = DEFAULT_HOTKEY,
    stdin_fd: int | None = None,
    stdout_fd: int | None = None,
    show_banner: bool = True,
) -> int:
    """Run ``argv`` interactively and record the session.

    Returns the child's exit status. Restores the user's terminal state
    on exit even if an exception is raised.
    """
    cast_path = Path(cast_path)
    cast_path.parent.mkdir(parents=True, exist_ok=True)
    if stdin_fd is None:
        stdin_fd = sys.stdin.fileno()
    if stdout_fd is None:
        stdout_fd = sys.stdout.fileno()
    if cols is None or rows is None:
        size = shutil.get_terminal_size((80, 24))
        cols = cols or size.columns
        rows = rows or size.lines

    full_env = {**os.environ, **(env or {})}
    full_env.setdefault("TERM", "xterm-256color")
    full_env.setdefault("COLORTERM", "truecolor")

    pty = PtyTransport()
    recorder = CastRecorder(
        cast_path,
        cols=cols,
        rows=rows,
        env=full_env,
        title=" ".join(argv),
    )

    if show_banner:
        _print_banner(stdout_fd)

    # Forward every output chunk to the user's terminal AND record it.
    def on_output(chunk: bytes) -> None:
        os.write(stdout_fd, chunk)
        recorder.record_output(chunk)

    pty.add_listener(on_output)
    await pty.spawn(list(argv), env=full_env, cwd=cwd, cols=cols, rows=rows)

    # Put the user's tty in raw mode so all keystrokes (incl. control codes)
    # reach us byte-by-byte.
    old_attrs = termios.tcgetattr(stdin_fd)
    tty.setraw(stdin_fd)

    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    state = _BridgeState(hotkey=hotkey, recorder=recorder, pty=pty, stopping=stopping, stdout_fd=stdout_fd)

    def on_stdin() -> None:
        try:
            data = os.read(stdin_fd, 4096)
        except (BlockingIOError, OSError):
            return
        if not data:
            stopping.set()
            return
        state.feed(data)

    def on_winch() -> None:
        size = shutil.get_terminal_size((cols, rows))
        try:
            pty.resize(size.columns, size.lines)
        except OSError:
            pass

    loop.add_reader(stdin_fd, on_stdin)
    try:
        loop.add_signal_handler(signal.SIGWINCH, on_winch)
    except NotImplementedError:
        pass  # not available on Windows / inside some test runners

    # Watch the child — if it exits on its own, stop too.
    async def watch_child() -> None:
        await pty.wait_exit()
        stopping.set()

    watcher = asyncio.create_task(watch_child())

    try:
        await stopping.wait()
    finally:
        # Drain any pending input.
        state.flush()
        watcher.cancel()
        loop.remove_reader(stdin_fd)
        try:
            loop.remove_signal_handler(signal.SIGWINCH)
        except (NotImplementedError, ValueError):
            pass
        await pty.stop(timeout=2.0)
        recorder.close()
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_attrs)

    return pty.exit_status or 0


# ---------------------------------------------------------------------------
# Bridge state machine
# ---------------------------------------------------------------------------


class _BridgeState:
    """Tracks per-byte state for the stdin forwarder.

    Pulled out so the hotkey / menu / label-collection state isn't tangled
    in the asyncio reader closure.
    """

    def __init__(
        self,
        *,
        hotkey: int,
        recorder: CastRecorder,
        pty: PtyTransport,
        stopping: asyncio.Event,
        stdout_fd: int,
    ) -> None:
        self._hotkey = hotkey
        self._recorder = recorder
        self._pty = pty
        self._stopping = stopping
        self._stdout_fd = stdout_fd
        self._menu = False
        self._collecting_label = False
        self._label_buf = bytearray()

    def feed(self, data: bytes) -> None:
        forward = bytearray()
        for b in data:
            if self._collecting_label:
                if b in (0x0A, 0x0D):  # newline ends the label
                    label = self._label_buf.decode("utf-8", "replace").strip() or "labeled"
                    self._recorder.mark(label)
                    self._label_buf.clear()
                    self._collecting_label = False
                    self._notice(f" label: {label} ")
                elif b == 0x1B:  # ESC cancels
                    self._label_buf.clear()
                    self._collecting_label = False
                    self._notice(" label cancelled ")
                elif b == 0x7F or b == 0x08:  # backspace
                    if self._label_buf:
                        self._label_buf.pop()
                else:
                    self._label_buf.append(b)
                continue

            if self._menu:
                self._handle_menu(b)
                self._menu = False
                continue

            if b == self._hotkey:
                self._menu = True
                continue

            forward.append(b)

        if forward:
            payload = bytes(forward)
            self._recorder.record_input(payload)
            self._pty.write_bytes(payload)

    def flush(self) -> None:
        """Called on shutdown to ensure no dangling state."""
        self._menu = False
        if self._collecting_label and self._label_buf:
            label = self._label_buf.decode("utf-8", "replace").strip()
            if label:
                self._recorder.mark(label)
        self._label_buf.clear()
        self._collecting_label = False

    def _handle_menu(self, b: int) -> None:
        if b == _MENU_SNAPSHOT:
            self._recorder.mark("snapshot")
            self._notice(" ✓ snapshot ")
        elif b == _MENU_QUIT:
            self._notice(" stopping... ")
            self._stopping.set()
        elif b == _MENU_LABEL:
            self._collecting_label = True
            self._notice(" label > ")
        elif b == _MENU_HELP:
            self._notice(_HELP_BANNER)
        # Other bytes silently cancel the menu.

    def _notice(self, text: str) -> None:
        """Briefly flash text in the user's terminal status area.

        We can't reliably know where the cursor is, so we save the
        cursor, scroll up one line, write at the bottom, restore.
        """
        # \x1b7 = save cursor; \x1b[s alt
        # \x1b[?47h would alt-screen but TUIs already use that.
        # Simplest non-invasive: write to stderr (most TUIs don't paint there).
        try:
            os.write(2, ("\x1b[7m" + text + "\x1b[0m\x1b[K\n").encode("utf-8"))
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def _print_banner(stdout_fd: int) -> None:
    msg = (
        "\x1b[2J\x1b[H"
        "tuiwright is recording your session.\r\n"
        "    Drive the app as you normally would.\r\n"
        "    Press Ctrl+] then s to snapshot, l to label, q to stop.\r\n"
        "\r\n"
        "Starting in 1 second...\r\n"
    )
    try:
        os.write(stdout_fd, msg.encode("utf-8"))
    except OSError:
        pass
    time.sleep(1.0)
