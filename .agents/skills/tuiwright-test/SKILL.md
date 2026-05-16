---
name: tuiwright-test
description: Scaffold a new tuiwright end-to-end test for a TUI binary. Use when the user asks to write, add, or stub an E2E test for a terminal application (e.g. "write a test for the help screen", "add a tuiwright test for the new command palette"). Produces a deterministic, snapshot-aware test that uses wait_for_* primitives — never asyncio.sleep.
---

# Writing a tuiwright test

You are scaffolding a new end-to-end TUI test using the tuiwright framework.

## Before you write code

Confirm in one sentence:

1. **What binary is under test?** (path, argv, env vars it needs)
2. **What user flow are you testing?** (one sentence; the test name)
3. **What's the assertion?** (text appears, region content, snapshot
   matches, app stays alive after action)

If any of these are unclear, ask the user once before writing.

## Test template

```python
import pytest

from tuiwright import TuiSession

pytestmark = pytest.mark.asyncio


async def test_<user_flow>(
    tui: TuiSession, gode_bin: str, gode_env: dict[str, str]
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=140, rows=44)
    # Wait for a UI signal that startup is complete. Pick the LAST
    # thing that paints — usually a footer, status, or composer label.
    await tui.wait_for_text("<startup marker>", timeout=12)
    await tui.wait_for_stable(quiet_ms=150)

    # Drive the flow.
    await tui.press("ctrl+p")        # or .type(...), .click(row, col), etc.
    await tui.wait_for_text("<post-action marker>", timeout=3)

    # Assert.
    assert "<expected substring>" in tui.screen.text
    # or, for layout regression:
    # from tuiwright._snapshot import ScreenSnapshotExtension
    # assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

## Rules of thumb

- **Never `asyncio.sleep` for state.** Use `wait_for_text`,
  `wait_for_predicate`, or `wait_for_stable`. Sleeping makes tests
  slow on healthy machines and flaky on slow ones.
- **`wait_for_text` first, assert second.** If you `assert "foo" in
  tui.screen.text` without a preceding wait, you're racing the render.
- **Pick stable text.** Avoid version numbers, timestamps, random IDs.
  Use UI strings that ship in the source (labels, headers).
- **Between rapid input bursts**, add a `wait_for_stable(quiet_ms=80)`.
  Many TUIs process one event per render tick.
- **Snapshot tests need stable layout.** Use the same `cols` and `rows`
  every time. Pin them in the test, don't rely on terminal defaults.

## When the user wants a snapshot test

```python
from syrupy.assertion import SnapshotAssertion
from tuiwright._snapshot import ScreenSnapshotExtension

async def test_<thing>_layout(
    tui: TuiSession,
    gode_bin: str,
    gode_env: dict[str, str],
    snapshot: SnapshotAssertion,
) -> None:
    await tui.start([gode_bin], env=gode_env, cols=120, rows=30)
    await tui.wait_for_text("<startup marker>")
    await tui.wait_for_stable(quiet_ms=200)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

Run with `--snapshot-update` the first time to create the file. Commit
the `.screen` file alongside the test — reviewers can read the ASCII
frame.

## When the user wants mouse, paste, or focus

These need the app to enable the corresponding DEC mode first. Wait
for it explicitly:

```python
await tui.wait_for_predicate(
    lambda _: tui._emu.is_mouse_tracking(),  # type: ignore[attr-defined]
    timeout=3,
    description="mouse tracking enabled",
)
await tui.click(row=10, col=20)
```

Without the wait, you'll get a one-time warning and the input will be
ignored by the app.

## Confirmation checklist before reporting done

- [ ] Test uses `async def` (no `@pytest.mark.asyncio` decorator
      needed when the project is in `asyncio_mode = "auto"`)
- [ ] No bare `asyncio.sleep` for state
- [ ] Every `await tui.<action>` is followed by a `wait_for_*` or
      `wait_for_stable` before assertions
- [ ] Cols/rows are pinned for any snapshot test
- [ ] The test runs (`uv run pytest path/to/test_x.py -v`) and passes
      twice in a row (flake check)
