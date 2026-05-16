# `@pytest.mark.tui`

Per-test configuration without depending on `tui_config` directly.

```python
import pytest


@pytest.mark.tui(cols=140, rows=44, timeout=10, strict_mouse=True)
async def test_big_screen(tui):
    await tui.start("myapp")
    ...
```

## Options

| Key | Default | Purpose |
|---|---|---|
| `cols` | 80 | Terminal width |
| `rows` | 24 | Terminal height |
| `timeout` | 5.0 | Default `wait_for_*` timeout (seconds) |
| `strict_mouse` | `False` | Raise instead of warn when mouse input is sent before the app enabled tracking |

The marker takes precedence over CLI flags (`--tui-cols`, `--tui-rows`,
`--tui-timeout`).

## When to use it vs. inline `tui.start(cols=…)`

The marker is right when **every action in the test** needs the same
size:

```python
@pytest.mark.tui(cols=160, rows=50)
async def test_wide_layout(tui):
    await tui.start("myapp")
    await tui.wait_for_text("...")
    # any subsequent resize is still possible, but starts at 160×50
```

The `tui.start(cols=…)` keyword is right when you want to **override
once** within an otherwise default test:

```python
async def test_resize_flow(tui):
    await tui.start("myapp", cols=80, rows=24)   # explicit start size
    await tui.resize(160, 50)                    # then grow
```

## Common configurations

```python
# A larger viewport for layout snapshots
@pytest.mark.tui(cols=120, rows=30)

# Strict mouse mode for a click-heavy suite
@pytest.mark.tui(strict_mouse=True)

# Slow CI runner — bump the wait timeout
@pytest.mark.tui(timeout=15)

# Combined
@pytest.mark.tui(cols=140, rows=44, timeout=10, strict_mouse=True)
```

## Registering markers

The plugin registers `tui` as a known marker, so you won't get
"unknown marker" warnings. If you've enabled strict markers
(`filterwarnings = error::pytest.PytestUnknownMarkWarning`), this is
seamless.

Next: [CLI flags →](cli.md)
