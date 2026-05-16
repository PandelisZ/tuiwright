# Debugging flakes

A flaky `tuiwright` test almost always falls into one of five
buckets. Triage in this order.

## 1. Read the screen dump

Every `TuiTimeoutError` includes the **full last screen**:

```
TuiTimeoutError: timed out after 5.0s waiting for text 'Saved'.
--- last screen ---
gode  gemini/gemini-3.1-pro-preview-customtools high                                                                          idle

No transcript yet. Ask gode to inspect, edit, or run something.
... (full screen) ...
--- end ---
```

Read it before doing anything else. The answer is usually visible:

- A modal you didn't dismiss
- A loading spinner that's still spinning
- An unexpected error notification
- The text you wanted, just in a different region

## 2. Classify

| Symptom | Most likely cause | Section |
|---|---|---|
| Text is on screen, but `wait_for_text` still times out | Region was stale | §A |
| Text doesn't appear in the dump either | App never rendered it | §B |
| Passes once, fails next run | Race condition | §C |
| Input has no effect | DEC mode not enabled, or rapid burst | §D |
| Snapshot diffs without code changes | Cursor / mode flap | §E |

## §A — Stale region

The `Region` object holds a snapshot of one `Screen`. If you captured
it and *then* started a wait, the wait was checking frozen data:

```python
# BAD
region = tui.region(title="Logs")
text = region.text             # ← captured here
if "done" not in text:
    ...                        # ← stale forever
```

`wait_for_text(region=…)` is special — it re-derives the bounds from
the *current* screen on every poll. Always pass regions in that way:

```python
# GOOD
await tui.wait_for_text("done", region=tui.region(title="Logs"))
```

## §B — Text really isn't there

Quick standalone repro:

```python
import asyncio
from tuiwright import TuiSession

async def main():
    s = TuiSession()
    await s.start(["myapp"], env={"KEY": "v"}, cols=140, rows=44)
    for i in range(10):
        await asyncio.sleep(1)
        print(f"--- t={i+1}s ---")
        print(s.screen.text)
        if "<expected>" in s.screen.text:
            break
    await s.stop()

asyncio.run(main())
```

Common causes:

- Missing env var (API key, config flag) — the app silently degrades
- App crashed at startup — check `s.alive` after each second
- Text uses Unicode that doesn't appear in `screen.text` — check
  individual cells: `s.screen.cells[row][col].char`
- App is waiting for stdin you haven't provided

## §C — Race condition

A test that passes sometimes is almost always missing a wait between
input and assertion. **Never** patch with `asyncio.sleep`; add the
right primitive:

```python
# BAD — fast on your laptop, flaky in CI
await tui.press("ctrl+p")
await asyncio.sleep(0.5)
assert "Settings" in tui.screen.text

# GOOD — deterministic everywhere
await tui.press("ctrl+p")
await tui.wait_for_text("Settings")
assert "Models" in tui.screen.text
```

If the screen continues changing after the wait (animations, layout
debouncing), follow with `wait_for_stable`:

```python
await tui.wait_for_text("Settings")
await tui.wait_for_stable(quiet_ms=150)
assert "Models" in tui.screen.text
```

## §D — Input goes nowhere

Triage in a debug script:

```python
print("mouse on:", tui._emu.is_mouse_tracking())
print("paste on:", tui._emu.is_bracketed_paste())
print("focus on:", tui._emu.is_focus_events())
print("DEC modes:", sorted(tui._emu.private_modes))
```

If the relevant mode is **off**, the app hasn't enabled it yet. Wait:

```python
await tui.wait_for_predicate(
    lambda _: tui._emu.is_mouse_tracking(),
    timeout=3,
    description="mouse tracking",
)
```

If the mode is on but input still has no effect, the app probably
debounces — many widgets process one event per render tick. Add a
stable wait between rapid presses:

```python
for _ in range(5):
    await tui.press("down")
    await tui.wait_for_stable(quiet_ms=50)
```

Special characters worth knowing about:

- `\x13` (Ctrl-S) and `\x11` (Ctrl-Q) are flow control in cooked mode.
  `TuiSession.start` puts the PTY in raw mode so they pass through.
  If you bypass the session and use `PtyTransport` directly, set raw
  mode yourself.
- `\x7f` (DEL, the Backspace key) is `VERASE` in cooked mode. Same
  fix.

## §E — Snapshot flaps

Cell-grid snapshots compare cursor position, mode set, and cell attrs
— not just text. Flakiness usually comes from:

1. **Cursor twitch.** The cursor moves during a redraw. Add
   `wait_for_stable(quiet_ms=200)` before the assertion.
2. **A DEC mode toggling on/off.** Make sure mode-setting completes
   before the snapshot.
3. **Variable text in the render.** Version numbers, timestamps,
   working directory, model names. Either stub them via env vars or
   snapshot a region that excludes them.

## Repeat to confirm

A test fails once → it's flaky.
A test fails 5/20 → it's reliably flaky.
A test fails 20/20 → it's broken (good news, much easier).

```bash
for i in $(seq 20); do
  pytest tests/test_x.py::test_thing -q --timeout=20 || echo "FAIL $i"
done | grep -c FAIL
```

## When you really can't reproduce

1. Bump `--tui-timeout=30` and `--timeout=60` — slow runners hide
   issues.
2. `pytest --tui-trace=on` and inspect the cast file with
   [asciinema-player](https://docs.asciinema.org/manual/player/).
3. Add `RUST_BACKTRACE=1` (or your runtime's equivalent) to `env=` so
   crashes show up clearly.
4. Open an issue with the cast file — they're plain JSON, small, and
   100% reproduce-able locally.

Next: [CI integration →](ci.md)
