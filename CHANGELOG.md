# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-05-16

Adds `tuiwright record` — an interactive wrapper that records your
session driving a TUI and generates a pytest test that codifies the
behaviour you just demonstrated.

### Added

- `tuiwright record` CLI subcommand: spawns a TUI under a PTY sized
  to match your real terminal, transparently forwards keystrokes /
  mouse / resize, tees everything to an asciinema v2 cast file.
  Reserved <kbd>Ctrl</kbd>+<kbd>]</kbd> hotkey for snapshot / label /
  stop without forwarding the bytes to the TUI.
- `tuiwright codegen` CLI subcommand: turns a cast file into a
  complete pytest async test. Coarse-by-default style collapses runs
  of printable bytes into `tui.type()`, recognises named keys
  (`"enter"`, `"ctrl+s"`, `"alt+left"`), pretty-prints mouse events
  as `tui.click(row=N, col=N)`, and infers waits from the output
  that arrived between actions (`wait_for_text` when there's a
  distinctive new fragment, `wait_for_stable` otherwise).
- `tuiwright replay` CLI subcommand: re-runs a cast against a fresh
  spawn at the original timing, useful for demos and verifying
  recordings.
- New `tuiwright._record` subpackage with `decoders.py` (reverse of
  `_input.py`), `codegen.py`, and `bridge.py`.
- 61 new tests covering decoders (round-trip with encoders), codegen
  (syntactic validity, action emission, wait inference, snapshot
  markers, styles), and the bridge (end-to-end via a PTY pair).
- New docs page: [Record a test](recording.md), plus updates to
  Hello-TUI, Index, and Writing-tests guides.

## [0.1.0] - 2026-05-16

Initial release.

### Added
- `TuiSession` async driver for spawning TUI binaries under a real PTY.
- Input encoders for keys, text, mouse (SGR 1006), bracketed paste, focus
  events, and `TIOCSWINSZ` resize.
- `Screen` / `Region` / `Cell` model with regex search, titled-region
  detection (ratatui-style `┌─ Title ─┐` borders), and live re-resolution
  inside `wait_for_text`.
- Wait primitives: `wait_for_text`, `wait_for_predicate`, `wait_for_stable`.
- DEC private-mode tracking for mouse / paste / focus, with a warning
  (or strict-mode error) when input is sent to an app that hasn't
  enabled the relevant mode.
- Asciinema cast v2 recording of every session.
- `ScreenSnapshotExtension` (syrupy) for cell-grid regression as a
  reviewable ASCII frame plus a JSON sidecar of cell attributes.
- `PNGSnapshotExtension` (syrupy) for pixel regression via `agg` +
  `pixelmatch`, with graceful degradation when `agg` is unavailable.
- Pytest plugin with `tui` and `tui_factory` fixtures, `@pytest.mark.tui`
  marker, and `--tui-trace` / `--tui-cols` / `--tui-rows` /
  `--tui-timeout` CLI flags.
- Raw-mode setup of the slave PTY's line discipline so input bytes
  (notably DEL `\x7f` and Ctrl-S `\x13`) pass through verbatim
  instead of being mangled by VERASE / IXON.
- Example test suite for [gode](https://github.com/cosine-ai/gode) under
  `examples/gode/`.
- 84 self-tests (input encoders, screen model, emulator, end-to-end
  session against a hand-rolled fixture TUI, snapshot round-trip).

[Unreleased]: https://github.com/PandelisZ/tuiwright/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/PandelisZ/tuiwright/releases/tag/v0.2.0
[0.1.0]: https://github.com/PandelisZ/tuiwright/releases/tag/v0.1.0
