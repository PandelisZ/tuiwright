# gode example suite

End-to-end tests for [`gode`](https://github.com/cosine-ai/gode), the
ratatui+crossterm TUI that motivated `tuiwright`.

## Setup

The tests assume a `gode` binary is on `PATH` or referenced by the
`GODE_BIN` environment variable.

```bash
# build in the gode repo:
cd /path/to/gode
cargo build --release -p roder-cli
# point the tests at it:
export GODE_BIN=/path/to/gode/target/release/gode
# or:
export GODE_BIN=/Users/pz/w/gode/bin/gode
```

These tests use the gode CLI's mock-provider path. You'll want to set a
dummy `OPENAI_API_KEY` so the provider initialisation doesn't bail.

```bash
export OPENAI_API_KEY=sk-test
pytest examples/gode/
```

## What's tested

| Test | What it covers |
|---|---|
| `test_startup_ready` | gode launches and the composer shows |
| `test_composer_echo` | typing reaches the composer widget |
| `test_palette_toggle` | `ctrl+p` opens / closes the command palette |
| `test_resize_no_panic` | resizing from 120×40 to 80×24 does not crash |
| `test_bracketed_paste` | pasting a multi-line string is one composer edit |

The tests are deliberately tolerant — they assert on text presence
rather than exact layout, so reskinning gode does not break them. The
fragile bits (exact cell positions, colours) live in
`test_visual_regression.py` which uses `ScreenSnapshotExtension`.
