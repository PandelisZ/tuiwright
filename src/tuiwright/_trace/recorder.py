"""Asciinema cast v2 recorder.

Writes a file that asciinema's ``agg`` CLI can render to PNG / GIF, and
that asciinema-player can replay in a browser. Format spec:

    https://docs.asciinema.org/manual/asciicast/v2/

A cast is a JSON header followed by newline-delimited JSON event arrays
``[seconds_since_start, "o" | "i", data_string]``.

We tap into the PTY byte stream (output) and into the session's input
encoders (input echo) so the trace replay shows what the user "typed".
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import IO, Final

CAST_VERSION: Final[int] = 2


class CastRecorder:
    """Writes an asciinema cast v2 file.

    The recorder owns the file handle; call :meth:`close` to flush.
    Use :meth:`record_output` for bytes from the PTY (what the app
    printed) and :meth:`record_input` for what the test driver sent.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        cols: int,
        rows: int,
        env: dict[str, str] | None = None,
        title: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: IO[str] = self.path.open("w", encoding="utf-8", buffering=1)
        self._t0 = time.monotonic()
        header: dict[str, object] = {
            "version": CAST_VERSION,
            "width": cols,
            "height": rows,
            "timestamp": int(time.time()),
        }
        if title:
            header["title"] = title
        if env:
            # Filter to the keys asciinema-player understands so the file
            # stays small; arbitrary keys are allowed by the spec.
            keep = {k: v for k, v in env.items() if k in ("SHELL", "TERM")}
            if keep:
                header["env"] = keep
        self._fh.write(json.dumps(header, separators=(",", ":")) + "\n")

    # -- public ---------------------------------------------------------

    def record_output(self, chunk: bytes) -> None:
        self._emit("o", chunk)

    def record_input(self, chunk: bytes) -> None:
        self._emit("i", chunk)

    def mark(self, label: str) -> None:
        """Insert a marker event (asciinema v2 uses ``"m"`` for markers)."""
        elapsed = time.monotonic() - self._t0
        self._fh.write(
            json.dumps([round(elapsed, 6), "m", label], separators=(",", ":")) + "\n"
        )

    def close(self) -> None:
        if not self._fh.closed:
            try:
                self._fh.flush()
                os.fsync(self._fh.fileno())
            except OSError:
                pass
            self._fh.close()

    # -- context manager ------------------------------------------------

    def __enter__(self) -> CastRecorder:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- internals ------------------------------------------------------

    def _emit(self, kind: str, chunk: bytes) -> None:
        if not chunk or self._fh.closed:
            return
        elapsed = time.monotonic() - self._t0
        # asciinema requires UTF-8 text for the data field; replace errors
        # so binary noise doesn't crash the recorder mid-test.
        text = chunk.decode("utf-8", errors="replace")
        self._fh.write(
            json.dumps([round(elapsed, 6), kind, text], separators=(",", ":")) + "\n"
        )
