"""Layer 1: async PTY transport built on ptyprocess.

Spawns a child process under a pseudo-terminal, exposes async reads via
``loop.add_reader``, and fans out incoming byte chunks to registered
listeners (the emulator and the cast recorder).

We deliberately stay below ``pexpect`` — it bundles regex/line semantics we
do not want for a full-screen TUI.
"""

from __future__ import annotations

import asyncio
import errno
import fcntl
import os
import signal
import struct
import termios
import tty
from collections.abc import Awaitable, Callable
from typing import Final

from ptyprocess import PtyProcess

_READ_CHUNK: Final[int] = 65536

ByteListener = Callable[[bytes], None]


class PtyTransport:
    """Async wrapper around a child process running under a PTY.

    Listeners registered via :meth:`add_listener` are invoked synchronously
    on the event loop thread each time a chunk of output bytes arrives.
    They MUST NOT block — push work to a task if needed.
    """

    def __init__(self) -> None:
        self._proc: PtyProcess | None = None
        self._fd: int = -1
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listeners: list[ByteListener] = []
        self._exited: asyncio.Event = asyncio.Event()
        self._exit_status: int | None = None

    # -- lifecycle ------------------------------------------------------

    async def spawn(
        self,
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        cols: int = 80,
        rows: int = 24,
    ) -> None:
        if self._proc is not None:
            raise RuntimeError("PtyTransport already spawned")
        self._loop = asyncio.get_running_loop()
        self._proc = PtyProcess.spawn(
            argv,
            env=env,
            cwd=cwd,
            dimensions=(rows, cols),
            echo=False,
        )
        self._fd = self._proc.fd
        # Ensure non-blocking reads — ptyprocess does not guarantee this.
        flags = fcntl.fcntl(self._fd, fcntl.F_GETFL)
        fcntl.fcntl(self._fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        # Put the slave PTY's line discipline in raw mode. Without this,
        # bytes we write are mangled by the kernel on the way to the
        # child — e.g. DEL (0x7f) triggers VERASE and is silently dropped
        # if the child is briefly in cooked mode during startup, and
        # IXON treats Ctrl-S as XOFF. Raw mode disables ALL of that so
        # what we write is exactly what the child reads.
        _set_raw_mode(self._fd)
        self._loop.add_reader(self._fd, self._on_readable)

    async def stop(self, *, timeout: float = 2.0) -> int:
        """Graceful stop: SIGTERM, wait up to ``timeout``, then SIGKILL."""
        if self._proc is None:
            return self._exit_status or 0
        if not self._exited.is_set():
            try:
                self._proc.kill(signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(self._exited.wait(), timeout=timeout)
            except TimeoutError:
                try:
                    self._proc.kill(signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    await asyncio.wait_for(self._exited.wait(), timeout=1.0)
                except TimeoutError:
                    pass
        self._teardown()
        return self._exit_status or 0

    # -- listeners ------------------------------------------------------

    def add_listener(self, listener: ByteListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: ByteListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    # -- IO -------------------------------------------------------------

    def write_bytes(self, data: bytes) -> None:
        if self._proc is None or self._fd < 0:
            raise RuntimeError("PtyTransport not running")
        # PTYs may report partial writes under pressure; loop until done.
        view = memoryview(data)
        total = 0
        while total < len(view):
            try:
                n = os.write(self._fd, view[total:])
            except BlockingIOError:
                # The PTY's input buffer is full; yield briefly via the loop.
                # In practice this is rare for keyboard-rate input.
                continue
            if n <= 0:
                break
            total += n

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is None or self._fd < 0:
            raise RuntimeError("PtyTransport not running")
        winsz = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self._fd, termios.TIOCSWINSZ, winsz)
        # ptyprocess sends SIGWINCH automatically via setwinsize, but ioctl
        # alone is sufficient on macOS and Linux — the kernel notifies the
        # process group.

    # -- properties -----------------------------------------------------

    @property
    def alive(self) -> bool:
        return self._proc is not None and not self._exited.is_set()

    @property
    def exit_status(self) -> int | None:
        return self._exit_status

    def wait_exit(self) -> Awaitable[None]:
        return self._exited.wait()

    # -- internals ------------------------------------------------------

    def _on_readable(self) -> None:
        if self._fd < 0:
            return
        try:
            chunk = os.read(self._fd, _READ_CHUNK)
        except BlockingIOError:
            return
        except OSError as exc:
            # EIO is the normal "child closed the PTY" signal on Linux/macOS.
            if exc.errno in (errno.EIO, errno.EBADF):
                self._on_child_exit()
                return
            raise
        if not chunk:
            self._on_child_exit()
            return
        for listener in list(self._listeners):
            listener(chunk)

    def _on_child_exit(self) -> None:
        if self._exited.is_set():
            return
        if self._loop is not None and self._fd >= 0:
            try:
                self._loop.remove_reader(self._fd)
            except (ValueError, OSError):
                pass
        if self._proc is not None:
            try:
                self._proc.wait()
                self._exit_status = self._proc.exitstatus or 0
            except OSError:
                self._exit_status = -1
        self._exited.set()

    # -- module-level helpers ------------------------------------------

    def _teardown(self) -> None:
        if self._loop is not None and self._fd >= 0:
            try:
                self._loop.remove_reader(self._fd)
            except (ValueError, OSError):
                pass
        if self._proc is not None:
            try:
                self._proc.close(force=True)
            except OSError:
                pass
        self._fd = -1
        self._proc = None


def _set_raw_mode(fd: int) -> None:
    """Configure the PTY's line discipline to pass bytes through verbatim.

    ``tty.setraw`` does what we want — clears ECHO, ICANON, IXON,
    ICRNL, etc. — but is normally called on a controlling terminal.
    It works on a PTY master too because the kernel applies the line
    discipline between master and slave.
    """
    try:
        tty.setraw(fd, termios.TCSANOW)
    except termios.error:
        # If the fd isn't a TTY (rare — we just opened it from ptyprocess),
        # there's nothing to configure. Silent best-effort.
        pass
