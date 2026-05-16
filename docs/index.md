---
hide:
  - navigation
  - toc
---

# tuiwright

**Playwright-style end-to-end testing for terminal UI applications.**

`tuiwright` spawns any TUI binary under a real pseudo-terminal, parses
its output through a faithful VT102 emulator, and lets you assert on
the rendered screen with an async pytest API. Keys, text, mouse,
bracketed paste, resize, focus events — all first-class. Cell-grid and
PNG snapshot regression out of the box.

```python
import pytest
from tuiwright import TuiSession
from tuiwright._snapshot import ScreenSnapshotExtension

pytestmark = pytest.mark.asyncio


async def test_save_flow(tui: TuiSession, snapshot):
    await tui.start("myapp", cols=120, rows=40)
    await tui.wait_for_text("Ready")

    await tui.type("hello world")
    await tui.press("ctrl+s")
    await tui.wait_for_text("Saved")

    await tui.click(row=5, col=12)
    await tui.assert_region(title="Logs", contains="saved hello world")

    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

## Why it exists

The TUI testing ecosystem is fragmented:

<div class="grid cards" markdown>

-   :material-keyboard:{ .lg .middle } **`pexpect` / `expect`**

    ---
    Line/regex-oriented. Break the moment your app uses cursor addressing.

-   :material-record:{ .lg .middle } **`vhs`, `asciinema`**

    ---
    Demo recording, not designed for assertions.

-   :material-bee-flower:{ .lg .middle } **Textual `Pilot`, `teatest`**

    ---
    In-process — never exercise the real binary or the PTY.

-   :material-camera:{ .lg .middle } **`insta`, `syrupy`**

    ---
    Assertion layer only, no driver.

</div>

`tuiwright` is the missing piece: **black-box, async, snapshot-aware,
ergonomic**.

## Highlights

- :material-language-python: **Pure Python**. Pure-Python deps too —
  no native build, no docker, no chromium.
- :material-keyboard-outline: **Real input.** Keys, text, mouse
  (click/scroll/drag/hover), bracketed paste, resize, focus events.
- :material-clock-outline: **No `sleep()` ever.** Wait primitives are
  predicate-driven and settle-based; tests are fast on healthy
  machines and reliable on slow ones.
- :material-image-multiple: **Two regression modes.** Cell-grid
  snapshots (text + per-cell attrs, reviewable as a diff) and PNG
  snapshots (via `agg` + `pixelmatch`).
- :material-test-tube: **First-class pytest.** `tui` fixture, marker,
  CLI flags, asciinema cast retention on failure.

## Get started in 30 seconds

=== "uv"

    ```bash
    uv add --dev tuiwright
    ```

=== "pip"

    ```bash
    pip install tuiwright
    ```

Then write a test:

```python
async def test_my_tui(tui):
    await tui.start("path/to/binary")
    await tui.wait_for_text("Ready")
    await tui.type("hello")
    await tui.press("enter")
    assert "hello" in tui.screen.text
```

Continue with the [Install guide](install.md) →
