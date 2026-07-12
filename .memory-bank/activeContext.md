# Active Context
> Updated: 2026-07-08

## Current State
- No active implementation guide.
- `smart-trim` is the PreCompact handler package behind the `~/.claude/hooks/smart-trim.py` shim.

## Durable Notes
- `post_json` was intentionally dropped during the v3.2 to v3.3 split; summarization uses `ollama_client.chat` / `cheap_complete`.
- Do not store compact-session directives or transient prompt rules in agent memory.
