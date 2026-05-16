# Resize & focus

## Resize

`tui.resize(cols, rows)` changes the simulated terminal size. Under
the hood:

1. `ioctl(fd, TIOCSWINSZ, …)` on the PTY master — the kernel
   delivers `SIGWINCH` to the child's process group.
2. The internal `pyte.Screen` is resized to match so subsequent
   reads use the new geometry.
3. `TuiConfig.cols` / `rows` are updated for any downstream logic
   (snapshot dimensions, etc).

```python
await tui.resize(cols=120, rows=40)
await tui.wait_for_stable(quiet_ms=150)
assert tui.alive, "app should not crash on resize"
```

### Why `wait_for_stable` after resize

Apps typically re-render on resize. Without a settle, an assertion
right after `resize` might catch the screen mid-redraw.

### Rapid resize burst

Real users drag window corners — that produces a flood of SIGWINCH.
Test that your app survives it:

```python
for cols in (130, 120, 110, 100, 110, 120, 130, 140):
    await tui.resize(cols, 44)
await tui.wait_for_stable(quiet_ms=300)
assert tui.alive
```

### Tiny terminal

Most TUIs have a minimum viable size. They should degrade, not panic:

```python
await tui.resize(40, 10)            # below most minimums
await tui.wait_for_stable(quiet_ms=300)
assert tui.alive
```

### Original size

```python
await tui.start("myapp", cols=80, rows=24)
await tui.resize(120, 40)
# … do stuff …
await tui.resize(80, 24)            # restore
```

## Focus events

DEC mode 1004 makes the terminal send `\x1b[I` on focus-in and
`\x1b[O` on focus-out. Apps use this to pause animations, dim cursors,
or reload state on tab return.

```python
await tui.focus(in_=False)          # user clicked away
await tui.wait_for_text("paused")
await tui.focus(in_=True)           # user came back
await tui.wait_for_text("running")
```

### No-op if the app didn't ask for them

```python
async def test_focus(tui):
    await tui.start("myapp")
    await tui.wait_for_text("Ready")
    # If mode 1004 isn't on, focus() does nothing — no error.
    await tui.focus(in_=False)
```

For strict tests:

```python
await tui.wait_for_predicate(
    lambda _: tui._emu.is_focus_events(),
    timeout=2,
    description="focus reporting enabled",
)
await tui.focus(in_=False)
```

## DEC mode reference

The framework tracks these private modes. Query via
`tui._emu.private_modes` (a `frozenset[int]`) or the helper
predicates:

| Code | What | Helper |
|---|---|---|
| 1000 | X10 mouse tracking | `is_mouse_tracking()` |
| 1002 | Button-event mouse | `is_mouse_tracking()` |
| 1003 | Any-event mouse (incl. hover) | `is_mouse_tracking()` |
| 1004 | Focus events | `is_focus_events()` |
| 1006 | SGR mouse encoding | (combined w/ 1000/1002/1003) |
| 1049 | Alt screen buffer | – |
| 2004 | Bracketed paste | `is_bracketed_paste()` |

`is_mouse_tracking()` returns true if any of 1000/1002/1003 is on —
those are the "is the app listening for mouse" modes. 1006 is the
encoding choice; it can be on without any tracking active.

Next: [Cell-grid snapshots →](../snapshots/cell-grid.md)
