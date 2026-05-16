# Architecture

`tuiwright` is built as six layers. Each one has a single
responsibility, and each one is replaceable in principle (e.g. swap
`pyte` for `libvterm` without touching the input encoders).

```
┌─────────────────────────────────────────────────────────────┐
│ 6. pytest plugin                                            │
│    fixtures (tui, tui_factory), marker, CLI flags           │
├─────────────────────────────────────────────────────────────┤
│ 5. Test API — TuiSession                                    │
│    start / press / type / paste / click / scroll / drag /   │
│    hover / resize / focus / wait_for_* / screen / region    │
├─────────────────────────────────────────────────────────────┤
│ 4. Screen model                                             │
│    Cell grid, attrs, .row_containing(), .region(title=)     │
│    Snapshot-friendly serialisation                          │
├─────────────────────────────────────────────────────────────┤
│ 3. Input encoders                                           │
│    Key→bytes, mouse SGR (1006), bracketed paste, focus      │
├─────────────────────────────────────────────────────────────┤
│ 2. Terminal emulator (pyte)                                 │
│    Parse PTY bytes → Screen + DEC mode tracking +           │
│    asciinema cast tee                                       │
├─────────────────────────────────────────────────────────────┤
│ 1. PTY transport (ptyprocess + asyncio)                     │
│    spawn / read (loop.add_reader) / write / resize /        │
│    raw-mode line discipline                                 │
└─────────────────────────────────────────────────────────────┘
```

## Layer 1 — PTY transport

`tuiwright._pty.PtyTransport` wraps `ptyprocess.PtyProcess`:

- Spawns the child under a pseudo-terminal.
- Sets the slave fd to non-blocking and registers a reader via
  `loop.add_reader` — so output is async without a thread.
- **Puts the line discipline in raw mode** (`tty.setraw` on the
  master). Without this, the kernel interprets `\x7f` (DEL) as
  `VERASE` and `\x13` (Ctrl-S) as `IXON` XOFF flow control, eating
  those bytes before the child sees them.
- Supports `TIOCSWINSZ` resize and a graceful SIGTERM → SIGKILL
  shutdown escalation.

The transport doesn't know about emulation or encoding — it just moves
bytes.

## Layer 2 — Terminal emulator

`tuiwright._emulator.Emulator` wraps `pyte.Screen` + `pyte.ByteStream`:

- Feeds output bytes into a VT102 parser.
- Subclasses `pyte.Screen` to track every DEC private mode the app
  enables — mouse (1000/1002/1003/1006), bracketed paste (2004), focus
  (1004), alt screen (1049).
- Exposes `cells()`, `revision` (bumps on every feed), and the
  current mode set.

Why tracking DEC modes matters: when you call
`tui.click(row, col)` against an app that hasn't enabled mouse
tracking, we can warn (or raise in strict mode). Catches the most
common "why doesn't my test work" question.

## Layer 3 — Input encoders

`tuiwright._input` is a table of pure functions:

- `encode_key("ctrl+shift+f5") → b"\x1b[15;6~"`
- `encode_mouse(button="left", row=5, col=10) → b"\x1b[<0;10;5M"`
- `encode_paste("hello") → b"\x1b[200~hello\x1b[201~"`
- `encode_focus(in_=True) → b"\x1b[I"`

These produce exactly the byte sequences a real terminal (alacritty,
iTerm2, ghostty, xterm) sends in xterm-262color mode. Apps written
against `crossterm`, `termion`, or `ncurses` parse them identically.

## Layer 4 — Screen model

`tuiwright.Screen` is an immutable snapshot of the grid:

```python
screen.text                      # newline-joined, trailing spaces stripped
screen.row(0)                    # one row as a string
screen.cells[row][col]           # Cell(char, fg, bg, bold, ...)
screen.row_containing("Ready")   # row index or None
screen.find(r"\d+", regex=True)  # list[Position]
screen.region(title="Logs")      # heuristic detection of framed blocks
```

Regions detect ratatui-style box-drawn frames (`┌─ Title ─┐`)
heuristically. When that's not enough, fall back to explicit
`rows=(top, bottom), cols=(left, right)`.

## Layer 5 — `TuiSession`

The user-facing async class. Owns one PTY, one emulator, one cast
recorder.

```python
async with TuiSession() as t:
    await t.start("myapp")
    await t.wait_for_text("Ready")
    await t.type("hello")
    assert "hello" in t.screen.text
```

`TuiSession` does **no waiting magic**: every method that injects
input returns immediately; you compose them with explicit
`wait_for_*` primitives. This is why tests don't get flaky on slow
machines — there are no implicit sleeps to tune.

## Layer 6 — Pytest plugin

`tuiwright.pytest_plugin` registers via the standard `pytest11`
entry-point. Installing the package gives you:

- `tui` fixture (function-scoped, auto-stops)
- `tui_factory` fixture (for multi-session tests)
- `@pytest.mark.tui(cols=120, rows=40, timeout=10)`
- `--tui-trace`, `--tui-cols`, `--tui-rows`, `--tui-timeout` CLI flags
- Automatic asciinema cast retention on failed tests

## Two snapshot extensions

Living off to the side of the main layers:

- `tuiwright._snapshot.ScreenSnapshotExtension` — serialises a
  `Screen` to a text file with ASCII frame + JSON sidecar of cell
  attributes. Reviewable as a PR diff.
- `tuiwright._snapshot.PNGSnapshotExtension` — renders the current
  cast file to PNG via `agg`, then pixel-diffs with `pixelmatch`.

Both plug into syrupy, so you get `--snapshot-update` and the rest of
syrupy's review machinery for free.

Next: [Sessions →](sessions.md)
