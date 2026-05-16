# Screens & regions

A `Screen` is an immutable snapshot of the terminal grid at one
moment. Cells are addressed `(row, col)`, 0-based, top-left origin.

## Accessing the screen

```python
screen = tui.screen        # rebuilt on each access — cheap
```

The screen is **not** a live view. If you want the latest state,
re-read `tui.screen`. This is intentional: snapshots are reproducible
and equality is well-defined.

## Cell-level access

```python
cell = screen.cells[row][col]
cell.char          # str (single grapheme)
cell.fg, cell.bg   # Color (named, default, or rgb hex)
cell.bold          # bool
cell.italic
cell.underline
cell.reverse
cell.strike
cell.blink
```

`Cell` is a frozen dataclass — equality and hashing work as expected,
so you can drop cells into sets and use them as dict keys.

## Text views

```python
screen.text                 # all rows joined with '\n', trailing spaces stripped
screen.row(2)               # one row, trimmed
screen.row_padded(2)        # one row, exactly cols wide
```

`screen.text` is the workhorse for assertions:

```python
assert "Ready" in tui.screen.text
```

## Searching

```python
from re import Pattern
import re

screen.contains("Ready")
screen.contains(re.compile(r"v\d+\.\d+"))            # regex pattern
screen.contains(r"v\d+\.\d+", regex=True)            # str + flag
screen.row_containing("Error")                       # int or None
screen.find("foo")                                   # list[Position]
screen.find(r"\d+", regex=True)                     # all matches
```

`Position` is a `NamedTuple` of `(row, col)`.

## Regions

A `Region` is a rectangular sub-view of a screen. Use them to scope
assertions to one panel and avoid false matches.

### By title (heuristic)

`tuiwright` looks for ratatui-style framed blocks
(`┌─ Title ─┐ … └─────┘`):

```python
logs = tui.region(title="Logs")
assert "saved" in logs.text
```

The heuristic walks the box-drawing characters around the title to
find the inside rectangle. It works for the default ratatui
`Block::default().borders(Borders::ALL).title("Logs")` plus the
double-line variant.

If the heuristic doesn't match (custom borders, different chars),
fall back to explicit coordinates.

### By coordinates

```python
header = tui.region(rows=(0, 1), cols=(0, tui.screen.cols))
status = tui.region(rows=(tui.screen.rows - 1, tui.screen.rows), cols=(0, tui.screen.cols))
```

Bounds are half-open: `rows=(0, 1)` is one row.

### Region methods

```python
region.text                  # joined rows, trimmed
region.row(0)                # one row of the region
region.rows                  # height
region.cols                  # width
region.contains("foo")
region.contains(r"v\d+\.\d+", regex=True)
```

## Equality

`Screen` equality is **cell-by-cell, attributes included**:

```python
assert tui.screen == prior_screen      # all cells match
```

Two screens differ if:

- Any character differs
- Any cell's fg/bg differs
- Any cell's bold/italic/underline/reverse/strike/blink differs
- Cursor position or visibility differs
- Active DEC mode set differs

This makes [cell-grid snapshots](../snapshots/cell-grid.md) sensitive
to colour and attribute changes, not just text.

If you only care about visible text, compare `screen.text` strings
instead of full screens.

## Common patterns

### Assert on a status line

```python
assert "ready" in tui.screen.row(tui.screen.rows - 1)
```

### Assert on a region's first matching row

```python
panel = tui.region(title="Errors")
row = panel.row(0)
assert "ENOENT" in row
```

### Find every error marker

```python
errors = tui.screen.find("✗")
assert len(errors) == 3
for pos in errors:
    print(f"error at row {pos.row}, col {pos.col}")
```

### Wait until a region has a specific value

`wait_for_text` accepts a region — it re-derives the region from the
current screen on every poll, so it stays correct even as the screen
updates:

```python
panel = tui.region(title="Output")
await tui.wait_for_text("done", region=panel, timeout=10)
```

Next: [Waiting (no sleep!) →](waiting.md)
