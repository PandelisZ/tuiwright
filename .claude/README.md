# Claude skills bundled with tuiwright

This directory ships slash-command skills that make tuiwright easy for
AI coding agents to operate. Anyone using Claude Code (or another
agent that honours the `.claude/skills/` convention) will get them
automatically when they open this repo.

## Available skills

| Slash command | Purpose |
|---|---|
| `/tuiwright-test` | Scaffold a new E2E test with proper fixtures, waits, and snapshot patterns |
| `/tuiwright-run` | Pick the right pytest invocation for a goal (full / one file / snapshot update / flake hunt) |
| `/tuiwright-debug` | Diagnose flaky, hanging, or mysteriously failing tests |

The repo's `CLAUDE.md` is the overall agent-orientation doc — read it
once to get architecture context before invoking any skill.

## How agents discover these

Most agent runtimes look for `.claude/skills/<name>/SKILL.md` files
relative to the working directory. The first line block (the YAML
front matter with `name:` and `description:`) is the trigger spec.

If you're using a runtime that doesn't auto-load, you can copy these
into your own `~/.claude/skills/` directory and they'll work globally.

## Extending

To add a skill, create `.claude/skills/<your-skill>/SKILL.md` with the
following front matter:

```markdown
---
name: your-skill
description: When to invoke this skill — be specific about user phrases.
---

# Skill body…
```

Keep the body procedural — the goal is to push an agent toward the
right action, not to teach the framework from scratch (`CLAUDE.md`
does that).
