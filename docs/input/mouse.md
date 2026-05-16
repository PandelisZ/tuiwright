# Mouse

All mouse input uses SGR 1006 encoding — the modern default that
`crossterm`, `ratatui`, and `xterm` all parse natively. Coordinates
are **0-based** in the API (matching cell indices) and converted to
1-based on the wire.

## The catch: enable mouse tracking first

The target app must have enabled mouse tracking (DEC modes
1000/1002/1003) before clicks register. Most modern TUIs do this at
startup, but startup takes a moment. Wait for it:

```python
await tui.start("myapp")
await tui.wait_for_text("Ready")
await tui.wait_for_predicate(
    lambda _: tui._emu.is_mouse_tracking(),
    timeout=2,
    description="mouse tracking enabled",
)
await tui.click(row=10, col=20)
```

If you click before the app enables tracking, `tuiwright` emits a
one-time warning. In `strict_mouse=True` mode it raises.

## Single click

```python
await tui.click(row=5, col=10)                              # left click
await tui.click(row=5, col=10, button="right")
await tui.click(row=5, col=10, button="middle")
await tui.click(row=5, col=10, modifiers=("ctrl", "shift"))
```

Each click sends both a press and a release event (with `M` and `m`
finals respectively).

## Double-click

```python
await tui.double_click(row=5, col=10)
await tui.double_click(row=5, col=10, interval=0.1)        # gap between clicks
```

The default `interval=0.05` (50 ms) matches what most TUIs expect for
double-click detection.

## Drag

```python
await tui.drag(from_row=5, from_col=10, to_row=12, to_col=30)
await tui.drag(5, 10, 12, 30, steps=8)                     # smoother motion
```

Sends: press at the start, `steps` motion events along the path,
release at the end. Useful for text selection and drag-and-drop.

## Scroll wheel

```python
await tui.scroll(row=10, col=20, direction="down")
await tui.scroll(row=10, col=20, direction="up", lines=3)
```

Sends `lines` wheel events at the given position. Wheel buttons are
encoded as 64 (up) and 65 (down) per the SGR 1006 spec.

## Hover (motion without button)

Hover requires the app to have enabled mode 1003 (any-event mouse,
including pure motion):

```python
await tui.hover(row=5, col=10)
```

If the app is only in mode 1002 (button-event mouse), hover events
are not sent by the protocol — but apps that opt into 1003 see them
as `MouseEventKind::Moved`.

## Modifier keys with mouse

Pass a tuple of modifier names to `click`:

```python
await tui.click(row=5, col=10, modifiers=("ctrl",))
await tui.click(row=5, col=10, modifiers=("ctrl", "shift"))
```

SGR 1006 modifier bits:

| Modifier | Bit |
|---|---|
| Shift | 4 |
| Alt | 8 |
| Ctrl | 16 |

The framework OR-s them into the button code before sending.

## Common patterns

### Click on a specific cell that contains text

```python
pos = tui.screen.find("Settings")[0]
await tui.click(row=pos.row, col=pos.col)
```

### Click inside a titled region

```python
panel = tui.region(title="Files")
# click on the third row of the panel, leftmost cell
await tui.click(row=panel.top + 2, col=panel.left)
```

### Scroll through a long list

```python
for _ in range(10):
    await tui.scroll(row=20, col=40, direction="down")
    await tui.wait_for_stable(quiet_ms=80)
```

### Select a range with drag

```python
await tui.drag(from_row=4, from_col=10, to_row=4, to_col=25)
```

Some TUIs only fire selection logic if the mouse button is held with
motion events — the `drag` helper does exactly that.

## Strict-mouse mode

For a project where mouse input is critical, set
`strict_mouse=True` so a mistake (clicking before the app enabled
tracking) raises instead of warning:

```python
@pytest.mark.tui(strict_mouse=True)
async def test_clicks(tui):
    await tui.start("myapp")
    # forgot to wait_for_predicate...
    await tui.click(row=5, col=5)
    # RuntimeError: mouse input sent but the app has not enabled mouse tracking
```

## Coordinate origins

| | Origin | Indexing |
|---|---|---|
| `tuiwright` API | top-left | 0-based |
| SGR 1006 wire format | top-left | 1-based |
| `Screen.cells[row][col]` | top-left | 0-based |

The framework adds 1 to row/col internally before encoding. You
should always pass 0-based coordinates from tests.

Next: [Paste →](paste.md)
