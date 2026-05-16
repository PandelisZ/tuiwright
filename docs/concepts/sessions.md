# Sessions

A `TuiSession` is one running TUI under one PTY. Most tests use one
session via the `tui` fixture; for multi-pane scenarios, use
`tui_factory`.

## Lifecycle

```python
async def test_thing(tui):
    # 1. start — spawn the binary, hook listeners
    await tui.start("myapp", env={"FOO": "bar"}, cols=120, rows=40)

    # 2. drive — input + waits
    await tui.wait_for_text("Ready")
    await tui.type("hello")

    # 3. assert
    assert "hello" in tui.screen.text

    # 4. stop — automatic when the fixture tears down
```

The `tui` fixture handles steps 1-end-of-test for you: it constructs
the session, yields it, then calls `await session.stop()` in cleanup.

## Starting

```python
await tui.start(
    cmd,                     # str (shlex-split) or list[str]
    *,
    env=None,                # extra env vars, merged with os.environ
    cwd=None,                # working dir
    cols=80,                 # terminal width
    rows=24,                 # terminal height
    cast_path=None,          # explicit cast file location
)
```

The string form runs through `shlex.split`, so `"myapp --flag arg"`
becomes `["myapp", "--flag", "arg"]`. Use the list form when arguments
contain spaces.

### Common environment knobs

| Var | Purpose |
|---|---|
| `TERM` | Defaults to `xterm-256color`. Override if your app expects something specific. |
| `COLORTERM` | Defaults to `truecolor`. Some apps gate true-colour output on this. |
| `PAGER` / `LESS` | Defaulted to safe values to prevent paging from breaking the layout. |

You can override any of these via `env={}` and they'll take precedence.

## Stopping

```python
exit_status = await tui.stop(timeout=2.0)
```

Sequence:

1. Send `SIGTERM`.
2. Wait up to `timeout` seconds for the child to exit.
3. If still alive, send `SIGKILL`.
4. Close the PTY and recorder.

The fixture calls this for you with the default timeout. Override
explicitly only when you know the app needs more shutdown grace.

## Context manager

For one-off scripts (not pytest), use the async context manager:

```python
import asyncio
from tuiwright import TuiSession, TuiConfig


async def main():
    async with TuiSession(TuiConfig(cols=120, rows=40)) as tui:
        await tui.start("myapp")
        await tui.wait_for_text("Ready")
        await tui.type("hello")


asyncio.run(main())
```

## Multiple sessions

```python
async def test_two_panes(tui_factory):
    left = tui_factory()
    right = tui_factory()

    await left.start("myapp", cols=80, rows=24)
    await right.start("myapp", cols=80, rows=24)

    await left.wait_for_text("Ready")
    await right.wait_for_text("Ready")

    # both are independent; the fixture stops both on teardown
```

## What lives on `TuiSession`

| Property | Use |
|---|---|
| `tui.screen` | Snapshot of the current grid (cheap; rebuilt on each access) |
| `tui.alive` | `True` until the child exits |
| `tui.cast_path` | Path to the live asciinema cast file |
| `tui.config` | The active `TuiConfig` |

| Method | Use |
|---|---|
| `tui.start(...)` | Spawn |
| `tui.stop(...)` | Graceful shutdown |
| `tui.press(key)` | One key event ([reference](../input/keys.md)) |
| `tui.type(text)` | Plain text input |
| `tui.paste(text)` | Bracketed paste |
| `tui.click / scroll / drag / hover(...)` | [Mouse](../input/mouse.md) |
| `tui.resize(cols, rows)` | TIOCSWINSZ + SIGWINCH |
| `tui.focus(in_=)` | Focus in/out |
| `tui.wait_for_text(...)` | [See Waiting](waiting.md) |
| `tui.wait_for_predicate(...)` | Custom condition |
| `tui.wait_for_stable(...)` | Settle on no-change |
| `tui.region(title=, rows=, cols=)` | [Screen subview](screens.md) |
| `tui.assert_region(...)` | Convenience assertion |
| `tui.png()` | Render current cast to PNG via `agg` |

## Configuration

`TuiConfig` is a frozen-ish dataclass; tweak it per-test via the
`tui_config` fixture or via the `@pytest.mark.tui` marker.

```python
@pytest.mark.tui(cols=140, rows=44, timeout=15, strict_mouse=True)
async def test_strict(tui):
    ...
```

Defaults:

```python
TuiConfig(
    cols=80,
    rows=24,
    default_timeout=5.0,
    poll_interval=0.02,
    stable_quiet_ms=50,
    agg_path=None,           # auto-discovered from PATH
    cast_dir=None,           # tempdir per session
    strict_mouse=False,      # warn instead of raise
)
```

Next: [Screens & regions →](screens.md)
