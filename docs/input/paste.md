# Paste

Bracketed paste lets an app distinguish "the user typed this letter
by letter" from "this was pasted as a block". Modern TUIs use it to
disable autocomplete during pastes, to treat the paste as one undo
unit, and to prevent code injection.

## Sending a paste

```python
await tui.paste("hello world")
await tui.paste("line one\nline two\nline three")
```

The framework wraps the payload in the bracketed-paste sentinels:

```
\x1b[200~  <payload>  \x1b[201~
```

This is exactly what iTerm2, alacritty, and friends send when you
hit ⌘V (or Ctrl+Shift+V).

## The catch: enable bracketed paste first

The app has to have enabled DEC mode 2004. If it hasn't, the
sentinels would leak into the buffer as garbage. `tuiwright` checks
and falls back to plain `type` automatically:

```python
async def test_paste(tui):
    await tui.start("myapp")
    await tui.wait_for_text("Ready")
    # If the app hasn't enabled paste, this acts like .type("hello"):
    await tui.paste("hello")
```

For strict tests where you want to fail loudly if paste mode isn't
on:

```python
await tui.wait_for_predicate(
    lambda _: tui._emu.is_bracketed_paste(),
    timeout=2,
    description="bracketed paste enabled",
)
await tui.paste("hello")
```

## Multi-line pastes

A paste is one atomic event — multi-line content arrives as one
chunk:

```python
await tui.paste("""line one
line two
line three""")
```

Tests can assert that the app handled all three lines:

```python
await tui.wait_for_text("line one")
assert "line two" in tui.screen.text
assert "line three" in tui.screen.text
```

## Sentinel collision

If your payload contains the literal end-marker `\x1b[201~`, the
paste would break out early — and the rest of the payload would be
interpreted as key events. That's both a bug and a security smell,
so the framework raises:

```python
await tui.paste("safe content")
await tui.paste("oops \x1b[201~ unsafe")
# ValueError: paste payload contains the bracketed-paste end marker
```

If you genuinely need to send the marker bytes as part of the
content, use `tui.type` instead — the app won't see them as a paste
boundary but you also lose the bracket semantics.

## What apps see

A `crossterm` app sees the paste as a single `Event::Paste(String)`.
A `tui-textarea` widget treats it as one edit (one undo unit). An
`ncurses` app with `KEY_PASTE` support sees a single paste event.

## Common patterns

### Paste a multi-line script into a composer

```python
script = (
    "select * from users\n"
    "where id = 42\n"
    "limit 10;"
)
await tui.paste(script)
await tui.wait_for_text("select * from users")
```

### Round-trip via the clipboard semantics

```python
# Test that pasting code preserves indentation
code = "def f():\n    return 42"
await tui.paste(code)
await tui.wait_for_text("def f():")
# 4-space indent should be preserved (no autocompletion eating it)
assert "    return 42" in tui.screen.text
```

Next: [Resize & focus →](resize-focus.md)
