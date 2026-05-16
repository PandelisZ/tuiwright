# Cell-grid snapshots

Cell-grid snapshots freeze the rendered screen as a **text file** —
diffable in a PR review, immune to font choice and OS rendering
differences. This is the workhorse regression strategy for `tuiwright`.

## Quick start

```python
import pytest
from syrupy.assertion import SnapshotAssertion
from tuiwright import TuiSession
from tuiwright._snapshot import ScreenSnapshotExtension

pytestmark = pytest.mark.asyncio


async def test_layout(tui: TuiSession, snapshot: SnapshotAssertion):
    await tui.start("myapp", cols=120, rows=30)
    await tui.wait_for_text("Ready")
    await tui.wait_for_stable(quiet_ms=200)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

First run creates the snapshot:

```bash
pytest --snapshot-update
```

Commit the generated `.screen` file under
`tests/__snapshots__/<test_module>/`.

## What gets serialised

The snapshot file has three parts:

```
# tuiwright screen snapshot v1
# cols=120 rows=30 cursor=(29,119) hidden modes=[1003, 1006, 1049, 2004]
+────────────────────────────────────────...────+
| <row 0, padded to col width>                  |
| <row 1>                                       |
| ...                                           |
+────────────────────────────────────────...────+
{
  "0,5": {"fg": "ff8800", "bold": true},
  "3,12": {"bg": "blue"}
}
```

1. A header with dimensions, cursor position, hidden flag, and the
   DEC modes that are currently on.
2. An ASCII frame containing the rendered text, one row per line,
   padded to the column width so column-alignment is preserved.
3. A JSON map of cell attributes — only for cells whose attributes
   differ from default. Most cells default, so this stays tiny.

## Why this format

- **Readable in a PR.** A 120×30 snapshot is a single 30-line block
  with a frame around it. A reviewer can see the layout at a glance.
- **Stable hash.** No fonts, no anti-aliasing, no OS rendering. Two
  identical screens always produce identical files.
- **Diffable.** GitHub's PR diff highlights changed rows. `git diff`
  works as you'd expect.
- **Lossless on attrs.** The JSON sidecar preserves fg/bg/bold/etc
  without bloating the human-readable frame.

## What it catches

| Change | Snapshot diff |
|---|---|
| Text changes anywhere | One or more rows differ |
| Layout shifts | Multiple rows differ |
| Cursor moves to a new cell | Header line changes |
| Cursor visibility toggles | Header line changes |
| New DEC mode enabled | Header line changes |
| Colour change on one cell | One JSON entry differs |
| Bold/italic toggle | One JSON entry differs |
| Hidden whitespace change | Padded row differs |

## What it misses

- **Pixel-level rendering bugs.** Font kerning, ligatures, ambiguous-width
  characters that render differently on different terminals. Use
  [PNG snapshots](png.md) for these.
- **Truly off-screen state.** Anything not in the current viewport.

## Stability rules

Snapshots are diffable artifacts — keep them deterministic:

- **Pin terminal size.** Never rely on `--tui-cols` defaults — the
  test should declare `cols=` and `rows=` explicitly.
- **Settle before capture.** Always call `wait_for_stable(quiet_ms=200)`
  after the last interaction.
- **Mock variable state.** Version strings, timestamps, random IDs,
  hostnames — all of these will churn your snapshot unnecessarily.
  Either stub them in the app via env vars (the app's job) or scope
  the assertion to a region that excludes them.

## Updating

When you intentionally change the UI:

```bash
# update all snapshots
pytest --snapshot-update

# update just one test
pytest tests/test_layout.py::test_thing --snapshot-update

# review what would change without writing
pytest --snapshot-warn-unused
```

Commit the updated snapshot file as part of the same PR that changes
the UI — reviewers can see both changes side-by-side.

## Region snapshots

Snapshot just one panel rather than the whole screen:

```python
async def test_status_bar(tui, snapshot):
    await tui.start("myapp")
    await tui.wait_for_text("Ready")
    await tui.wait_for_stable(quiet_ms=150)

    status = tui.region(rows=(tui.screen.rows - 1, tui.screen.rows), cols=(0, tui.screen.cols))
    assert status.text == snapshot
```

For region snapshots, `snapshot` (no extension class) defaults to
syrupy's plain-text serializer — clean and minimal.

## Multiple snapshots per test

Use the `name=` parameter to namespace several snapshots in one test:

```python
async def test_workflow(tui, snapshot):
    await tui.start("myapp")
    await tui.wait_for_text("Ready")
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension, name="initial")

    await tui.press("ctrl+p")
    await tui.wait_for_text("Settings")
    await tui.wait_for_stable(quiet_ms=150)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension, name="settings_open")
```

Files land as `test_workflow__initial.screen` and
`test_workflow__settings_open.screen`.

Next: [PNG snapshots →](png.md)
