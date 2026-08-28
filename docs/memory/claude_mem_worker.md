# claude-mem background worker (full text)

<!-- Extracted VERBATIM from CLAUDE.md on 2026-08-28 (issue #46). Nothing here
was rewritten — CLAUDE.md keeps the headline, this file keeps the detail. -->

## claude-mem background worker

The `claude-mem` plugin requires a background worker (Bun) on port **37778**
(set in `~/.claude-mem/settings.json`). The plugin auto-starts it with `--daemon`
when Claude Code opens. A `UserPromptSubmit` hook in `~/.claude/settings.json`
also checks port 37778 and restarts via `Start-Process bun --daemon` if down.
No manual action needed — if you ever see hook errors saying "worker unreachable",
just send any message and the hook will restart it.

To start manually if needed:
```
bun C:/Users/Joshua/.claude/plugins/cache/thedotmack/claude-mem/13.6.1/scripts/worker-service.cjs --daemon
```

