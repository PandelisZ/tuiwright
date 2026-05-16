---
name: tuiwright-run
description: Pick the right pytest invocation for a tuiwright-driven test goal — full suite, single file, snapshot update, flake hunt, verbose with trace. Use whenever the user asks to "run the tests", "update snapshots", or "check for flakes" in a tuiwright project.
---

# Running tuiwright tests

Map the user's goal to the right command. Always run from the project
root (the one with `pyproject.toml`).

| Goal | Command |
|---|---|
| Run everything, fast | `uv run pytest -q` |
| Run everything, verbose | `uv run pytest -v` |
| Run one file | `uv run pytest tests/test_x.py -v` |
| Run one test | `uv run pytest tests/test_x.py::test_thing -v` |
| Run by keyword | `uv run pytest -k "mouse and not slow"` |
| Update snapshots | `uv run pytest --snapshot-update` |
| Update only one test's snapshot | `uv run pytest -k name --snapshot-update` |
| Keep cast files on pass | `uv run pytest --tui-trace=on` |
| Pin terminal size | `uv run pytest --tui-cols=120 --tui-rows=30` |
| Bump global timeout | `uv run pytest --tui-timeout=15` |
| Flake hunt | `for i in 1 2 3 4 5; do uv run pytest -q --timeout=30 || break; done` |
| First failure, short trace | `uv run pytest -x --tb=short` |
| With debugger on failure | `uv run pytest --pdb` |

## When to update snapshots

ONLY after confirming with the user (or after they explicitly asked)
that the rendering change is intentional. Snapshot files are committed
artifacts; updating them is equivalent to approving a UI diff.

## When a test hangs

A "hang" usually means a `wait_for_*` is waiting for text that never
appears. Run with `--timeout=10` to force a timeout, then the failure
message dumps the full last screen — that tells you what's actually
rendered. **Don't** add `await asyncio.sleep(n)` to "give it time" —
that hides the real issue.

```bash
uv run pytest tests/test_x.py::test_thing -v --timeout=10
```

## When tests pass locally but fail in CI

Common causes:

- `agg` not installed in CI → PNG snapshot tests can `pytest.skip`,
  not fail. Check if the runner has it.
- Stale snapshots from a UI change → run locally with
  `--snapshot-update`, commit, push.
- Terminal size differs → CI may default to 80×24. Pin sizes in tests.
- Timing assumptions → bump `--tui-timeout` in CI or use
  `wait_for_stable` more aggressively.

## After running

Always report back with:

- pass/fail counts
- the duration
- if anything was non-deterministic (a test passing only sometimes),
  flag it as a flake and suggest `tuiwright-debug`
