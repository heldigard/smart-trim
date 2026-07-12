# Project: smart-trim

`smart-trim` — LLM-powered PreCompact context-compression hook for Claude Code
(and Gemini/Antigravity via symlink). Graduated from the monolithic
`~/.claude/hooks/smart-trim.py` (1114L) into its own vertical-slice package,
mirroring the `codeq` project layout.

## Architecture: vertical-slice hook package (NOT a CLI)

smart-trim is a **PreCompact hook**, not a CLI. Entry point is
`~/.claude/hooks/smart-trim.py` — a ~20-line **shim** that does only:
`from smart_trim.features.precompact.command import main; main()`. The hook is
wired in `~/.claude/settings.json` (`python3 ~/.claude/hooks/smart-trim.py`) and
reached by Gemini via a symlink (`~/.gemini/hooks/smart-trim.py`). The shim
preserves that wired path so neither settings.json nor the symlink moves.

## Layout

```
src/smart_trim/
  shared/        config, paths, ollama, timeutil, compat (infra; no feature deps)
  features/
    session/     discover Claude session + extract conversation context
    summarize/   LLM cascade (ollama primary/secondary -> cloud tertiary)
    fallback/    deterministic rule-based handoff (always succeeds)
    grounding/   read currentTask/progress/activeContext/objective (read-side)
    writer/      persist handoff to .memory-bank + topic index (write-side)
    hygiene/     rotate/audit archived summaries
    precompact/  orchestrator handle_precompact + main entry
```

## Conventions

- **One responsibility per feature folder** (cohesion > size). 250L per module
  is the meta, not a hard cap; `vs-soft-allow` for cohesive pipelines
  (handle_precompact is one end-to-end pipeline).
- `handle_precompact` uses **late binding by module** for the functions the
  tests monkeypatch (`from smart_trim.features import summarize as _sum`;
  `_sum.summarize_primary(...)`) so `monkeypatch.setattr` on the origin module
  resolves at call time.
- Cross-feature imports go through `shared/`, never feature→feature (except
  precompact orchestrating all of them).

## Critical constraints (regression risks)

1. **`shared/compat.py`** owns the `sys.path` inserts + `try/except` imports of
   `ollama_client`, `cheap_complete`, `context_guard_lib.reset_state` (all in
   `~/.claude/scripts/`). Without `Path(__file__).resolve()` (Gemini arrives via
   symlink) these silently fail → rule-based fallback only. compat is imported
   by `smart_trim/__init__.py` so it runs exactly once on package import.
2. **Agent-memory freshness filtering** comes from the optional installed
   `agent_memory.features.entries.command` module. Never restore a file-path
   import from `~/.claude/scripts/`; missing agent-memory must degrade to raw
   memory-bank lines — see `features/grounding/command.py`.
3. **Output is byte-identical** to the v3.2 monolith for the same input — the
   split is pure reorganization. `handle_precompact` returns the same dict,
   writes the same `activeContext.md` and `~/.claude/summaries/` artifacts.

## Commands

- Install (dev): `pip install -e ~/agent-memory && pip install -e ~/smart-trim`
- Test: `python3 -m pytest tests/ -q`
- Layout gate: `python3 -m pytest tests/test_layout.py -q` (250L meta per module)
- Lint: `ruff check src/ tests/`
- Smoke the hook: `echo '{"trigger":"manual","sessionId":"smoke","cwd":"'"$PWD"'"}' | python3 ~/.claude/hooks/smart-trim.py`

## Workflow

- New behavior → failing test in `tests/test_<slice>.py` first, then implement.
- Before editing a symbol → `codeq refs <name>` (call sites).
- After changes → `pytest tests/ -q` + `ruff check .`.
- Register durable decisions in `.memory-bank/systemPatterns.md`.

## Things that look wrong but aren't

- `compat.py` does `sys.path.insert` at import time — intentional, so the
  `~/.claude/scripts/` helpers resolve from any CWD the hook runs under.
- `precompact/command.py` imports sibling feature modules instead of their
  functions — deliberate late binding so monkeypatch in tests works.
- No `[project.scripts]` in pyproject — it's a hook, not a CLI.
