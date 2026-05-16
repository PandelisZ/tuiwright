# `.agents/` — vendor-neutral skills for tuiwright

This directory follows the emerging convention of putting cross-agent
skill / instruction files under `.agents/` so any coding agent
(Codex CLI, Cursor, Continue, Aider, Claude Code, etc.) can find them
in one canonical place.

The repo also exposes:

| File / dir | Audience |
|---|---|
| `AGENTS.md` (repo root) | Codex CLI and any agent honouring the [agents.md](https://agents.md) convention |
| `.claude/skills/` | Claude Code's slash-command skill loader |
| `.agents/skills/` | Vendor-neutral mirror — same content as `.claude/skills/` |

All three carry **identical guidance**. If you update one, update the
others. The duplication is intentional — symlinks don't survive
shallow clones, Windows archives, or several CI cache strategies.

## Skills

| Skill | Purpose |
|---|---|
| `tuiwright-test` | Scaffold a new E2E test with proper fixtures, waits, and snapshot patterns |
| `tuiwright-run` | Pick the right pytest invocation for a goal — full suite / one file / snapshot update / flake hunt |
| `tuiwright-debug` | Diagnose flaky, hanging, or mysteriously failing tests |

## How agents discover these

Each agent has its own loader logic:

- **Codex CLI** reads `AGENTS.md` at the repo root automatically.
- **Cursor** reads `.cursor/rules/*.mdc` (not provided yet — file an
  issue if you want them).
- **Claude Code** loads any `*.md` in `.claude/skills/<name>/` as a
  slash-command.
- **Aider / Continue / etc.** vary — many just look for `AGENTS.md`.

If your agent doesn't look in any of the above paths, copy
`.agents/skills/` into whatever location your runtime expects.

## Adding a new skill

Mirror this structure across all three locations:

```
.agents/skills/<your-skill>/SKILL.md
.claude/skills/<your-skill>/SKILL.md
```

Each `SKILL.md` should start with YAML front-matter:

```markdown
---
name: your-skill
description: When to invoke - be specific about user phrases that should trigger this.
---

# Body — procedural, push the agent toward correct actions
```
