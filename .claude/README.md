# Claude skills for tuiwright

This directory holds the Claude Code copy of the bundled skills. The
**canonical** vendor-neutral location is `.agents/skills/` — the
content here is kept identical for runtimes (Claude Code) that only
look inside `.claude/`.

If you update a skill, update both `.claude/skills/<name>/SKILL.md`
**and** `.agents/skills/<name>/SKILL.md`. The duplication is
intentional — symlinks don't survive shallow clones, Windows
archives, or several CI cache strategies.

## Available skills

| Slash command | Purpose |
|---|---|
| `/tuiwright-test` | Scaffold a new E2E test with proper fixtures, waits, and snapshot patterns |
| `/tuiwright-run` | Pick the right pytest invocation for a goal (full / one file / snapshot update / flake hunt) |
| `/tuiwright-debug` | Diagnose flaky, hanging, or mysteriously failing tests |

The repo's `CLAUDE.md` is the overall agent-orientation doc — read it
once to get architecture context before invoking any skill.
`AGENTS.md` at the repo root carries the same orientation for
non-Claude agents.

## How Claude Code loads these

Claude Code looks for `.claude/skills/<name>/SKILL.md` files relative
to the working directory. The first line block (the YAML front matter
with `name:` and `description:`) is the trigger spec — Claude uses
the description to decide when to invoke the skill.

If you're using a runtime that doesn't auto-load, copy these into
your own `~/.claude/skills/` directory and they'll work globally.

## See also

- [`../AGENTS.md`](../AGENTS.md) — repo orientation for non-Claude
  agents
- [`../.agents/`](../.agents/) — vendor-neutral skill mirror
- [`../CLAUDE.md`](../CLAUDE.md) — Claude Code repo orientation
