# Contributing to tuiwright

Thanks for picking up a piece of this. The framework lives or dies by
its reliability, so the bar for changes is: **the self-test suite
passes zero-flake across at least five consecutive runs**.

## Dev setup

```bash
git clone https://github.com/pandelisz/tuiwright.git
cd tuiwright
uv sync --all-extras --group dev
uv run pytest                                # ~5 s
uv run pytest -x --tb=short                  # first failure, short trace
```

`uv` will auto-install Python 3.12 if needed.

For PNG regression tests you also need [`agg`](https://github.com/asciinema/agg):

```bash
brew install agg                       # macOS
cargo install --git https://github.com/asciinema/agg
```

Tests skip PNG assertions gracefully when `agg` isn't on `PATH`.

## Project layout

```
src/tuiwright/
├── session.py            # TuiSession — the public async API
├── screen.py             # Screen, Region, Cell, Color, Cursor
├── _pty.py               # ptyprocess wrapper + raw-mode setup
├── _emulator.py          # pyte + DEC private-mode tracking
├── _input.py             # key / mouse / paste / focus encoders
├── _trace/recorder.py    # asciinema cast v2 writer
├── _snapshot/cells.py    # syrupy extension for Screen
├── _snapshot/png.py      # syrupy extension for PNG via agg
└── pytest_plugin.py      # fixtures, marker, CLI flags
tests/
├── fixtures/demo_app.py  # the hand-rolled TUI used as a target
├── test_input.py         # encoder unit tests
├── test_screen.py        # model unit tests
├── test_emulator.py      # DEC mode + resize unit tests
├── test_session_*.py     # end-to-end session tests
└── test_snapshots.py     # cell-grid round-trip
examples/gode/            # real-world test suite (skipped without GODE_BIN)
```

## Coding style

- Run `uv run ruff check src tests` and `uv run ruff format src tests`
  before opening a PR.
- Public API surface lives in `tuiwright.__init__` — anything else is
  underscore-prefixed and may change without a major bump.
- Tests should never use `asyncio.sleep` as a stand-in for waiting on
  state. Use `wait_for_text` / `wait_for_predicate` / `wait_for_stable`.
- New input encoders need a unit test in `tests/test_input.py` and an
  integration test in `tests/test_session_*.py`.

## Adding a new key, mouse button, or sequence

1. Add the mapping in `src/tuiwright/_input.py` (key table, button
   enum, or new `encode_*` helper).
2. Add a parametrised case to `tests/test_input.py`.
3. If the new input requires a DEC mode (e.g. mouse, focus), wire it
   through the mode-check path in `TuiSession`.
4. Add an end-to-end test that drives `tests/fixtures/demo_app.py`
   (extend the fixture app if needed — keep it dependency-free).

## Snapshot updates

```bash
uv run pytest --snapshot-update           # refresh everything
uv run pytest tests/test_snapshots.py --snapshot-update -k name_of_test
```

Commit the snapshot file alongside the code change. Reviewers should be
able to read the snapshot's ASCII frame and judge whether the change is
intentional.

## Release

```bash
# 1. bump version in pyproject.toml + src/tuiwright/__init__.py
# 2. update CHANGELOG.md
uv build
uv publish    # requires PyPI token in env
git tag v0.X.Y
git push --tags
```

## Reporting bugs

Open an issue at https://github.com/pandelisz/tuiwright/issues with:

- the command that spawns your TUI
- the expected vs actual screen text (or attach the cast file from a
  failing test — they're plain JSON)
- `uv pip freeze | grep -E "tuiwright|pyte|ptyprocess"` output

A failing case in the form of a test against `tests/fixtures/demo_app.py`
or a small standalone script is hugely appreciated.
