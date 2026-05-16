# Install

## Requirements

| | Minimum |
|---|---|
| Python | 3.11 |
| OS | macOS, Linux (Windows ConPTY support is on the roadmap) |
| Optional | [`agg`](https://github.com/asciinema/agg) for PNG snapshot regression |

## Install the package

=== "uv"

    ```bash
    uv add --dev tuiwright
    ```

=== "pip"

    ```bash
    pip install tuiwright
    ```

=== "poetry"

    ```bash
    poetry add --group dev tuiwright
    ```

That's it. `tuiwright` ships as a pytest plugin via entry points — there
is no `conftest.py` boilerplate to add.

Verify the install:

```bash
python -c "import tuiwright; print(tuiwright.__version__)"
```

## Install `agg` (optional, for PNG snapshots)

[`agg`](https://github.com/asciinema/agg) is the asciinema GIF/PNG
generator. `tuiwright` shells out to it when you call `tui.png()` or
compare against a [PNG snapshot](snapshots/png.md).

=== "Homebrew (macOS)"

    ```bash
    brew install agg
    ```

=== "Cargo (any OS)"

    ```bash
    cargo install --git https://github.com/asciinema/agg
    ```

Without `agg`, cell-grid snapshots still work — only PNG assertions
require it, and they raise a clear error pointing at this page if it's
missing.

## What gets installed

`tuiwright` has these runtime dependencies:

| Package | Why |
|---|---|
| `ptyprocess` | The PTY transport layer |
| `pyte` | Pure-Python VT102 emulator |
| `pytest` + `pytest-asyncio` | Test runner integration |
| `syrupy` | Snapshot infrastructure |
| `pillow`, `pixelmatch` | PNG comparison |

All are pure-Python — no native compilation step.

## Editor support

The package ships with `py.typed`, so:

- VS Code (with Pylance / Pyright) gets full IntelliSense
- PyCharm gets type hints in tooltips and autocomplete
- mypy and pyright treat it as a typed package

## Troubleshooting

??? question "I get `ModuleNotFoundError: No module named 'tuiwright'` in CI"

    The `tui` fixture is discovered via pytest entry points. If you're
    running pytest in a venv that doesn't have `tuiwright` installed,
    you'll see this. Confirm with `pip list | grep tuiwright`.

??? question "Tests fail with `FileNotFoundError: agg`"

    PNG snapshot assertions need the `agg` binary on your `PATH`.
    Install it as shown above, or remove PNG snapshot assertions and
    rely on [cell-grid snapshots](snapshots/cell-grid.md) only.

??? question "Tests work locally but timeout in CI"

    CI runners are slower than your laptop, especially the first
    cold-start. Bump the default timeout with `--tui-timeout=15` or set
    it per-test with `@pytest.mark.tui(timeout=15)`.

Next: [Quickstart →](quickstart.md)
