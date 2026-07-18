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
to foreign-session storage or silently failed. `_final_message` moved
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

## 2026-07-14 — Redaction precision + cascade wall-clock budget

**Decision 1 (redaction)**: split `SECRET_RE` into `SECRET_VALUE_RE`
(high-confidence values: prefixed tokens, PEM, JWT — masked at the matched
SPAN) and `SECRET_KEYWORD_RE` (loose labels api_key/password/secret/... —
masked keyword→END-OF-LINE). `redact_sensitive` masks spans instead of whole
lines.

**Why**: the old whole-line redaction deleted any LLM handoff line that merely
mentioned "secret"/"password"/"api_key" as a word — real decisions like "rotate
the api_key weekly" vanished. Span/value masking keeps the decision context
("Rotate ") while never leaking a value. Keyword→EOL is the conservative choice
that still catches prose-form secrets ("the secret is hunter2").

**Invariant**: redaction MUST stay idempotent under double-application
(handle_precompact redacts, then writer redacts again on the same text). The
keyword-tier placeholder wording is chosen to contain NO trigger keyword — a
second pass is a no-op. Enforced by `test_redact_is_idempotent_under_double_application`.

**Decision 2 (budget)**: the LLM cascade is bounded by ONE wall-clock budget
(`SMART_TRIM_CASCADE_BUDGET_SECONDS`, default 40; floor `CASCADE_MIN_TIER_SECONDS`=3).
`_tier_timeout(deadline, share)` clamps each tier's per-call timeout to the
remaining budget (primary share=0.6 so secondary still gets a turn; secondary
and cloud share=1.0), under `OLLAMA_TIMEOUT_SECONDS`.

**Why**: the cascade runs BEFORE any write, so a hung model exceeding the
PreCompact hook timeout lost the ENTIRE handoff. Worst case was primary(45s)+
secondary(45s)+cloud(45s)=135s. The budget fails OPEN to rule-based fallback
instead. Healthy gens (primary ~6s) finish well under their 60%-share cap, so
the common path is unaffected; only true hangs hit the cap.

**Rejected**: parallelizing primary+secondary — GPU serializes local gens, so
it wastes GPU on the success path and doesn't fix a single hung model. The
budget is the correct bound.

**Rejected**: splitting the cascade tiers out of `precompact/command.py` (now
284L) into `precompact/cascade.py` — the budget logic is cascade orchestration,
not a separable responsibility, and splitting would fracture the late-binding
monkeypatch contract. Used the layout ALLOWLIST instead (review if > ~320L).
- 2026-07-15T01:34:50Z | Decision: a present project objective registry is authoritative, including invalid/terminal states; do not fall back to global state and risk cross-project contamination.
- 2026-07-15 | Decision: summarize num_ctx raised 32768→65536 (env `SMART_TRIM_NUM_CTX`). gemma4-e2b supports 128K natively and weighs 3.4GB Q4; RTX 5080 16GB holds ~7GB at 64K ctx (model+KV). 32K left 75% of the native window unused → long sessions truncated (done_reason=length). PRIMARY stays `batiai/gemma4-e2b:q4` (ollama-bench smart_trim #1, 11.81); `gemma4-12b` (256K native, 7.4GB, score 11.35) NOT promoted — lower score + slower, and e2b's 128K already covers needs at half the VRAM. Cascade (e2b→cryptidbleh→deepseek-cloud) confirmed optimal vs RANKING.md.
- 2026-07-15 | Decision: activeContext truncation is item-aware, not blob-slice. `compact_items` (writer/active.py) dedups + fills the budget with WHOLE items (` | `-joined) + a `(+N omitted)` tag that displaces whole items, never fragments one; a single oversized item delegates to `compact_value` (evidence for Errors/Files, tail-truncate `…` + word-boundary for prose). Replaced the `…[recortado]…` mid-line marker — root cause of the Codex incident (marker glued mid-line + head/tail semantic overlap, e.g. `permissions, o …[recortado]… permissions`). Full handoff detail remains in the archived session-handoffs topic; activeContext is the bounded teaser. active.py ALLOWLISTed at 309L (cohesive single-responsibility renderer).
- 2026-07-17T15:51:29Z | status:completed | PreCompact topic persistence uses a bounded non-blocking POSIX lock with a portability fallback: brief concurrent bursts may wait up to 250 ms, but a busy/suspended writer causes the optional handoff write to skip instead of hanging compaction. Ollama overrides are plain-HTTP loopback only.
