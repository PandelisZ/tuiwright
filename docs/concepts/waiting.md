# Waiting (no sleep!)

The #1 cause of flaky TUI tests is `asyncio.sleep(N)`. `tuiwright` has
three primitives that replace every legitimate use of `sleep`. **Learn
these; use nothing else.**

!!! danger "Don't do this"

    ```python
    await tui.press("ctrl+s")
    await asyncio.sleep(0.5)                 # ← flake factory
    assert "Saved" in tui.screen.text
    ```

!!! success "Do this"

    ```python
    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")         # ← deterministic
    ```

## `wait_for_text`

Polls until a substring or regex appears.

```python
await tui.wait_for_text("Ready")
await tui.wait_for_text("Ready", timeout=10)
await tui.wait_for_text(r"v\d+\.\d+", regex=True)
await tui.wait_for_text("error", region=tui.region(title="Logs"))
```

Returns the `re.Match` object so you can extract groups:

```python
match = await tui.wait_for_text(r"id=(\w+)", regex=True)
job_id = match.group(1)
```

On timeout, the error includes a full dump of the last screen so you
can see exactly what the app rendered.

## `wait_for_predicate`

For conditions that aren't a text match:

```python
await tui.wait_for_predicate(
    lambda screen: screen.cursor.row == 10,
    timeout=3,
    description="cursor reaches row 10",
)
```

The predicate is called with the current `Screen`. It can be sync or
return an awaitable.

Use this for:

- Cursor position checks
- Cell-attribute checks ("the OK button should turn green")
- Cross-region invariants ("all error rows should have a ✗ in col 0")
- Process state ("the app should have exited") — pass `lambda _: not tui.alive`

## `wait_for_stable`

Returns when no output has arrived for `quiet_ms`.

```python
await tui.wait_for_stable(quiet_ms=100)
await tui.wait_for_stable(quiet_ms=200, timeout=3)
```

Use this:

- **After startup**, to make sure the entire first frame has been
  drawn (the bottom status bar often paints last):

    ```python
    await tui.wait_for_text("Ready")
    await tui.wait_for_stable(quiet_ms=150)
    # now safe to assert on any part of the screen
    ```

- **Between rapid input bursts**, because many TUIs process one event
  per render tick:

    ```python
    for _ in range(3):
        await tui.press("backspace")
        await tui.wait_for_stable(quiet_ms=80)
    ```

- **Before snapshotting**, so the captured screen is stable:

    ```python
    await tui.wait_for_stable(quiet_ms=200)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
    ```

## How polling works

Internally, every `wait_for_*` uses the same loop:

1. Check the condition.
2. If true → return.
3. If timeout exceeded → raise `TuiTimeoutError` with the last screen.
4. Otherwise → wait on a "screen changed" event with a short backoff
   (default 20 ms), then loop.

The "screen changed" event fires every time bytes arrive from the PTY.
So the loop is event-driven, not a fixed sleep — you typically wake up
the same millisecond the data arrives.

## Tuning the poll interval

The default poll interval (20 ms) is right for almost every test. You
can change it per-session:

```python
from tuiwright import TuiSession
from tuiwright.session import TuiConfig

session = TuiSession(TuiConfig(poll_interval=0.005))   # 5 ms polls
```

But honestly, if you're tweaking this, you probably have a different
problem.

## `TuiTimeoutError`

When a wait times out, you get:

```
TuiTimeoutError: timed out after 5.0s waiting for text 'Saved'.
--- last screen ---
gode  gemini/gemini-3.1-pro-preview-customtools high                                                                          idle

No transcript yet. Ask gode to inspect, edit, or run something.
... (full screen) ...
--- end ---
```

Read the screen. The answer is usually right there: a modal you
didn't dismiss, a status that says "loading", a popup the test didn't
account for.

## Common timeout situations

??? question "I'm waiting for text that's clearly on screen"

    You're probably checking a region that was captured *before* the
    screen updated. Pass the region by **kwarg** to `wait_for_text` —
    we re-derive it from the current screen on every poll:

    ```python
    # bad: region captured once, never re-checked
    panel = tui.region(title="Logs")
    text = panel.text
    if "done" not in text:
        ...

    # good: re-derived on every poll
    await tui.wait_for_text("done", region=tui.region(title="Logs"))
    ```

??? question "I'm waiting for the app to exit"

    ```python
    await tui.wait_for_predicate(
        lambda _: not tui.alive,
        timeout=2,
        description="exit",
    )
    ```

??? question "My snapshot tests are flaky"

    Add a `wait_for_stable` before the assertion. Cursor position
    twitches are the most common culprit (the cursor is part of the
    snapshot header).

Next: [Keys →](../input/keys.md)
