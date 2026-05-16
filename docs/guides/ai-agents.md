# Use with AI agents

`tuiwright` ships with `.claude/` skills that make it easy for AI
coding agents (Claude Code, Cursor, anything that honours the
`.claude/skills/` convention) to drive the framework.

## What's bundled

| Slash command | Purpose |
|---|---|
| `/tuiwright-test` | Scaffold a new E2E test with proper fixtures, waits, and snapshot patterns |
| `/tuiwright-run` | Pick the right pytest invocation for a goal — full suite / one file / snapshot update / flake hunt |
| `/tuiwright-debug` | Diagnose flaky, hanging, or mysteriously failing tests |

Plus `CLAUDE.md` at the repo root — an agent-orientation doc covering
architecture, invariants, and common gotchas. Agents that read this
file before working on the codebase make far fewer mistakes.

## How agents discover skills

Most agent runtimes (Claude Code, Cursor with custom rules, etc) look
for `.claude/skills/<name>/SKILL.md` files relative to the working
directory. The YAML front matter with `name:` and `description:` is
the trigger spec.

If your runtime doesn't auto-load, copy the skill files into your own
`~/.claude/skills/` directory for global availability.

## Using the skills

In Claude Code (or a compatible agent):

```
> /tuiwright-test
```

Then describe the test you want:

```
> Write a tuiwright test for the help screen — it opens with ? and shows
> a "Keyboard shortcuts" header.
```

The skill walks the agent through the right structure:
`tui.start` → `wait_for_text` → `tui.press("?")` → `wait_for_text("Keyboard shortcuts")`
→ assertion. No `asyncio.sleep`, no race conditions.

## Why pre-built skills help

AI agents writing TUI tests from scratch tend to:

- Use `asyncio.sleep` as a "wait for state" substitute → flaky tests
- Skip `wait_for_stable` after startup → races against the status bar
- Click before the app enables mouse tracking → silently-ignored input
- Snapshot without settling → flapping snapshots

The skills push the agent toward the patterns that work the first
time. They contain the same gotchas any human contributor would learn
the hard way over their first week.

## Adding your own project skills

Mirror the structure inside your project:

```
your-project/
├── .claude/
│   ├── skills/
│   │   └── your-skill/
│   │       └── SKILL.md
│   └── README.md
└── CLAUDE.md            # repo-level orientation
```

A useful project-level skill might be `/test-feature-x` that knows
your specific binary path, env vars, and stable startup markers. It
saves the agent re-discovering them every session.

## Reference

Browse the bundled skills in the
[tuiwright repo](https://github.com/PandelisZ/tuiwright/tree/master/.claude/skills).
Each `SKILL.md` is short and worth reading once if you write tests by
hand too — they capture the framework's "spirit" in a few hundred
lines.

Next: [API reference →](../api.md)
