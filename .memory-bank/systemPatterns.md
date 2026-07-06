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

## 2026-07-05 — Audit fixes (4 real bugs + DRY)

**Decision**:
1. Persisted method labels are now DERIVED from the active model tag (`summarize.primary_label/secondary_label`), not hardcoded — quantization suffixes (`_Q4_64k_8GB-GPU`, `_Q4_K_M`, etc.) are stripped so VRAM hints don't leak into `activeContext.md`.
2. `_same_or_nested_project` switched from `recorded == current` to `current.relative_to(recorded)`, so worktree sessions (cwd nested in the recorded project root) keep their shared objective injection instead of being silently mis-classified as foreign.
3. Archive directory consolidated: `shared.paths.default_summaries_dir()` is the single source of truth; both `hygiene.cleanup_old_summaries` and `precompact._archive_summary` resolve through it.
4. `hygiene` switched from `print(..., file=sys.stderr)` to `logging.getLogger("smart_trim.hygiene")` (named logger; still best-effort / never-block, but routed through the standard logging framework).

**Why**:
Audit caught: README + `_try_local` disagreed with the actual model order; the env override for the primary/secondary model persisted a STALE label into `activeContext.md` (the bug); the nested-project guard silently dropped worktree sessions; two features held independent copies of the same path (drift risk); and stderr noise bypassed the harness logging conventions.

**Risks mitigated**:
- Label derivation: tests no longer hard-code the literal method strings; assertions now compare against `primary_label()/secondary_label()`. A future model swap (different default tag) propagates automatically.
- Nested match: the test suite now covers all three cases (equal, nested, sibling).

- 2026-07-06T22:58:02Z | status:active | Memory hygiene: runtime instructions from compaction hooks and worker wrappers are not durable project memory. Filter FUSION_PANEL/CODEX_WORKER/NO_DELEGATE/NO_TOOLS/NO_SWARM markers and generic post-compact 'DO NOT re-read...' guidance from negative constraint extraction; preserve real user/project constraints such as 'Never read .env files.'
