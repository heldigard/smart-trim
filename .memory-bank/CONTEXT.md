# Context

- Vertical-slice architecture mirrors `~/codeq/` (`features/<feat>/command.py` +
  `shared/`). One responsibility per feature folder.
- `handle_precompact` (orchestrator) uses **late binding by module** so the
  pytest monkeypatches on origin modules resolve at call time. Do not collapse
  those to direct function imports or tests break.
- `shared/compat.py` is imported once via `smart_trim/__init__.py`; it owns the
  `sys.path` inserts for `~/.claude/scripts/` and the graceful `try/except`
  imports of `ollama_client` / `cheap_complete` / `context_guard_lib`.
- Grounding imports `agent_memory.features.entries.command` as an optional
  package dependency and uses its `filter_lines_for_injection`; missing or
  broken agent-memory degrades to unfiltered memory-bank lines.
- Persisted method labels (`ollama-…`) come from `summarize.primary_label() /
  secondary_label()` — derived from the active model tag, env-aware,
  quantization suffix stripped. Do NOT hardcode label strings elsewhere.
- `shared.paths.default_summaries_dir()` is the single source of truth for
  `~/.claude/summaries`. Both `hygiene.cleanup_old_summaries` (rotator) and
  `precompact._archive_summary` (writer) resolve through it — drift would
  silently break the rotation invariant.
- `_grounding._same_or_nested_project` uses `Path.relative_to`, so worktree
  sessions nested under the recorded project root keep their shared
  objective injection. Equality-only checks silently miss that case.
