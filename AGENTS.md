# AGENTS.md — tuiwright

This file follows the [AGENTS.md](https://agents.md) convention so any
coding agent (Codex CLI, Cursor, Claude Code, Aider, Continue, etc.)
can orient itself in this repo.

For Claude-specific guidance see `CLAUDE.md`. For vendor-neutral skill
files see `.agents/skills/`. The contents are equivalent — different
agents look for different paths.

## Project

`tuiwright` is a black-box end-to-end testing framework for terminal
applications. It spawns a TUI binary under a real PTY, parses output
through a VT102 emulator (`pyte`), and exposes a Playwright-style
async API for input and assertions. **Not** a TUI itself; it drives
TUIs.

## Repo layout

```
src/tuiwright/
├── session.py            # TuiSession — main async API
├── screen.py             # Screen, Region, Cell, Color, Cursor
├── _pty.py               # ptyprocess wrapper + raw-mode line discipline
├── _emulator.py          # pyte + DEC private-mode tracking
├── _input.py             # key / mouse / paste / focus encoders
├── _trace/recorder.py    # asciinema cast v2 writer
├── _snapshot/cells.py    # syrupy extension for Screen
├── _snapshot/png.py      # syrupy extension for PNG via agg
└── pytest_plugin.py      # tui / tui_factory fixtures, marker, CLI flags
tests/
├── fixtures/demo_app.py  # hand-rolled TUI used as the test target
├── test_input.py         # encoder unit tests
├── test_screen.py        # model unit tests
├── test_emulator.py      # DEC mode + resize unit tests
├── test_session_*.py     # end-to-end session tests
└── test_snapshots.py     # cell-grid round-trip
examples/gode/            # real-world test suite (skipped without GODE_BIN)
docs/                     # MkDocs Material site -> pandelisz.github.io/tuiwright
.agents/skills/           # vendor-neutral agent skills
.claude/skills/           # Claude-specific copies (identical content)
```

## Setup

```bash
uv sync --all-extras --group dev
uv run pytest               # ~5 s, 84 tests
```

For docs:

```bash
uv sync --group docs
uv run mkdocs serve         # localhost:8000
uv run mkdocs build --strict
```

For PNG snapshot regression: `brew install agg` or
`cargo install --git https://github.com/asciinema/agg`. Tests skip
PNG assertions gracefully without it.

## How to run tests

| Goal | Command |
|---|---|
| Everything | `uv run pytest -q` |
| One file | `uv run pytest tests/test_x.py -v` |
| Update snapshots | `uv run pytest --snapshot-update` |
| Flake hunt | `for i in 1 2 3 4 5; do uv run pytest -q --timeout=30 || break; done` |
| Lint | `uv run ruff check src tests` |

## Coding conventions

- Public API is `tuiwright.__init__` re-exports. Anything
  underscore-prefixed is internal and may change without a major bump.
- No `asyncio.sleep` as a "wait for state" substitute. Use
  `wait_for_text` / `wait_for_predicate` / `wait_for_stable`.
- `Screen` is immutable. A `Region` carries a snapshot of one
  `Screen`. `wait_for_text(region=…)` re-derives bounds from the
  *current* session screen on every poll — preserve that behaviour.
- Mouse / paste / focus inputs check the DEC mode first. Warn (or
  raise in `strict_mouse`) when input is sent to an app that hasn't
  enabled the relevant mode.
- All public modules use `from __future__ import annotations`.

## Critical invariants

- **PTY line discipline must be raw.** `_pty.spawn` calls
  `tty.setraw` on the master fd so DEL (`\x7f`) and Ctrl-S (`\x13`)
  pass through verbatim instead of being eaten by VERASE / IXON. If
  you add a code path that creates a `PtyProcess` directly, set raw
  mode yourself.
- **Cast file is the single source of truth for replay + PNG.** Every
  byte the child emits is tee'd to an asciinema v2 file.
  `tui.png()` invokes `agg` against the *current* cast position; the
  recorder must flush on every chunk.
- **Tests must be deterministic.** A new test is not merged unless
  the full suite passes zero-flake across at least five consecutive
  runs. This is non-negotiable — flaky tests are worse than no tests.

## Adding new functionality

### A new key / mouse button / sequence

1. Add to the lookup in `src/tuiwright/_input.py` (one of
   `_NAMED_KEYS`, `_CSI_LETTER_FINALS`, `_CSI_TILDE_NUMS`,
   `_BUTTON_ALIASES`).
2. Add a parametrised case in `tests/test_input.py`.
3. If the input is mode-gated, wire mode-check in `session.py`.
4. End-to-end test in `tests/test_session_*.py` against
   `tests/fixtures/demo_app.py` — extend the fixture if needed.

### A new wait primitive

Mirror existing `wait_for_*`: take `timeout=`, default to
`self.config.default_timeout`, drive through `_poll_until` /
`_poll_until_async`, never poll faster than
`self.config.poll_interval`.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `wait_for_text` times out but the text is on screen | Region captured stale | Pass `region=tui.region(…)` to `wait_for_text` so it re-resolves on every poll |
| Rapid keypresses dropped | App debounces or processes one event per render tick | `await tui.wait_for_stable(quiet_ms=80)` between presses |
| Ctrl-S does nothing | Slave PTY line discipline = XOFF | Raw mode is enabled in `_pty.spawn`; bypass = your problem |
| Mouse click ignored | App hasn't enabled mouse tracking | Wait for it: `await tui.wait_for_predicate(lambda _: tui._emu.is_mouse_tracking(), …)` |
| Snapshot diffs on whitespace | `Screen.row()` strips trailing spaces; `row_padded()` doesn't | Use `row()` for content checks, `row_padded()` for layout |

## Skills available

Three skills bundled at `.agents/skills/` (and mirrored at
`.claude/skills/` for Claude-specific runtimes):

- **tuiwright-test** — scaffold a new test with proper fixtures,
  waits, snapshot patterns
- **tuiwright-run** — pick the right pytest invocation for a goal
- **tuiwright-debug** — diagnose flaky / hanging / mysterious
  failures

Each is a single `SKILL.md` with YAML front-matter listing trigger
descriptions. Read them once for the "spirit" of the framework — even
when writing tests by hand they encode the patterns that work the
first time.

## Documentation

User-facing docs live at https://pandelisz.github.io/tuiwright/ and
under `docs/`. The site is built with MkDocs Material and deploys via
`.github/workflows/docs.yml` on push to master.

Reference pages worth knowing about:

- [Architecture](https://pandelisz.github.io/tuiwright/concepts/architecture/) — the six layers
- [Waiting (no sleep!)](https://pandelisz.github.io/tuiwright/concepts/waiting/) — wait primitive semantics
- [Writing good tests](https://pandelisz.github.io/tuiwright/guides/writing-tests/) — patterns that scale
- [Debugging flakes](https://pandelisz.github.io/tuiwright/guides/debugging/) — triage by symptom

## Release process

```bash
# 1. bump version in pyproject.toml + src/tuiwright/__init__.py
# 2. update CHANGELOG.md
uv build
uv publish              # requires PyPI token
git tag v0.X.Y
git push --tags
gh release create v0.X.Y dist/*.whl dist/*.tar.gz --notes-file CHANGELOG.md
```
