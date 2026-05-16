"""Integration test for the interactive recorder bridge.

The bridge is normally driven by a human at a real terminal. To exercise
it from a test runner we open our own PTY pair, hand the slave fd to the
bridge as its "stdin" / "stdout", and write canned input from the master.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pty
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

DEMO_APP = Path(__file__).parent / "fixtures" / "demo_app.py"


async def _read_until(fd: int, needle: bytes, *, timeout: float = 5.0) -> bytes:
    """Read from fd until ``needle`` appears or timeout. Returns all bytes seen."""
    loop = asyncio.get_running_loop()
    buf = bytearray()
    done = asyncio.Event()

    def on_readable() -> None:
        try:
            chunk = os.read(fd, 4096)
        except (BlockingIOError, OSError):
            return
        if chunk:
            buf.extend(chunk)
            if needle in buf:
                done.set()
        else:
            done.set()

    import fcntl
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    loop.add_reader(fd, on_readable)
    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    finally:
        loop.remove_reader(fd)
    return bytes(buf)


async def test_bridge_records_to_cast(tmp_path: Path) -> None:
    """Drive the bridge against the demo app; verify the resulting cast."""
    from tuiwright._record.bridge import record_session

    # Open a PTY pair: master = us (the "user"), slave = bridge's stdin/stdout.
    master, slave = pty.openpty()
    cast_path = tmp_path / "session.cast"

    # Run the bridge in a background task.
    task = asyncio.create_task(
        record_session(
            [sys.executable, str(DEMO_APP)],
            cast_path,
            stdin_fd=slave,
            stdout_fd=slave,
            cols=80,
            rows=24,
            show_banner=False,
        )
    )

    try:
        # Wait for the demo app's startup banner.
        await _read_until(master, b"Ready", timeout=5)
        # Type some text and ctrl+S.
        os.write(master, b"hello\x13")  # \x13 = ctrl+s -> demo sets status=Saved
        await _read_until(master, b"Saved", timeout=3)
        # Trigger the hotkey menu and snapshot.
        os.write(master, b"\x1ds")  # Ctrl+] then s
        await asyncio.sleep(0.1)
        # Quit via the bridge menu.
        os.write(master, b"\x1dq")  # Ctrl+] then q
        # Wait for the bridge to finish.
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        os.close(master)
        with contextlib.suppress(OSError):
            os.close(slave)

    # Assert the cast file looks right.
    assert cast_path.is_file()
    with cast_path.open() as fh:
        header = json.loads(fh.readline())
        events = [json.loads(line) for line in fh if line.strip()]
    assert header["version"] == 2
    assert header["width"] == 80
    assert header["height"] == 24

    kinds = [ev[1] for ev in events]
    assert "i" in kinds, "no user input was recorded"
    assert "o" in kinds, "no app output was recorded"
    assert "m" in kinds, "Ctrl+] s did not insert a marker"

    # The recorded inputs should include the typed text and ctrl+s — and
    # they should *not* include the hotkey bytes (those are intercepted).
    inputs = b"".join(ev[2].encode("utf-8", "replace") for ev in events if ev[1] == "i")
    assert b"hello" in inputs
    assert b"\x13" in inputs
    assert b"\x1d" not in inputs, "hotkey byte must not be forwarded to the child"


async def test_bridge_then_codegen_runnable(tmp_path: Path) -> None:
    """End-to-end: record → codegen → resulting test is syntactically valid."""
    from tuiwright._record.bridge import record_session
    from tuiwright._record.codegen import generate_test

    master, slave = pty.openpty()
    cast_path = tmp_path / "session.cast"

    task = asyncio.create_task(
        record_session(
            [sys.executable, str(DEMO_APP)],
            cast_path,
            stdin_fd=slave,
            stdout_fd=slave,
            cols=80,
            rows=24,
            show_banner=False,
        )
    )

    try:
        await _read_until(master, b"Ready", timeout=5)
        os.write(master, b"hi")
        await _read_until(master, b"hi", timeout=3)
        os.write(master, b"\x1dq")
        await asyncio.wait_for(task, timeout=5)
    finally:
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        os.close(master)
        with contextlib.suppress(OSError):
            os.close(slave)

    src = generate_test(cast_path, command=[sys.executable, str(DEMO_APP)])
    import ast
    ast.parse(src)
    assert "tui.type(" in src
    assert "async def test_recorded" in src
