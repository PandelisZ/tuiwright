# Writing good tests

The single biggest predictor of a maintainable TUI test suite is how
you handle **timing**. Get that right and everything else follows.

## The golden pattern

```python
async def test_save_flow(tui):
    # 1. start with explicit dimensions
    await tui.start("myapp", cols=120, rows=40)

    # 2. wait for a startup signal — the LAST thing painted
    await tui.wait_for_text("Ask me anything")
    await tui.wait_for_stable(quiet_ms=150)

    # 3. drive — input + wait_for the resulting change
    await tui.type("hello")
    await tui.wait_for_text("hello")

    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")

    # 4. assert
    assert "Saved" in tui.screen.row(0)
```

Every action has a paired wait. The assertion runs against a known
state. No sleeps anywhere.

## Pick the right startup signal

The first painted character isn't enough — many TUIs draw the status
bar last, so an assertion against `screen.row(rows-1)` right after
seeing the title will race.

Strategies, in order of preference:

1. **Wait for the bottom-most thing**, like the composer placeholder
   or the status bar text. Once that's drawn, everything above is
   too.
2. **Wait for text + a brief stable** when the above isn't possible.
   `wait_for_stable(quiet_ms=150)` gives the render loop room.
3. **Wait for a DEC mode** when the app enables mouse / paste /
   focus at startup — those modes are a reliable "I'm initialized"
   signal:
   ```python
   await tui.wait_for_predicate(
       lambda _: tui._emu.is_mouse_tracking() and tui._emu.is_bracketed_paste(),
       timeout=5,
   )
   ```

## Don't over-assert

The flakiest tests assert "this specific text appears at this exact
position with these exact attributes". The most robust assert
"something with this substring is visible somewhere relevant":

```python
# Brittle — breaks if the framing changes
assert tui.screen.row(3) == "┌─ Logs ──────────┐"

# Robust — survives reskinning
assert "Logs" in tui.screen.text

# Best — scoped to where we expect it
assert "Logs" in tui.region(title="Sidebar").text
```

Reserve full-screen snapshots for layout regression tests where the
*entire* point is to detect any change.

## Handle rapid input

Many TUIs process one event per render tick (60-120 Hz). A burst of
five `await tui.press(...)` calls can collapse into fewer events.

```python
# Doesn't always do what you think
for _ in range(5):
    await tui.press("down")

# Reliable
for _ in range(5):
    await tui.press("down")
    await tui.wait_for_stable(quiet_ms=50)
```

For text input, `tui.type` with a `delay=` is faster than
character-by-character `press`:

```python
await tui.type("a long sentence", delay=0.02)
```

## Use regions when scope matters

Assertions against `tui.screen.text` can match the wrong panel. When
the app has multiple panes, scope:

```python
sidebar = tui.region(title="Files")
main = tui.region(title="Editor")

assert "README.md" in sidebar.text
assert "def main():" in main.text
```

This catches bugs where text accidentally renders in the wrong place
— a full-screen contains check would silently pass.

## Name tests after user-visible behaviour

```python
# Tells you nothing
async def test_handler_1():
    ...

# Tells you the contract
async def test_ctrl_s_saves_and_shows_status():
    ...
```

If the test fails, the name should help you triage in 5 seconds.

## Keep fixture apps deterministic

If you're writing your own fixture TUI for testing the framework
itself:

- Use **raw escape sequences**, not curses/urwid. Third-party
  libraries add timing quirks.
- Disable **flow control** (`IXON`, `IXOFF`) on stdin — these eat
  Ctrl-S / Ctrl-Q.
- **Clear-then-paint** rather than incremental updates — easier to
  reason about state.
- One file, <200 lines.

See `tests/fixtures/demo_app.py` in the tuiwright repo for an
example.

## Cleanup is automatic

The `tui` fixture handles `await session.stop()` in teardown — never
call it manually unless you've stopped using the fixture.

## When tests start to feel slow

Profile before adding `--tui-timeout=30`. Slow tests are usually
slow for one of three reasons:

1. **The app is slow to start.** Use `cargo build --release` for Rust
   binaries; even debug builds have noticeable startup cost.
2. **A `wait_for_text` is matching too late.** Pick an earlier signal.
3. **You're calling `wait_for_stable(quiet_ms=500)` everywhere.**
   100 ms is usually plenty.

Run with `pytest --durations=10` to find the slowest tests.

## What to commit

- Test files (`tests/test_*.py`)
- Fixtures (`tests/conftest.py`, `tests/fixtures/`)
- Snapshots (`tests/__snapshots__/`) — yes, **commit them**
- `.gitignore` for `*.actual.png` and `*.diff.png`

Don't commit:

- Asciinema casts from passing tests (handled by `--tui-trace=retain-on-failure`)
- `.actual.*` / `.diff.*` files (snapshot mismatch artefacts)

Next: [Debugging flakes →](debugging.md)
