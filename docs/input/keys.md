# Keys

`tui.press("…")` sends one keystroke. `tui.type("…")` sends literal
text. Use `press` for control keys and named keys; use `type` for
ordinary text input.

## Syntax

```
[modifier+]…key
```

Modifiers are joined with `+`. The key is last. Case-insensitive for
named keys; case-sensitive for single characters (so `"A"` is the
shifted form of `"a"`).

```python
await tui.press("enter")
await tui.press("ctrl+s")
await tui.press("shift+tab")
await tui.press("ctrl+shift+f5")
await tui.press("alt+left")
```

## Modifiers

| Name | Aliases |
|---|---|
| Shift | `shift`, `s` |
| Alt | `alt`, `a`, `opt`, `option` |
| Ctrl | `ctrl`, `control`, `c` |
| Meta | `cmd`, `meta`, `super`, `win` |

## Named keys

### Whitespace / control

| Name | Bytes sent |
|---|---|
| `enter` / `return` | `\r` |
| `tab` | `\t` |
| `space` | ` ` |
| `escape` / `esc` | `\x1b` |
| `backspace` | `\x7f` |
| `delete` | `\x1b[3~` |
| `insert` | `\x1b[2~` |

### Arrows

| Name | Bytes |
|---|---|
| `up` / `down` / `left` / `right` | `\x1b[A` / `B` / `D` / `C` |
| `ctrl+up` etc | `\x1b[1;5A` (xterm modifier param) |
| `shift+up` etc | `\x1b[1;2A` |
| `alt+up` etc | `\x1b[1;3A` |

### Navigation

| Name | Bytes |
|---|---|
| `home` / `end` | `\x1b[H` / `\x1b[F` |
| `pageup` / `pgup` | `\x1b[5~` |
| `pagedown` / `pgdn` | `\x1b[6~` |

### Function keys

| Range | Encoding |
|---|---|
| `f1` … `f4` | `\x1bOP` … `\x1bOS` (SS3) |
| `f5` … `f12` | `\x1b[15~` … `\x1b[24~` |
| With modifiers | `\x1b[15;M~` (M = modifier param) |

## Modifier math

Modifier param values follow the xterm convention:

| Combination | Param |
|---|---|
| Shift | 2 |
| Alt | 3 |
| Shift + Alt | 4 |
| Ctrl | 5 |
| Shift + Ctrl | 6 |
| Alt + Ctrl | 7 |
| Shift + Alt + Ctrl | 8 |

The general formula: `1 + (Shift ? 1 : 0) + (Alt ? 2 : 0) + (Ctrl ? 4 : 0)`.

## Ctrl + letter

`ctrl+a` through `ctrl+z` map to the corresponding control byte
(`\x01` through `\x1a`):

```python
await tui.press("ctrl+a")   # \x01
await tui.press("ctrl+c")   # \x03 (SIGINT-style)
await tui.press("ctrl+h")   # \x08 (alt backspace)
await tui.press("ctrl+i")   # \x09 (= tab)
await tui.press("ctrl+m")   # \x0d (= enter)
await tui.press("ctrl+s")   # \x13 (XOFF in cooked mode — works because we raw the PTY)
```

## Alt + letter

`alt+x` sends ESC followed by the letter (`\x1b x`). This is how every
modern terminal emulator handles Alt:

```python
await tui.press("alt+f")    # \x1bf — typical "forward word" binding
await tui.press("alt+b")    # \x1bb — typical "back word"
```

## Typing literal text

For ordinary text, use `tui.type` — it's faster than `press` per
character and supports a delay:

```python
await tui.type("hello world")
await tui.type("slowly", delay=0.05)   # 50 ms between chars
```

`type` sends each character as its UTF-8 bytes. Unicode works:

```python
await tui.type("café — 日本語")
```

## What real terminals send

`tuiwright`'s encoder produces bytes identical to alacritty, iTerm2,
ghostty, kitty (in non-CSIu mode), and xterm-262color. This means:

- `crossterm` apps see exactly the same `KeyEvent` they'd get from a
  real terminal.
- `termion` and `ncurses` apps see the same byte stream.
- The kitty keyboard protocol (CSI u) is **not** implemented in v0.1;
  if your app requires it, file an issue.

## When a keypress does nothing

Three usual causes:

1. **Wrong modifier combination.** Check with `encode_key("ctrl+s")`
   to see the exact bytes sent.
2. **Line discipline is eating it.** This shouldn't happen —
   `TuiSession.start` puts the PTY in raw mode — but if you're using
   the lower-level `PtyTransport` directly, set raw mode yourself.
3. **The app debounces.** Rapid bursts of the same key may collapse
   into one event. Add `await tui.wait_for_stable(quiet_ms=80)`
   between presses.

Next: [Mouse →](mouse.md)
