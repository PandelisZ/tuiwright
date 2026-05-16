---
name: tuiwright-debug
description: Diagnose flaky, hanging, or mysteriously failing tuiwright tests. Use when a test fails intermittently, times out, or shows a screen state the user didn't expect — covers the most common causes (race conditions in waits, DEC mode timing, PTY mangling, snapshot churn) and how to narrow each down.
---

# Debugging a tuiwright test

You are diagnosing why a tuiwright-driven test is misbehaving. Work
top-down: the most common issues are timing-related, not bugs in the
framework or the app.

## 1. Reproduce deterministically

```bash
uv run pytest tests/test_x.py::test_thing -v --timeout=15
```

The failure dump includes the **full last screen** — read it first.
Often the answer is right there: a modal you didn't expect, a status
line that says "loading", text that's been truncated.

## 2. Classify the failure

| Symptom | Most likely cause | Section |
|---|---|---|
| `TuiTimeoutError: timed out waiting for text 'X'` and screen shows 'X' | Region snapshot stale, or text in a different region | §A |
| `TuiTimeoutError` and screen does NOT show 'X' | App hasn't rendered yet, or won't | §B |
| Test passes once, fails next run | Race / timing | §C |
| Input has no effect | DEC mode not enabled, or PTY line-discipline mangled it | §D |
| Snapshot diff on unchanged code | Cursor position changed, mode flag changed, env var leaked | §E |

## §A — Wait completes but assertion sees stale state

Happens when the user grabbed `region = tui.region(...)` before
the screen finished rendering and then passed it back to
`wait_for_text`. `wait_for_text(region=...)` re-resolves bounds from
the *current* screen on every poll, but if the user stored
`region.text` directly somewhere, that's frozen.

**Fix:** never store `region.text`; always re-fetch via `tui.region(...)`
or pass the spec to `wait_for_text`.

## §B — Text just isn't appearing

```bash
uv run python -c "
import asyncio
from tuiwright import TuiSession
async def main():
    s = TuiSession()
    await s.start(['<binary>'], env={'API_KEY': 'sk-test'}, cols=140, rows=44)
    for i in range(10):
        await asyncio.sleep(1)
        print(f'--- t={i+1}s ---')
        print(s.screen.text)
        if '<expected>' in s.screen.text: break
    await s.stop()
asyncio.run(main())
"
```

Common causes:

- App needs an API key / env var. Add it to `env=`.
- App is waiting on stdin you haven't provided. Send the right key.
- App died early. Check `s.alive` after each tick.
- Text is rendered with attrs that change the visible char (e.g. a
  ligature). Check `s.screen.cells[row][col]` directly.

## §C — Race conditions

A test that passes sometimes is almost always missing a `wait_for_*`
between an input and an assertion. Don't fix with `asyncio.sleep` —
add the right wait:

```python
await tui.press("ctrl+p")
await tui.wait_for_text("Settings")        # not asyncio.sleep(0.5)
assert "Models" in tui.screen.text
```

If the screen changes after the wait fires (e.g. animations,
debounced layout), follow with `wait_for_stable`:

```python
await tui.wait_for_text("Settings")
await tui.wait_for_stable(quiet_ms=150)
assert "Models" in tui.screen.text
```

## §D — Input goes nowhere

Quick triage:

```python
# In a debug script:
print("mouse tracking on:", tui._emu.is_mouse_tracking())
print("paste mode on:", tui._emu.is_bracketed_paste())
print("focus mode on:", tui._emu.is_focus_events())
print("DEC modes:", sorted(tui._emu.private_modes))
```

If the relevant mode is **off**, the app hasn't enabled it yet. Wait
for it:

```python
await tui.wait_for_predicate(
    lambda _: tui._emu.is_mouse_tracking(),
    timeout=3,
    description="mouse enabled",
)
```

If the mode is on but input still does nothing, check whether the app
debounces. Rapid input bursts often get coalesced. Add
`wait_for_stable(quiet_ms=80)` between presses.

Special characters: `Ctrl-S` and `Ctrl-Q` are flow control on most
PTYs, but `tuiwright._pty._set_raw_mode` disables IXON / IXOFF
specifically to make these work. If a test bypasses `TuiSession.start`
and writes directly to a raw `ptyprocess.PtyProcess`, it will hit the
old behaviour.

## §E — Snapshot keeps flapping

Causes (in order of likelihood):

1. **Cursor position** is part of the snapshot header. If the cursor
   moves between runs (app re-renders the composer), the snapshot
   changes even when the visible content doesn't. Fix: add a final
   `await tui.wait_for_stable(quiet_ms=200)` before the snapshot.
2. **A DEC mode toggle** got recorded. Modes is part of the header.
   Make sure all mode-setting happens before the snapshot.
3. **Environment-dependent text** in the render — a version number,
   model name, working directory. Mock those out or use a partial
   `region` check instead of a full screen snapshot.

## Last resort

Run the suite 20 times to confirm flakiness:

```bash
for i in $(seq 20); do
  uv run pytest tests/test_x.py::test_thing -q --timeout=20 || echo "FAIL on iter $i"
done | grep -c FAIL
```

0 failures → not flaky, retire the suspicion.
1–3 failures → real but rare race, look harder at the wait_for_* calls.
4+ failures → genuine framework or app bug; capture the failing cast
file and open an issue.
