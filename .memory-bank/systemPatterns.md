# System Patterns

## 2026-07-03 — Vertical-slice split (v3.2 monolith → v3.3.0 package)

**Decision**: extract smart-trim into its own repo `~/smart-trim/` (git +
.memory-bank + pyproject + `pip install -e`), mirroring `codeq`. Hook stays as a
~20-line shim at `~/.claude/hooks/smart-trim.py`.

**Why**: the monolith reached 1114L/42.6K across 9 sections (session, context
extraction, summarize cascade, fallback, grounding, writer, hygiene,
orchestrator, entry). Cohesion was degrading — one change to grounding forced
reading the whole file. codeq proved the `features/<feat>/command.py` + `shared/`
pattern scales; replicate it.

**Budget chosen**: hybrid — cohesion is the primary signal, 250L per module is
the meta (not hard). `vs-soft-allow` for cohesive pipelines (handle_precompact
is one end-to-end PreCompact pipeline).

**Risks mitigated**:
1. `shared/compat.py` centralizes the symlink-safe `sys.path` inserts +
   `try/except` imports — without it, Gemini (via symlink) silently degrades to
   rule-based fallback.
2. `handle_precompact` uses late binding (`_sum.summarize_primary()`) so pytest
   `monkeypatch.setattr` on origin modules works post-split.
3. `_load_project_memory` uses absolute `~/.claude/scripts/project-memory.py`
   (the `__file__`-relative path broke).

**Alternatives rejected**:
- Keep as hook-internal package under `~/.claude/hooks/smart_trim/` — less
  ceremony but no isolated git history / .memory-bank / versioning.
- Make it a CLI console script — wrong shape; it's a stdin-JSON hook.

## 2026-07-03 — Customization & Robustness Enhancements

**Decision**:
1. Support env overrides for primary/secondary local Ollama models (`SMART_TRIM_PRIMARY_MODEL`, `SMART_TRIM_SECONDARY_MODEL`).
2. Support env overrides for local/cloud context caps (`SMART_TRIM_MAX_CONTEXT_LOCAL`, `SMART_TRIM_MAX_CONTEXT_CLOUD`).
3. Serialize structured dictionary content inside `tool_result` blocks.

**Why**:
Users wanted customization to match their local GPU capacities (VRAM/context window size). Also, some tools return structured dictionary output in `tool_result`, which previously got skipped, causing information loss.

