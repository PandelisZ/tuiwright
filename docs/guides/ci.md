# CI integration

`tuiwright` tests run unchanged in CI as long as the runner has a
sane PTY (`/dev/ptmx`) and your TUI binary's deps. macOS and Linux
runners on GitHub Actions, CircleCI, and GitLab CI all qualify.

## GitHub Actions

A complete workflow that:

- Tests on Ubuntu + macOS, Python 3.11 / 3.12 / 3.13
- Installs `agg` for PNG snapshot tests
- Runs a 5-iteration flake check
- Uploads cast files and snapshot diffs on failure

```yaml title=".github/workflows/test.yml"
name: Tests

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  test:
    name: ${{ matrix.os }} · py${{ matrix.python }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install Python
        run: uv python install ${{ matrix.python }}

      - name: Install agg (for PNG snapshots)
        run: cargo install --git https://github.com/asciinema/agg

      - name: Install your TUI binary
        run: cargo build --release && cp target/release/myapp /usr/local/bin/

      - name: Sync deps
        run: uv sync --group dev --python ${{ matrix.python }}

      - name: Test (3 iterations for flake check)
        run: |
          for i in 1 2 3; do
            uv run pytest --tui-timeout=15 --timeout=60 -v
          done

      - name: Upload failure artifacts
        uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: failures-${{ matrix.os }}-py${{ matrix.python }}
          path: |
            tests/__snapshots__/**/*.actual.*
            tests/__snapshots__/**/*.diff.*
            **/*.cast
```

## GitLab CI

```yaml title=".gitlab-ci.yml"
test:
  image: python:3.12-slim
  before_script:
    - apt-get update && apt-get install -y curl
    - curl -LsSf https://astral.sh/uv/install.sh | sh
    - export PATH="$HOME/.local/bin:$PATH"
    - uv sync --group dev
  script:
    - uv run pytest --tui-timeout=15 --timeout=60
  artifacts:
    when: on_failure
    paths:
      - tests/__snapshots__/**/*.actual.*
      - tests/__snapshots__/**/*.diff.*
```

## Cold-start delays

CI runners are slower than your laptop, particularly:

- **First test in a job** — the runner warms up, Python imports take
  longer.
- **First spawn of a release-build binary** — disk cache cold.

Compensate:

```bash
# in CI, bump timeouts
pytest --tui-timeout=15 --timeout=60
```

Or in your test code:

```python
@pytest.mark.tui(timeout=15)
async def test_thing(tui):
    ...
```

## Saving cast files on failure

The default `--tui-trace=retain-on-failure` keeps the asciinema cast
file in the test's `tmp_path`. Configure pytest to keep `tmp_path`
between runs, or copy them out:

```yaml
- name: Save casts
  if: failure()
  run: |
    mkdir -p ci-traces
    find /tmp -name '*.cast' -newer pyproject.toml -exec cp {} ci-traces/ \;
  continue-on-error: true

- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: casts
    path: ci-traces/
```

Open them locally with
[asciinema-player](https://docs.asciinema.org/manual/player/), or
render to GIF with `agg cast.cast out.gif` for sharing in an issue.

## Caching

Both `uv` and `cargo install` have good caches that GitHub Actions
supports natively:

```yaml
- uses: astral-sh/setup-uv@v3
  with:
    enable-cache: true

- uses: Swatinem/rust-cache@v2
```

The `agg` install costs ~30 s without cache, ~5 s with.

## Parallelism

`tuiwright` tests are independent — every test gets its own PTY and
its own session — so you can run them in parallel safely:

```bash
uv run pytest -n auto             # requires pytest-xdist
```

Each parallel worker spawns its own child process; no shared state.

Beware of test count vs. runner CPU: each PTY child uses one core
during render bursts. On a 4-core runner, `-n 4` is the practical
maximum for most apps.

## Determinism

Pin every variable that affects rendering:

```python
@pytest.mark.tui(cols=120, rows=30)
async def test_layout(tui, snapshot):
    await tui.start("myapp", env={
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "TZ": "UTC",
    })
    ...
```

Without these, snapshots may differ between platforms due to locale,
timezone, or terminal-capability differences.

Next: [Use with AI agents →](ai-agents.md)
