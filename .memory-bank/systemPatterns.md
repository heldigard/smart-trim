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
3. Grounding uses the installed agent-memory package for freshness filtering;
   it never loads memory helpers by absolute script path.

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

- 2026-07-06T22:58:02Z | status:active | Memory hygiene: runtime instructions from compaction hooks and worker wrappers are not durable agent memory. Filter FUSION_PANEL/CODEX_WORKER/NO_DELEGATE/NO_TOOLS/NO_SWARM markers and generic post-compact 'DO NOT re-read...' guidance from negative constraint extraction; preserve real user/project constraints such as 'Never read .env files.'

## 2026-07-12 — Recovery-boundary hardening

**Decision**: Treat hook payload metadata and optional harness/filesystem state as
untrusted recovery inputs. Session IDs used for lookup are strictly validated
before filename construction; archive labels are separately sanitized and
uniquified. Per-entry filesystem/helper failures degrade locally instead of
escaping to the top-level no-op fallback.

**Why**: PreCompact must fail open without unnecessarily losing the handoff. A
malformed session ID could previously escape the archive directory or session
store, while one unreadable project/archive entry or a broken optional helper
could cancel otherwise recoverable work.

**Invariant**: Bounds described by configuration are exact (including joining
separators), and deterministic fallback output preserves first occurrence order.
- 2026-07-13T13:51:04Z | status:live | Meta-bank isolation (2026-07-13): the HOME meta bank (~/.claude/memory-bank via /home/eldi/.memory-bank symlink) is a catch-all for sessions launched from ~. smart-trim _is_foreign_session now treats a HOME-rooted session as FOREIGN unless its summary carries a harness/meta signal (.claude, hooks/, skills/, graduated package names, memory-bank) — so project work run from home (by name, no absolute path) routes to the foreign-sessions topic, not activeContext. Rule: launch project sessions FROM the project dir (cd project && cli) so they resolve their own .memory-bank; home is meta-only. elogix has its own bank at /mnt/ext4disk/ProyectosP/Elogix/.memory-bank. Fix lives in ~/smart-trim (shared by Claude+Codex).

## 2026-07-14 — Route-aware hook message + env knobs

**Decision**: `writer.update_agent_memory` returns its persistence route
(`active`/`foreign`/`error`); `policy.final_message` renders it so the
PreCompact systemMessage never claims an activeContext update that was routed
to `topics/foreign-sessions.md` or silently failed. `_final_message` moved
from precompact/command.py to policy.py (250L gate + cohesion: policy owns
both hook return dicts).

**Env knobs added** (all default-preserving):
- `SMART_TRIM_OLLAMA_BASE` (or standard `OLLAMA_HOST`, bare host:port OK) —
  Ollama endpoint; invalid values fall back to localhost:11434.
- `SMART_TRIM_CLOUD_MODEL` — cloud tier model; label stays `deepseek-cloud`
  for the default, else derives `cloud-<bare-model>` (env-aware like local tiers).

**Security**: SECRET_RE extended with high-confidence token prefixes
(gh[pousr]_/github_pat_/glpat-/AKIA/xox[abprs]-/npm_/AIza/JWT eyJ..eyJ).

**Harness**: `~/.codex/hooks/smart-trim.py` was an unmanaged identical COPY of
the Claude shim (drift risk, no sync script covers it) — converted to symlink
like Gemini; backup at smart-trim.py.bak.
