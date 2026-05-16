# tuiwright — AI agent guide

This file is the orientation doc for AI coding agents working in this
repo. It's not user-facing documentation (see `README.md` for that) —
it's the minimum context an agent needs to make a useful change without
re-reading the whole codebase.

## What this project is

`tuiwright` is a black-box end-to-end testing framework for terminal
applications. It spawns the TUI under a real PTY and parses the output
through a VT102 emulator (`pyte`), then exposes a Playwright-style
async API for input and assertions. It is **not** a TUI itself; it
**drives** TUIs.

## Architecture in 60 seconds

Six layers, bottom up:

1. `_pty.py` — async `ptyprocess` wrapper. Spawns the child, reads via
   `loop.add_reader`, writes raw bytes, resizes via `TIOCSWINSZ`. Puts
   the slave's line discipline in **raw mode** so bytes pass through
   verbatim (this is load-bearing — without it, DEL/Ctrl-S are eaten).
2. `_emulator.py` — wraps `pyte.Screen` + `pyte.ByteStream`. Tracks DEC
   private modes (mouse 1000/1002/1003/1006, paste 2004, focus 1004).
3. `_input.py` — encoders. Keys (`encode_key`), mouse SGR (`encode_mouse`),
   bracketed paste (`encode_paste`), focus (`encode_focus`).
4. `screen.py` — public model: `Screen`, `Cell`, `Region`, `Color`,
   `Cursor`, `Position`. Titled-region heuristic looks for
   `┌─ Title ─┐` ratatui-style borders.
5. `session.py` — `TuiSession` is the user-facing async class.
   Everything in layers 1–4 is internal.
6. `pytest_plugin.py` — fixtures (`tui`, `tui_factory`), marker
   (`@pytest.mark.tui`), CLI flags.

Snapshot extensions live under `_snapshot/`: `cells.py` for cell-grid
text snapshots, `png.py` for pixel regression via `agg`.

## Critical invariants

- **Public API is `tuiwright.__init__` re-exports only.** Anything
  underscore-prefixed is internal and may change. Don't import from
  internals in tests outside this repo.
- **No `asyncio.sleep(n)` as a "wait for state" substitute.** Use
  `wait_for_text` / `wait_for_predicate` / `wait_for_stable`. Sleeping
  is the #1 cause of flakes.
- **`Screen` is immutable.** A `Region` carries a snapshot of one
  `Screen`. `wait_for_text(region=...)` re-derives the region from the
  *current* session screen on every poll — preserve that behaviour.
- **Mouse / paste / focus inputs check the DEC mode first.** If the app
  hasn't enabled the mode, we warn once (or raise in `strict_mouse`).
  This catches the most common "why doesn't my test work" question.
- **All public classes use `from __future__ import annotations`.** The
  type-stub story is `py.typed`; runtime type evaluation is off.

## Adding a new key, mouse button, or sequence

1. Add to the lookup in `src/tuiwright/_input.py` (one of `_NAMED_KEYS`,
   `_CSI_LETTER_FINALS`, `_CSI_TILDE_NUMS`, `_BUTTON_ALIASES`).
2. Add a parametrised case in `tests/test_input.py`.
3. If the input is a mode-gated kind, wire `_check_mouse_enabled` /
   `is_focus_events` etc. in `session.py`.
4. End-to-end test in `tests/test_session_*.py` against
   `tests/fixtures/demo_app.py` — extend the fixture if needed.

## Adding a new wait primitive

Mirror the existing `wait_for_*` pattern: take a `timeout=` keyword,
read `self.config.default_timeout` as the default, drive the poll loop
through `_poll_until` or `_poll_until_async`, and never poll faster
than `self.config.poll_interval`.

## Running tests

```bash
uv run pytest                          # full suite, ~5 s
uv run pytest tests/test_input.py -v   # one file, with names
uv run pytest --snapshot-update        # refresh syrupy snapshots
uv run pytest -k mouse                 # one keyword
```

For PNG snapshot work you need `agg` on PATH (`brew install agg` or
`cargo install --git https://github.com/asciinema/agg`).

## Common gotchas an agent will hit

| Symptom | Cause | Fix |
|---|---|---|
| `wait_for_text` times out but the text is clearly on screen | The region was passed as a snapshot Region — fixed in v0.1 but worth checking the bounds | Re-derive bounds each poll (see `wait_for_text` impl) |
| Rapid keypresses are dropped | Target app debounces or processes events per render tick | `await tui.wait_for_stable(quiet_ms=80)` between presses |
| `Ctrl-S` does nothing | Slave PTY line discipline interprets `\x13` as XOFF | Raw mode is enabled in `_pty.spawn`; if a test bypasses `start()`, set it manually |
| Mouse click ignored | App hasn't enabled mouse tracking yet | `await tui.wait_for_predicate(lambda _: tui._emu.is_mouse_tracking(), …)` before clicking |
| Snapshot diffs on whitespace | `Screen.row()` strips trailing spaces; `row_padded()` doesn't | Use `row()` for content checks, `row_padded()` for layout snapshots |

## What lives where

```
src/tuiwright/
├── session.py            # 430 LOC — main API
├── screen.py             # 245 LOC — public model
├── _input.py             # 290 LOC — encoder tables + parsers
├── _pty.py               # 195 LOC — ptyprocess wrapper
├── _emulator.py          # 125 LOC — pyte + DEC modes
├── _snapshot/cells.py    #  90 LOC — screen→text snapshots
├── _snapshot/png.py      #  65 LOC — PNG snapshots via agg
├── _trace/recorder.py    #  90 LOC — asciinema cast writer
└── pytest_plugin.py      # 165 LOC — fixtures + CLI flags

tests/                    # 84 tests, ~5 s, zero flakes
examples/gode/            # 5 tests against a real ratatui binary
.claude/skills/           # Skills for AI agents driving this repo
```

## Skills available

If you're invoked here as a slash command, these are loaded:

- `/tuiwright-test` — scaffold a new test file with proper fixtures
- `/tuiwright-run` — run the right pytest command for a goal
- `/tuiwright-debug` — investigate a flaky or hanging test

See `.claude/skills/<name>/SKILL.md` for each.

## Cross-agent compatibility

The same skills are mirrored under `.agents/skills/` for vendor-neutral
loading (Codex CLI, Cursor, Aider, etc), and the framework's overall
guidance lives in `AGENTS.md` at the repo root (the
[agents.md](https://agents.md) cross-vendor convention) for runtimes
that don't read `CLAUDE.md`. If you modify a skill in `.claude/`,
mirror the change to `.agents/`. They're kept identical.
