"""``tuiwright`` command-line entry point.

Subcommands:

- ``record`` — run a TUI interactively and record to an asciinema cast
- ``codegen`` — turn a cast into a pytest test file
- ``replay`` — replay a recorded cast against a fresh spawn (no
  assertions; useful for demos and debugging)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from tuiwright import __version__


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuiwright",
        description="Playwright-style end-to-end testing for TUI applications.",
    )
    parser.add_argument("--version", action="version", version=f"tuiwright {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    # ----- record ----------------------------------------------------
    p_record = sub.add_parser(
        "record",
        help="Run a TUI interactively and record the session to a cast file.",
        description=(
            "Spawns CMD under a pseudo-terminal sized to your real terminal, "
            "forwards your keystrokes + mouse + resize transparently, and tees "
            "everything to an asciinema v2 cast file. Press Ctrl+] then s to "
            "snapshot, l to label, q to stop."
        ),
    )
    p_record.add_argument(
        "-c", "--cast",
        type=Path,
        default=None,
        help="Where to write the cast file (default: ./session-<timestamp>.cast).",
    )
    p_record.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Also generate a pytest test file at this path on exit.",
    )
    p_record.add_argument(
        "--test-name",
        default="test_recorded",
        help="Name of the generated test function (default: test_recorded).",
    )
    p_record.add_argument(
        "--style",
        choices=["coarse", "faithful", "hybrid"],
        default="coarse",
        help="Codegen style for the generated test (default: coarse).",
    )
    p_record.add_argument(
        "--settle-ms",
        type=int,
        default=120,
        help="Milliseconds of output silence that count as 'settled' (default: 120).",
    )
    p_record.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="The command (and arguments) to spawn. Prefix with -- if it starts with flags.",
    )
    p_record.set_defaults(_handler=_cmd_record)

    # ----- codegen ---------------------------------------------------
    p_codegen = sub.add_parser(
        "codegen",
        help="Generate a pytest test file from an existing cast.",
        description=(
            "Walks the cast events and emits a complete pytest async test "
            "with high-level press/type/click/wait_for_text calls."
        ),
    )
    p_codegen.add_argument(
        "-i", "--input",
        type=Path,
        required=True,
        help="Path to the asciinema v2 cast file.",
    )
    p_codegen.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Write the test here. Defaults to stdout.",
    )
    p_codegen.add_argument(
        "--test-name",
        default="test_recorded",
        help="Name of the generated test function (default: test_recorded).",
    )
    p_codegen.add_argument(
        "--style",
        choices=["coarse", "faithful", "hybrid"],
        default="coarse",
        help="Codegen style for the generated test (default: coarse).",
    )
    p_codegen.add_argument(
        "--settle-ms",
        type=int,
        default=120,
        help="Milliseconds of output silence that count as 'settled' (default: 120).",
    )
    p_codegen.add_argument(
        "--cmd",
        default=None,
        help="Override the spawn command in the generated test (default: cast title).",
    )
    p_codegen.add_argument(
        "--cols",
        type=int,
        default=None,
        help="Override terminal cols in the generated test.",
    )
    p_codegen.add_argument(
        "--rows",
        type=int,
        default=None,
        help="Override terminal rows in the generated test.",
    )
    p_codegen.set_defaults(_handler=_cmd_codegen)

    # ----- replay ----------------------------------------------------
    p_replay = sub.add_parser(
        "replay",
        help="Replay a cast against a fresh spawn (no assertions).",
        description=(
            "Spawns the cast's recorded command and re-sends every input "
            "event with the original timing. Useful for demos and for "
            "verifying a recording reproduces the intended behaviour."
        ),
    )
    p_replay.add_argument(
        "cast",
        type=Path,
        help="Cast file to replay.",
    )
    p_replay.add_argument(
        "--cmd",
        default=None,
        help="Override the spawn command (default: the cast's title).",
    )
    p_replay.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speed multiplier for input timing (default: 1.0).",
    )
    p_replay.set_defaults(_handler=_cmd_replay)

    return parser


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------


def _cmd_record(args: argparse.Namespace) -> int:
    if not args.cmd:
        sys.stderr.write("error: provide a command to record, e.g.\n")
        sys.stderr.write("  tuiwright record python myapp.py\n")
        return 2
    cmd = list(args.cmd)
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    cast_path = args.cast or Path.cwd() / f"session-{int(time.time())}.cast"
    cast_path = cast_path.resolve()

    from tuiwright._record.bridge import record_session

    try:
        exit_status = asyncio.run(record_session(cmd, cast_path))
    except KeyboardInterrupt:
        sys.stderr.write("\nrecording interrupted\n")
        exit_status = 130

    sys.stderr.write(f"\nrecorded {cast_path}\n")

    if args.output is not None:
        sys.stderr.write(f"generating test → {args.output}\n")
        _generate_to(args.output, cast_path, args.test_name, args.style, args.settle_ms)
        sys.stderr.write(
            "\nrun your test with:\n"
            f"  uv run pytest {args.output} -v\n"
        )
    else:
        sys.stderr.write(
            "\nnext step — generate a test:\n"
            f"  tuiwright codegen --input {cast_path} --output tests/test_recorded.py\n"
        )

    return exit_status


# ---------------------------------------------------------------------------
# codegen
# ---------------------------------------------------------------------------


def _cmd_codegen(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        sys.stderr.write(f"error: cast file not found: {args.input}\n")
        return 2

    cmd: list[str] | str | None = args.cmd
    if isinstance(cmd, str):
        import shlex
        cmd = shlex.split(cmd)

    _generate_to(
        args.output,
        args.input,
        args.test_name,
        args.style,
        args.settle_ms,
        cmd=cmd,
        cols=args.cols,
        rows=args.rows,
    )
    return 0


def _generate_to(
    output: Path | None,
    cast: Path,
    test_name: str,
    style: str,
    settle_ms: int,
    *,
    cmd: list[str] | None = None,
    cols: int | None = None,
    rows: int | None = None,
) -> None:
    from tuiwright._record.codegen import CodegenStyle, generate_test

    rendered = generate_test(
        cast,
        command=cmd,
        test_name=test_name,
        style=CodegenStyle(style),
        settle_ms=settle_ms,
        cols=cols,
        rows=rows,
    )
    if output is None:
        sys.stdout.write(rendered)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def _cmd_replay(args: argparse.Namespace) -> int:
    if not args.cast.is_file():
        sys.stderr.write(f"error: cast file not found: {args.cast}\n")
        return 2

    asyncio.run(_replay(args.cast, override_cmd=args.cmd, speed=args.speed))
    return 0


async def _replay(cast_path: Path, *, override_cmd: str | None, speed: float) -> None:
    """Re-spawn the recorded command and inject the recorded input timing."""
    import shlex

    from tuiwright._pty import PtyTransport

    header: dict = {}
    events: list[tuple[float, str, str]] = []
    with cast_path.open() as fh:
        first = fh.readline()
        if first:
            header = json.loads(first)
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, list) and len(row) == 3:
                events.append((float(row[0]), str(row[1]), str(row[2])))

    argv = shlex.split(override_cmd) if override_cmd else shlex.split(str(header.get("title", "")))
    if not argv:
        sys.stderr.write("error: cast has no recorded command; pass --cmd\n")
        return

    cols = int(header.get("width", 80))
    rows = int(header.get("height", 24))
    pty = PtyTransport()

    def on_output(chunk: bytes) -> None:
        os.write(sys.stdout.fileno(), chunk)

    pty.add_listener(on_output)
    await pty.spawn(argv, cols=cols, rows=rows)

    t0 = time.monotonic()
    for ev_time, kind, data in events:
        if kind != "i":
            continue
        target = t0 + (ev_time / max(speed, 0.001))
        delay = target - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        pty.write_bytes(data.encode("utf-8", "replace"))

    # Give the app a moment to render the final state then stop.
    await asyncio.sleep(0.5)
    await pty.stop(timeout=2.0)


if __name__ == "__main__":
    sys.exit(main())
