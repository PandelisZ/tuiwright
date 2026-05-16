"""Layer 5: TuiSession — the user-facing async API.

This module is the only one most users interact with. The lower layers
(_pty, _emulator, _input, screen) are accessible but considered the
internal implementation.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tuiwright._emulator import Emulator
from tuiwright._input import (
    Mod,
    encode_focus,
    encode_key,
    encode_mouse,
    encode_paste,
    resolve_button,
)
from tuiwright._pty import PtyTransport
from tuiwright._trace.recorder import CastRecorder
from tuiwright.screen import Region, Screen

if TYPE_CHECKING:
    from re import Match


# Default poll interval for wait_for_* — small enough to feel instant,
# large enough to keep CPU at ~0 while idle.
_POLL_SECONDS = 0.02


class TuiTimeoutError(TimeoutError):
    """Raised when a ``wait_for_*`` call exceeds its timeout."""


@dataclass
class TuiConfig:
    cols: int = 80
    rows: int = 24
    default_timeout: float = 5.0
    poll_interval: float = _POLL_SECONDS
    stable_quiet_ms: int = 50
    agg_path: str | None = None  # Discovered lazily from PATH if None.
    cast_dir: Path | None = None  # Tempdir per session if None.
    strict_mouse: bool = False   # Raise instead of warning on mouse-mode mismatch.


# -----------------------------------------------------------------------
# Session
# -----------------------------------------------------------------------


class TuiSession:
    """Drives a TUI binary under a PTY.

    Use it as an async context manager or call :meth:`start` / :meth:`stop`
    explicitly. After start, every method that injects input is sync from
    the caller's perspective (no awaiting on the child) but ``async``
    because most flows interleave with ``await wait_for_*``.
    """

    def __init__(self, config: TuiConfig | None = None) -> None:
        self.config = config or TuiConfig()
        self._pty = PtyTransport()
        self._emu = Emulator(cols=self.config.cols, rows=self.config.rows)
        self._recorder: CastRecorder | None = None
        self._cast_path: Path | None = None
        self._started = False
        self._screen_changed = asyncio.Event()
        self._mouse_warned = False
        self._argv: list[str] = []

    # -- lifecycle -----------------------------------------------------

    async def __aenter__(self) -> TuiSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()

    async def start(
        self,
        cmd: str | list[str],
        *,
        env: dict[str, str] | None = None,
        cwd: str | os.PathLike[str] | None = None,
        cols: int | None = None,
        rows: int | None = None,
        cast_path: Path | str | None = None,
    ) -> None:
        if self._started:
            raise RuntimeError("session already started; create a new one")
        if cols is not None:
            self.config.cols = cols
        if rows is not None:
            self.config.rows = rows
        self._emu = Emulator(cols=self.config.cols, rows=self.config.rows)
        self._argv = shlex.split(cmd) if isinstance(cmd, str) else list(cmd)

        # Cast file: explicit > config.cast_dir > tempdir.
        if cast_path is not None:
            self._cast_path = Path(cast_path)
        else:
            base = self.config.cast_dir or Path(tempfile.gettempdir()) / "tuiwright"
            base.mkdir(parents=True, exist_ok=True)
            self._cast_path = base / f"session-{uuid.uuid4().hex[:12]}.cast"

        full_env = {**os.environ, **(env or {})}
        full_env.setdefault("TERM", "xterm-256color")
        full_env.setdefault("COLORTERM", "truecolor")
        # Disable any prompt-toolkit / pager that would mess with size.
        full_env.setdefault("PAGER", "cat")
        full_env.setdefault("LESS", "-FRX")

        self._recorder = CastRecorder(
            self._cast_path,
            cols=self.config.cols,
            rows=self.config.rows,
            env=full_env,
            title=" ".join(self._argv),
        )
        # Hook listeners BEFORE spawning so we don't miss the first chunk
        # (PTYs can emit data the same loop tick the reader is registered).
        self._pty.add_listener(self._on_output)
        await self._pty.spawn(
            self._argv,
            env=full_env,
            cwd=str(cwd) if cwd is not None else None,
            cols=self.config.cols,
            rows=self.config.rows,
        )
        self._started = True

    async def stop(self, *, timeout: float = 2.0) -> int:
        if not self._started:
            return 0
        try:
            return await self._pty.stop(timeout=timeout)
        finally:
            if self._recorder is not None:
                self._recorder.close()
            self._started = False

    # -- listeners -----------------------------------------------------

    def _on_output(self, chunk: bytes) -> None:
        self._emu.feed(chunk)
        if self._recorder is not None:
            self._recorder.record_output(chunk)
        # Wake any wait_for_* waiters.
        self._screen_changed.set()
        # Re-arm. A wait coroutine that consumed the event must rebuild
        # its reference before re-awaiting; we use a fresh Event each
        # tick to avoid races.
        self._screen_changed = asyncio.Event()

    def _record_input(self, data: bytes) -> None:
        if self._recorder is not None:
            self._recorder.record_input(data)

    # -- properties ----------------------------------------------------

    @property
    def screen(self) -> Screen:
        return Screen.from_emulator(self._emu)

    @property
    def cast_path(self) -> Path:
        if self._cast_path is None:
            raise RuntimeError("session not started yet")
        return self._cast_path

    @property
    def alive(self) -> bool:
        return self._pty.alive

    # -- input: keys / text --------------------------------------------

    async def press(self, key: str) -> None:
        self._require_started()
        data = encode_key(key)
        self._record_input(data)
        self._pty.write_bytes(data)
        await asyncio.sleep(0)  # let the loop service the write/read

    async def type(self, text: str, *, delay: float = 0.0) -> None:
        """Send each character as its UTF-8 bytes.

        ``delay`` is seconds between characters — useful for apps that
        debounce input or for emulating a human typist in demos.
        """
        self._require_started()
        if delay <= 0:
            data = text.encode("utf-8")
            self._record_input(data)
            self._pty.write_bytes(data)
            await asyncio.sleep(0)
            return
        for ch in text:
            data = ch.encode("utf-8")
            self._record_input(data)
            self._pty.write_bytes(data)
            await asyncio.sleep(delay)

    async def paste(self, text: str) -> None:
        self._require_started()
        if not self._emu.is_bracketed_paste():
            # The app didn't enable bracketed paste, so the brackets would
            # leak into the buffer. Fall back to plain type.
            await self.type(text)
            return
        data = encode_paste(text)
        self._record_input(data)
        self._pty.write_bytes(data)
        await asyncio.sleep(0)

    # -- input: mouse ---------------------------------------------------

    async def click(
        self,
        row: int,
        col: int,
        *,
        button: str = "left",
        modifiers: tuple[str, ...] = (),
    ) -> None:
        self._require_started()
        self._check_mouse_enabled()
        mods = _modtuple_to_mod(modifiers)
        # 0-based → 1-based on the wire.
        down = encode_mouse(
            button=button, row=row + 1, col=col + 1, pressed=True, modifiers=mods
        )
        up = encode_mouse(
            button=button, row=row + 1, col=col + 1, pressed=False, modifiers=mods
        )
        self._record_input(down + up)
        self._pty.write_bytes(down)
        # Small gap so apps that distinguish press/release see two events.
        await asyncio.sleep(0)
        self._pty.write_bytes(up)
        await asyncio.sleep(0)

    async def double_click(
        self, row: int, col: int, *, button: str = "left", interval: float = 0.05
    ) -> None:
        await self.click(row, col, button=button)
        await asyncio.sleep(interval)
        await self.click(row, col, button=button)

    async def drag(
        self,
        from_row: int,
        from_col: int,
        to_row: int,
        to_col: int,
        *,
        button: str = "left",
        steps: int = 4,
    ) -> None:
        self._require_started()
        self._check_mouse_enabled()
        btn = resolve_button(button)
        down = encode_mouse(button=btn, row=from_row + 1, col=from_col + 1, pressed=True)
        self._record_input(down)
        self._pty.write_bytes(down)
        await asyncio.sleep(0)
        for i in range(1, steps + 1):
            r = from_row + (to_row - from_row) * i // steps
            c = from_col + (to_col - from_col) * i // steps
            move = encode_mouse(
                button=btn, row=r + 1, col=c + 1, pressed=True, motion=True
            )
            self._record_input(move)
            self._pty.write_bytes(move)
            await asyncio.sleep(0)
        up = encode_mouse(button=btn, row=to_row + 1, col=to_col + 1, pressed=False)
        self._record_input(up)
        self._pty.write_bytes(up)
        await asyncio.sleep(0)

    async def scroll(
        self,
        row: int,
        col: int,
        *,
        direction: str = "down",
        lines: int = 1,
    ) -> None:
        self._require_started()
        self._check_mouse_enabled()
        button = "wheel_down" if direction == "down" else "wheel_up"
        for _ in range(lines):
            data = encode_mouse(button=button, row=row + 1, col=col + 1, pressed=True)
            self._record_input(data)
            self._pty.write_bytes(data)
            await asyncio.sleep(0)

    async def hover(self, row: int, col: int) -> None:
        self._require_started()
        self._check_mouse_enabled()
        # Motion-only event uses button code 3 (release) + motion bit (32).
        data = encode_mouse(
            button="left", row=row + 1, col=col + 1, pressed=True, motion=True
        )
        # Override button bits with 35 (3 + 32) for "no button motion".
        # The encoder doesn't expose that directly, so build it inline:
        from tuiwright._input import CSI
        msg = CSI + b"<35;" + str(col + 1).encode() + b";" + str(row + 1).encode() + b"M"
        self._record_input(msg)
        self._pty.write_bytes(msg)
        await asyncio.sleep(0)
        _ = data  # silence unused warning

    # -- input: resize / focus -----------------------------------------

    async def resize(self, cols: int, rows: int) -> None:
        self._require_started()
        self._pty.resize(cols, rows)
        self._emu.resize(cols, rows)
        self.config.cols = cols
        self.config.rows = rows
        await asyncio.sleep(0)

    async def focus(self, in_: bool = True) -> None:
        self._require_started()
        if not self._emu.is_focus_events():
            return  # No-op if the app didn't enable focus reporting.
        data = encode_focus(in_)
        self._record_input(data)
        self._pty.write_bytes(data)
        await asyncio.sleep(0)

    # -- waits ----------------------------------------------------------

    async def wait_for_text(
        self,
        needle: str | re.Pattern[str],
        *,
        timeout: float | None = None,
        region: Region | None = None,
        regex: bool = False,
    ) -> Match[str]:
        timeout = timeout if timeout is not None else self.config.default_timeout
        pattern = needle if isinstance(needle, re.Pattern) else (
            re.compile(needle) if regex else re.compile(re.escape(needle))
        )
        # A Region is a snapshot of one Screen. To keep polling honest, we
        # re-derive a Region with the same bounds (or title lookup) from
        # the current screen on every iteration.
        bounds = None if region is None else (region.title, region.top, region.bottom, region.left, region.right)

        def check() -> Match[str] | None:
            if bounds is None:
                target = self.screen.text
            else:
                title, top, bottom, left, right = bounds
                live_screen = self.screen
                if title is not None:
                    try:
                        live = live_screen.region(title=title)
                        target = live.text
                    except LookupError:
                        target = ""
                else:
                    target = "\n".join(
                        "".join(c.char for c in live_screen.cells[r][left:right]).rstrip()
                        for r in range(top, min(bottom, live_screen.rows))
                    )
            return pattern.search(target)

        return await self._poll_until(check, timeout=timeout, description=f"text {needle!r}")

    async def wait_for_predicate(
        self,
        predicate: Callable[[Screen], bool | Awaitable[bool]],
        *,
        timeout: float | None = None,
        description: str = "predicate",
    ) -> None:
        timeout = timeout if timeout is not None else self.config.default_timeout

        async def check() -> bool:
            res = predicate(self.screen)
            if asyncio.iscoroutine(res):
                res = await res
            return bool(res)

        await self._poll_until_async(check, timeout=timeout, description=description)

    async def wait_for_stable(
        self,
        *,
        quiet_ms: int | None = None,
        timeout: float | None = None,
    ) -> None:
        """Wait until no new output has arrived for ``quiet_ms``."""
        quiet = (quiet_ms if quiet_ms is not None else self.config.stable_quiet_ms) / 1000.0
        timeout = timeout if timeout is not None else self.config.default_timeout
        deadline = time.monotonic() + timeout
        last_rev = self._emu.revision
        last_change = time.monotonic()
        while True:
            await asyncio.sleep(self.config.poll_interval)
            now = time.monotonic()
            if self._emu.revision != last_rev:
                last_rev = self._emu.revision
                last_change = now
            elif now - last_change >= quiet:
                return
            if now >= deadline:
                raise TuiTimeoutError(
                    f"screen did not stabilise within {timeout}s "
                    f"(quiet_ms={int(quiet * 1000)})"
                )

    # -- queries / assertions ------------------------------------------

    def region(
        self,
        *,
        title: str | None = None,
        rows: tuple[int, int] | None = None,
        cols: tuple[int, int] | None = None,
    ) -> Region:
        return self.screen.region(title=title, rows=rows, cols=cols)

    async def assert_region(
        self,
        *,
        title: str | None = None,
        contains: str | re.Pattern[str] | None = None,
        rows: tuple[int, int] | None = None,
        cols: tuple[int, int] | None = None,
        regex: bool = False,
    ) -> None:
        reg = self.region(title=title, rows=rows, cols=cols)
        if contains is not None and not reg.contains(contains, regex=regex):
            raise AssertionError(
                f"region {title or (rows, cols)!r} does not contain {contains!r}.\n"
                f"--- region text ---\n{reg.text}\n--- end ---"
            )

    # -- rendering ------------------------------------------------------

    def png(self, *, out_path: Path | str | None = None, theme: str = "asciinema") -> bytes:
        """Render the current cast position to a PNG via ``agg``.

        Returns the PNG bytes; if ``out_path`` is given, also writes there.
        Raises :class:`FileNotFoundError` if ``agg`` is not installed.
        """
        if self._cast_path is None:
            raise RuntimeError("session not started")
        agg = self.config.agg_path or shutil.which("agg")
        if agg is None:
            raise FileNotFoundError(
                "agg (asciinema-agg) is not installed or not on PATH. "
                "Install via `cargo install --git https://github.com/asciinema/agg` "
                "or `brew install agg`, or set TuiConfig.agg_path."
            )
        # agg streams to stdout when given '-' as output, but the v1 CLI
        # requires a file argument. Use a tempfile.
        target = Path(out_path) if out_path else Path(tempfile.mkstemp(suffix=".png")[1])
        try:
            subprocess.run(
                [agg, "--theme", theme, "--cols", str(self.config.cols),
                 "--rows", str(self.config.rows), str(self._cast_path), str(target)],
                check=True,
                capture_output=True,
            )
            return target.read_bytes()
        finally:
            if out_path is None:
                try:
                    target.unlink()
                except OSError:
                    pass

    # -- internals ------------------------------------------------------

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("call start() before sending input")

    def _check_mouse_enabled(self) -> None:
        if self._emu.is_mouse_tracking():
            return
        if self.config.strict_mouse:
            raise RuntimeError(
                "mouse input sent but the app has not enabled mouse tracking "
                "(modes 1000/1002/1003). Set TuiConfig.strict_mouse=False to warn instead."
            )
        if not self._mouse_warned:
            import warnings
            warnings.warn(
                "Sending mouse event but the app has not enabled mouse tracking. "
                "The app likely won't see this input. Wait for the app to fully start.",
                stacklevel=3,
            )
            self._mouse_warned = True

    async def _poll_until(
        self,
        check: Callable[[], Any],
        *,
        timeout: float,
        description: str,
    ) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            result = check()
            if result:
                return result
            if time.monotonic() >= deadline:
                raise TuiTimeoutError(
                    f"timed out after {timeout}s waiting for {description}.\n"
                    f"--- last screen ---\n{self.screen.text}\n--- end ---"
                )
            try:
                await asyncio.wait_for(
                    self._screen_changed.wait(),
                    timeout=min(self.config.poll_interval, deadline - time.monotonic()),
                )
            except TimeoutError:
                pass

    async def _poll_until_async(
        self,
        check: Callable[[], Awaitable[bool]],
        *,
        timeout: float,
        description: str,
    ) -> None:
        deadline = time.monotonic() + timeout
        while True:
            if await check():
                return
            if time.monotonic() >= deadline:
                raise TuiTimeoutError(
                    f"timed out after {timeout}s waiting for {description}.\n"
                    f"--- last screen ---\n{self.screen.text}\n--- end ---"
                )
            try:
                await asyncio.wait_for(
                    self._screen_changed.wait(),
                    timeout=min(self.config.poll_interval, deadline - time.monotonic()),
                )
            except TimeoutError:
                pass


def _modtuple_to_mod(mods: tuple[str, ...]) -> Mod:
    from tuiwright._input import _MOD_ALIASES  # type: ignore[attr-defined]

    out = Mod.NONE
    for m in mods:
        v = _MOD_ALIASES.get(m.lower())
        if v is None:
            raise ValueError(f"unknown modifier {m!r}")
        out |= v
    return out
