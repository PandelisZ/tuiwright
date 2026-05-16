# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/pandelisz/tuiwright/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pandelisz/tuiwright/releases/tag/v0.1.0
