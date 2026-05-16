# tuiwright

**Playwright-style end-to-end testing for terminal user interfaces.**

`tuiwright` drives any TUI binary under a real PTY plus a faithful
terminal emulator, then lets you assert on the rendered screen with an
async pytest API. It covers keys, text, mouse, resize, bracketed paste,
and focus events out of the box, with cell-grid and PNG snapshot
regression.

```python
async def test_save_flow(tui, snapshot):
    await tui.start("myapp", cols=120, rows=40)
    await tui.wait_for_text("Ready")

    await tui.type("hello world")
    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")

    await tui.click(row=5, col=12)
    await tui.assert_region(title="Logs", contains="saved hello world")

    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

## Why

| Existing tool | Limitation |
|---|---|
| `pexpect` / `expect` | Line/regex oriented — broken on cursor-addressed full-screen apps |
| `vhs`, `asciinema` | Demo recording, not designed for assertions |
| Textual `Pilot`, `teatest` | In-process — never exercise the real binary or PTY |
| `ratatui::TestBackend` | Same — model-level only |
| `insta`, `syrupy` | Assertion layer only, no driver |

`tuiwright` is the missing piece: **black-box, async, snapshot-aware,
ergonomic**.

## Install

```bash
uv add --dev tuiwright
# or
pip install tuiwright
```

Optional, for PNG regression:

```bash
# macOS
brew install agg
# from source (recommended for latest)
cargo install --git https://github.com/asciinema/agg
```

Without `agg`, cell-grid snapshots still work; PNG assertions raise a
clear `FileNotFoundError`.

## Quick start

`tuiwright` registers itself as a `pytest` plugin — no
`conftest.py` boilerplate. Just write `async def test_*`:

```python
# tests/test_my_tui.py
from tuiwright._snapshot import ScreenSnapshotExtension

async def test_help_panel_opens(tui, snapshot):
    await tui.start(["myapp", "--no-color"], cols=100, rows=30)
    await tui.wait_for_text("Ready")
    await tui.press("?")
    await tui.wait_for_text("Help", region=tui.region(title="Help"))
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

Run it:

```bash
pytest                       # red on first run — no snapshot yet
pytest --snapshot-update     # green; commit the .screen file
pytest                       # green forever, until the rendering changes
```

Snapshot files are plain text (an ASCII frame plus a small JSON sidecar
of cell attributes) and live in `tests/__snapshots__/<test_module>/`.
They diff cleanly in PR review.

## API

### `TuiSession` (the `tui` fixture)

| Method | Purpose |
|---|---|
| `await start(cmd, *, env=, cwd=, cols=, rows=, cast_path=)` | Spawn a binary under a PTY |
| `await stop(timeout=2.0)` | Graceful SIGTERM → SIGKILL escalation |
| `await press(key)` | `"enter"`, `"ctrl+s"`, `"shift+tab"`, `"alt+left"`, `"f5"`, `"ctrl+shift+f5"` |
| `await type(text, delay=0)` | Per-char input with optional delay |
| `await paste(text)` | Wrapped in `\x1b[200~ … \x1b[201~`; falls back to `type` if app didn't enable bracketed paste |
| `await click(row, col, button="left", modifiers=())` | SGR 1006 mouse encoding, 0-based coords |
| `await double_click(row, col)` | Two clicks within `interval=` seconds |
| `await drag(from_row, from_col, to_row, to_col, steps=4)` | Press → motion events → release |
| `await scroll(row, col, direction="down", lines=1)` | Mouse wheel |
| `await hover(row, col)` | Motion-no-button (requires mode 1003) |
| `await resize(cols, rows)` | `TIOCSWINSZ` + SIGWINCH |
| `await focus(in_=True)` | Focus in/out (`\x1b[I` / `\x1b[O`) |
| `await wait_for_text(needle, timeout=, region=, regex=False)` | Returns the `re.Match` |
| `await wait_for_predicate(fn, timeout=)` | `fn(screen) -> bool`, sync or async |
| `await wait_for_stable(quiet_ms=50, timeout=)` | Settle on no-change |
| `screen` | Current `Screen` (sync property) |
| `region(title=, rows=, cols=)` | Subview into the current screen |
| `png()` | Render current cast to PNG via `agg` |
| `cast_path` | Path to the live asciinema cast file |
| `alive` | `True` until the child exits |

### `Screen`, `Region`, `Cell`

```python
screen.text                      # all rows joined with '\n', trailing spaces stripped
screen.row(0)                    # one row as a string
screen.row_containing("Error")   # row index or None
screen.find(r"\d+", regex=True)  # list[Position]
screen.contains("Ready")
screen.region(title="Logs")      # heuristic detection of ┌─ Logs ─┐ ratatui frames
screen.region(rows=(3, 8), cols=(10, 40))

cell = screen.cells[row][col]
cell.char, cell.fg, cell.bg, cell.bold, cell.italic, cell.reverse, ...
```

### CLI flags

```
--tui-trace=on|retain-on-failure|off   # default: retain-on-failure
--tui-trace-dir=DIR                     # where to keep cast files (default: tmp_path)
--tui-cols=N, --tui-rows=N              # default terminal size
--tui-timeout=SECONDS                   # default wait_for_* timeout
--snapshot-update                       # from syrupy: refresh all snapshots
```

### Marker

```python
@pytest.mark.tui(cols=120, rows=40, timeout=10, strict_mouse=True)
async def test_large_screen(tui):
    ...
```

`strict_mouse=True` raises if mouse input is sent before the app has
enabled mouse tracking (DEC modes 1000/1002/1003). Off by default — a
single warning is emitted.

## How it works

```
┌─ pytest fixture (tui) ──────────────────────────────────────┐
│ TuiSession                                                  │
│  ├─ Input encoders ── press / type / paste / mouse / resize │
│  ├─ Emulator (pyte) ── parses PTY output → 2D cell grid     │
│  ├─ Cast recorder ─── asciinema v2 file for replay + PNG    │
│  └─ PTY transport ── ptyprocess, async via add_reader       │
└─────────────────────────────────────────────────────────────┘
              │ stdin (bytes)                ▲ stdout
              ▼                              │
      ┌──────────────── child process ─────────────────┐
      │   the TUI binary under test                     │
      └─────────────────────────────────────────────────┘
```

- **PTY** (`ptyprocess`): real pseudo-terminal — the app cannot tell it
  isn't running under iTerm. SIGWINCH on resize, real flow control, the
  whole shape.
- **Emulator** (`pyte`): VT102 parser. Exposes the cell grid plus DEC
  private modes (mouse, paste, focus) so input encoders know what the
  app will accept.
- **Cast recorder**: tees PTY output into an asciinema v2 file. Renders
  to PNG on demand via `agg`, and can be replayed in
  asciinema-player for trace viewing.
- **Snapshot extensions**: syrupy plugins for `Screen` (text + JSON
  sidecar) and PNG (with `pixelmatch` for pixel-tolerant diff).

## Project layout

```
src/tuiwright/
├── session.py              # TuiSession — public API
├── screen.py               # Screen, Region, Cell, Color, Cursor
├── _pty.py                 # ptyprocess wrapper
├── _emulator.py            # pyte + DEC mode tracking
├── _input.py               # key/mouse/paste encoders
├── _trace/recorder.py      # asciinema cast writer
├── _snapshot/cells.py      # syrupy ext for Screen
├── _snapshot/png.py        # syrupy ext for PNG (pixelmatch)
└── pytest_plugin.py        # tui fixture, marker, CLI flags
```

## Limitations (v0.1)

- POSIX only (macOS + Linux). Windows ConPTY is on the roadmap.
- Mouse encoding is SGR 1006 (the modern default). Legacy X10 / urxvt
  encodings are not implemented.
- Sixel, Kitty graphics, OSC 52 clipboard are passed through but not
  parsed.
- The `region(title=...)` heuristic looks for ratatui-style
  single-line box drawing borders (`┌─ Title ─┐`). For other border
  styles fall back to explicit `rows=`, `cols=`.

## License

MIT.
