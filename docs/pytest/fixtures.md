# Fixtures

`tuiwright` registers a pytest plugin via the standard `pytest11`
entry point. Installing the package gives you the fixtures —
no `conftest.py` boilerplate.

## `tui`

The primary fixture: one `TuiSession` per test, auto-stopped on
teardown.

```python
import pytest
from tuiwright import TuiSession

pytestmark = pytest.mark.asyncio


async def test_thing(tui: TuiSession):
    await tui.start("myapp")
    await tui.wait_for_text("Ready")
    assert tui.alive
```

Scope: **function**. Each test gets a fresh session — no shared state.

## `tui_factory`

For tests that need multiple sessions (multi-pane scenarios,
client/server within the same test):

```python
async def test_two_panes(tui_factory):
    a = tui_factory()
    b = tui_factory()

    await a.start("myapp", cols=80, rows=24)
    await b.start("myapp", cols=80, rows=24)

    await a.wait_for_text("Ready")
    await b.wait_for_text("Ready")

    # Both sessions are independent; the fixture stops both on teardown.
```

Each call to `tui_factory()` returns a fresh `TuiSession`. The
fixture tracks them and stops every one in cleanup.

## `tui_config`

The `TuiConfig` derived from CLI flags and the active `@pytest.mark.tui`
marker. Override per-test by depending on it explicitly:

```python
async def test_override(tui_config, tui):
    tui_config.cols = 200
    tui_config.rows = 60
    await tui.start("myapp")    # uses 200×60
```

You usually don't need this — the marker is more declarative.

## `snapshot` (from syrupy)

Comes with `syrupy`, which `tuiwright` pulls in as a runtime
dependency. Combine with one of the `tuiwright` snapshot extensions:

```python
from syrupy.assertion import SnapshotAssertion
from tuiwright._snapshot import ScreenSnapshotExtension, PNGSnapshotExtension


async def test_screen(tui, snapshot: SnapshotAssertion):
    await tui.start("myapp")
    await tui.wait_for_stable(quiet_ms=200)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
```

See:

- [Cell-grid snapshots](../snapshots/cell-grid.md)
- [PNG snapshots](../snapshots/png.md)

## Common patterns

### A shared "ready" helper

If most tests start the same way, factor it into a helper rather than
a fixture (so each test stays self-documenting):

```python
async def _ready(tui, gode_bin, gode_env):
    await tui.start([gode_bin], env=gode_env, cols=140, rows=44)
    await tui.wait_for_text("Ask gode to work on this repo", timeout=12)
    await tui.wait_for_stable(quiet_ms=150)
```

This reads better in test bodies than a magic fixture, and it keeps
the startup wait explicit.

### Project-specific fixtures in `conftest.py`

Your project will often have its own binary path, env vars, and
auth setup. Put those in `tests/conftest.py`:

```python
import os
import pytest


@pytest.fixture
def myapp_bin() -> str:
    return os.environ.get("MYAPP_BIN", "/usr/local/bin/myapp")


@pytest.fixture
def myapp_env() -> dict[str, str]:
    return {
        "MYAPP_LOG_LEVEL": "warn",
        "API_KEY": os.environ.get("API_KEY", "test-key"),
    }
```

Then in tests:

```python
async def test_thing(tui, myapp_bin, myapp_env):
    await tui.start([myapp_bin], env=myapp_env)
    ...
```

## Async setup

The project's `pyproject.toml` should have:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
```

This means:

- `async def test_*` works without `@pytest.mark.asyncio` decorators.
- Each test gets a fresh asyncio loop (matches the `tui` fixture's
  function scope).

Without `asyncio_mode = "auto"`, add `pytestmark = pytest.mark.asyncio`
at the top of every test file.

Next: [Marker →](marker.md)
