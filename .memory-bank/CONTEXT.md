# Context

- Vertical-slice architecture mirrors `~/codeq/` (`features/<feat>/command.py` +
  `shared/`). One responsibility per feature folder.
- `handle_precompact` (orchestrator) uses **late binding by module** so the
  pytest monkeypatches on origin modules resolve at call time. Do not collapse
  those to direct function imports or tests break.
- `shared/compat.py` is imported once via `smart_trim/__init__.py`; it owns the
  `sys.path` inserts for `~/.claude/scripts/` and the graceful `try/except`
  imports of `ollama_client` / `cheap_complete` / `context_guard_lib`.
- `_load_project_memory` resolves the helper at the absolute path
  `~/.claude/scripts/project-memory.py` (the v3.2 `__file__`-relative path
  broke after the split).
