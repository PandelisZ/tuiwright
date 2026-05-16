# CLI flags

`tuiwright` adds these flags to pytest's CLI. Inspect with
`pytest --help` (look for the "tuiwright" group).

## `--tui-trace=on|retain-on-failure|off`

Default: `retain-on-failure`.

Controls when the asciinema cast file (everything the PTY emitted) is
kept on disk.

| Value | Behaviour |
|---|---|
| `on` | Always keep the cast — useful for demos and debugging passing tests |
| `retain-on-failure` | Keep cast only when the test fails (default) |
| `off` | Delete the cast unconditionally |

The cast is plain JSON (asciinema v2 format). Replay it in a browser
with [asciinema-player](https://docs.asciinema.org/manual/player/), or
render to GIF/PNG with [`agg`](https://github.com/asciinema/agg).

```bash
pytest --tui-trace=on
```

## `--tui-trace-dir=PATH`

Default: each test's `tmp_path`.

Where retained casts go. Useful for inspecting them after CI:

```bash
pytest --tui-trace=retain-on-failure --tui-trace-dir=./tui-traces
```

Then upload `tui-traces/` as a CI artifact.

## `--tui-cols=N` / `--tui-rows=N`

Default: 80 × 24.

Default terminal dimensions for every session. Tests that override
via `tui.start(cols=…)` or `@pytest.mark.tui(cols=…)` ignore these.

```bash
pytest --tui-cols=120 --tui-rows=40
```

## `--tui-timeout=SECONDS`

Default: 5.0.

Default timeout for every `wait_for_text`, `wait_for_predicate`, and
`wait_for_stable`. Per-test overrides via the marker take precedence:

```bash
pytest --tui-timeout=10            # bump globally
pytest --tui-timeout=2             # tighter for fast-feedback runs
```

## Inherited from syrupy

These come from `syrupy` (the snapshot library `tuiwright` builds on)
and apply to all snapshot assertions:

| Flag | Purpose |
|---|---|
| `--snapshot-update` | Update snapshots to match current output |
| `--snapshot-warn-unused` | Warn about snapshots that weren't asserted on |
| `--snapshot-details` | Show the snapshot content in failure messages |

## Inherited from pytest

Useful ones for `tuiwright` tests:

| Flag | Purpose |
|---|---|
| `-x` | Stop on first failure |
| `-v` / `-vv` | Show test names / show snapshot diffs verbatim |
| `-k EXPR` | Run tests matching keyword expression |
| `--timeout=N` | Per-test hard timeout (separate from `--tui-timeout`) |
| `--tb=short` | One-line tracebacks |
| `--pdb` | Drop into debugger on failure |

## Examples

```bash
# Fast-feedback: stop at first failure, brief output
pytest -x --tb=short

# Update all snapshots after an intentional UI change
pytest --snapshot-update

# Update one test's snapshot
pytest tests/test_layout.py -k startup --snapshot-update

# Keep cast files for inspection
pytest --tui-trace=on --tui-trace-dir=./traces

# CI run with margin for slow runners
pytest --tui-timeout=15 --timeout=30 -v

# Reproduce a CI failure locally with the same flags
pytest --tui-cols=120 --tui-rows=40 -k name_of_failing_test
```

Next: [Writing good tests →](../guides/writing-tests.md)
