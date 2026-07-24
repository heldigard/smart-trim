# Progress

## 2026-07-18 — v3.4.1: doctor depth + module entry (SHIPPED)

Native-Ubuntu follow-up after v3.4.0.
- `doctor` now probes cascade helpers (`ollama_client`, `cheap_complete`, `cg_reset`),
  PreCompact shim presence, prints the active Python interpreter, and supports
  `--json` via `collect_checks()` for machine-readable health.
- `python -m smart_trim` entry (`__main__.py`) matches the console script surface.
- Clearer agent-memory WARN when the isolated `uv tool` env lacks the package while
  the live hook (system python3 + shim) still has freshness filtering.
- Ops: reinstalled `uv tool` with `--with-editable ~/agent-memory`; project venv
  also has agent-memory editable.
- Gate: full pytest green, ruff check/format, mypy clean; diagnostics ~240L under meta.


## 2026-07-18 — v3.4.0: `doctor` subcommand + coverage hardening (SHIPPED)

Native-Ubuntu improvement pass. No hook-behavior change; additive only.
- NEW `features/diagnostics/command.py` → `smart-trim doctor`: probes Ollama
  `/api/tags` (stdlib `urllib`, 0 deps), checks primary/secondary models
  installed, agent-memory importable, memory-bank + archive writable, cascade
  budget sane. FAIL only on core-function breakage (memory-bank unwritable,
  self-defeating budget); Ollama/model/agent-memory gaps = WARN (cascade still
  hands off via cloud/fallback). Wired via `capabilities.handle_cli` (lazy
  import → off the hook path). `smoke` only proves offline fallback; `doctor`
  verifies the LLM tier is wired.
- Coverage closed on safety-critical code: `shared/filelock.py` 72%→100%
  (retry/timeout/OSError/unlock-error/fcntl-absent), `shared/config.py`
  95%→100% (loopback + positive_float/int edge cases).
- `summarize`: added `primary_model()`/`secondary_model()` accessors (DRY for
  doctor; avoids duplicating env defaults).
- Version 3.3.0→3.4.0; version test now asserts against `__version__` (future-
  proof). README got a Diagnostics section.
- Gate: ruff + format + mypy clean; 304 pytest pass; coverage 98.39% (≥95 gate).

## 2026-07-03 — vertical-slice split SHIPPED (v3.2 monolith → v3.3.0 package)

8 commits (F0-F7). All verification green:
- 103 pytest tests (7 feature modules + shared + layout gate)
- 250L layout gate, ALLOWLIST empty (every module complies; largest: precompact 224L)
- behavior diff monolith.bak vs shim: byte-IDENTICAL activeContext.md
- ruff lint clean, ruff format clean (33 files)
- hook smoke: manual/auto/garbage/empty stdin, Gemini symlink
- `pip install -e ~/smart-trim` registered; import sanity from /tmp

Layout shipped:
```
src/smart_trim/
  shared/   config(39) compat(55) paths(80) ollama(33) timeutil(39)
  features/ session/{command(165),content(111)} summarize(137) fallback(104)
            grounding(196) writer(123) hygiene(98) precompact(224)
tests/      8 files, 103 tests
```
Monolith backup: `smart-trim.py.pre-split.bak` (1114L) at repo root.
Hook shim: `~/.claude/hooks/smart-trim.py` (21L) → `smart_trim.features.precompact.command:main`.

### Correcciones aplicadas durante el split (not pure moves)
- Freshness filtering originally moved from a relative legacy-helper lookup to
  an absolute path; that interim adapter was later retired for the installed
  agent-memory package API.
- `post_json` helper: dropped (dead code — defined in v3.2 but never called; summarize uses ollama_client.chat / cheap_complete).
- `cleanup_old_summaries` / `check_memory_hygiene`: added injectable `summary_dir` param for testability without global Path.home monkeypatch.
- `compat.py`: sys.path inserts now use ABSOLUTE `~/.claude/{scripts,hooks}` (the `__file__`-relative inserts would have pointed at the wrong dirs from inside the package).
- 2026-07-04T01:09:12Z | status:completed | session:f089faa9-d9d2-4541-885e-a672096d9aab | claude: session done
- 2026-07-04T01:17:30Z | status:completed | session:7092ed22-555a-434f-8c1c-3205cfebe549 | gemini: reviewed project, achieved 100% test coverage across all features/shared modules, fixed lint/format warnings, implemented dictionary tool_result serialization, added env var overrides for models/context caps, and verified layout gate compliance.
- 2026-07-05T02:30:00Z | status:completed | audit: fixed 4 real bugs + DRY refactor — README model-order inverted (now matches code), `_same_or_nested_project` only checked equality (now uses `relative_to` so worktree subdirs match), `_try_local` hardcoded labels decoupled from env-overridden models (new `summarize.primary_label/secondary_label` derive from `_PRIMARY_MODEL/_SECONDARY_MODEL`, strip quantization suffixes), `_archive_summary` and `hygiene._default_summary_dir` duplicated the archive path (now shared via `paths.default_summaries_dir()`). Logging: stderr `print` → `logging.getLogger`. Tests: 148 → 160 (label derivation × 4, nested project × 3, shared dir × 1). Hook smoke + layout gate + ruff all green.

- 2026-07-05T20:00:48Z | 2026-07-05: Updated canonical harness-shim/smart-trim.py to bootstrap ~/smart-trim/src by shim location/env override so isolated-HOME workers keep real PreCompact behavior; pytest+ruff passed.
- 2026-07-06T22:58:02Z | status:completed | 2026-07-06: Fixed automatic memory-bank noise in PreCompact flow. smart-trim now writes only the handoff summary to agent memory and no longer persists transient POST-COMPACT RULES into activeContext/session-handoffs.
- 2026-07-08T00:49:42Z | status:completed | Memory hygiene: removed compact-session prompt rules and corrupted handoff fragments from activeContext; retained only durable smart-trim facts.
- 2026-07-08T01:39:57Z | 2026-07-08: Reviewed after ollama-bench scorer refactor. New smart_trim benchmark top is fredrezones55/Qwopus3.5 with functiongemma close fallback; runtime still uses shared ollama_client.chat, which strips recoverable reasoning traces. summarize/shared tests passed during verification.
- 2026-07-08T02:08:13Z | status:completed | 2026-07-08: Reconfigured summarization cascade to smart_trim bench winners: fredrezones55/Qwopus3.5:9b primary and functiongemma secondary. Tests/docs updated. qwen3.5 remains only a generic compatibility model elsewhere, not the smart-trim secondary.
- 2026-07-09T21:32:46Z | status:completed | 2026-07-09: Rewired local compaction from semantic risk-weighted evidence: batiai/gemma4-e2b:q4 PRIMARY, cryptidbleh/gemma4-claude-opus-4.6 SECONDARY; preserved security constraints and partial verification in the bench.
- 2026-07-10T18:43:33Z | status:completed | 2026-07-10: Closure audit complete. PreCompact version entrypoint and regression coverage pass full pytest/Ruff; no active implementation guide remains.
- 2026-07-10T22:10:00Z | status:completed | PreCompact handoffs now spend at most 384 local generation tokens and persist through a fixed-label renderer split into `writer/active.py`. Active context stays within 1,200 chars/28 lines, prioritizes Constraints/Task/Acceptance/Verified/Errors/Next, preserves middle error IDs/paths, names deferred fields, and points to the deep topic. Session/LLM text is redacted and marked quoted/non-authoritative before archive/topic/foreign/active sinks; active writes use fsync + atomic replace after the recovery topic exists. Full pytest, layout, Ruff, Mypy, and codescan passed.
- 2026-07-11T18:51:20Z | status:completed | Guard fail-open en precompact main() (bug de summarization nunca bloquea compaction, error a stderr); repo reformateado ruff 0.15 y CI con ruff format --check. Commits c7f6a3d, a13a863. Nota: smart-trim.py.pre-split.bak sigue en root (gitignored, backup local intencional)
- 2026-07-11T19:00:22Z | status:completed | Ronda 2: read_session acotado a cola de 4MiB del JSONL (SMART_TRIM_SESSION_TAIL_BYTES, 0=full), get_context_usage eliminado (sin callers). Commit d712643. Smoke e2e del shim OK
- 2026-07-12T12:33:13Z | status:completed | Autonomous reliability/security audit hardened PreCompact recovery edges: session-file lookup rejects path-like IDs and tolerates unreadable project entries; archives sanitize external IDs and cannot collide during rapid compacts; context caps include separators; fallback paths preserve first-seen order; optional grounding-helper failures and unreadable archive metadata remain fail-open. Verification: 172 pytest tests, Ruff check/format, Pyright, Semgrep, Gitleaks, Vulture, layout gate, and shim stdin smokes all green.
- 2026-07-12T12:34:54Z | status:completed | session:gen:a77b836c-5cff-4b17-b268-8e29396eb6bc | codex: session done
- 2026-07-12T12:44:15Z | status:completed | Migrated smart-trim from the retired memory-helper name to agent-memory: grounding now imports the optional agent_memory freshness API, writer/orchestrator symbols and documentation use agent-memory, legacy loader tests were removed, and full pytest/Ruff/Pyright/security validation passed.
- 2026-07-12T23:15:00Z | status:completed | Added Codex PreCompact compatibility (`transcript_path`, `session_id`) and shared shim wiring. Synthetic minimal/no-transcript events with no live objective now preserve the prior activeContext instead of overwriting it; no archive/topic is created. Full 172 tests plus Ruff, Pyright, Semgrep, Gitleaks, Vulture clean. No commit/push.
- 2026-07-12T23:50:53Z | status:completed | 2026-07-12: added safe CLI discovery without entering hook mode: `smart-trim --help` and `smart-trim capabilities --json` expose PreCompact writes, cost, open-world fallback, and degradation chain. Hook stdin/version behavior preserved. Suite 174 tests; Ruff/Mypy/Pyright/Semgrep/Gitleaks/Vulture clean.
- 2026-07-13T00:26:54Z | 2026-07-12: Ajustes finales de features de capacidades/precompact/sessión + cobertura y limpieza de ruido menor antes de commit/push del paquete.
- 2026-07-13T13:51:04Z | status:completed | 2026-07-13 meta-bank contamination fixed: smart-trim _is_foreign_session gained HOME-meta guard + ~/$HOME path expansion + known-project-name detection. Root cause = elogix Codex session ran from home, handoff named project without abs paths, overwrote meta activeContext. 4 regression tests, full suite green, pushed smart-trim d489c0e. agent-memory project_root() still has the same HOME-catch-all (lower priority — smart-trim was the active writer); optional follow-up.
- 2026-07-14T00:04:50Z | status:completed | session:f6e15eb3-92cf-43da-96b2-26f50e91c18b | gemini: session done

## 2026-07-14 — audit round: truthful routes + env-aware endpoints

- 215 pytest green (+17 new), ruff lint+format clean.
- Live smoke: foreign route and active route both verified end-to-end with real
  Ollama primary (ollama-gemma4-e2b) via the Claude shim.
- Codex shim now symlinks the Claude shim (single source of truth).

## 2026-07-14 — redaction precision + cascade wall-clock budget

- `redact_sensitive` now two-tier: high-confidence VALUES (prefixed tokens,
  PEM, JWT) masked at span; loose KEYWORDS (api_key/password/secret/...)
  masked keyword→EOL. Old whole-line nuke lost LLM decisions that merely named
  a field ("rotate the api_key weekly"). Placeholder wording avoids every
  trigger keyword so the double-application (orchestrator + writer) stays
  idempotent. config.py: SECRET_RE → SECRET_VALUE_RE + SECRET_KEYWORD_RE.
- LLM cascade now bounded by one wall-clock budget (`SMART_TRIM_CASCADE_BUDGET_SECONDS`,
  default 40s; `CASCADE_MIN_TIER_SECONDS`=3 floor). `_tier_timeout` clamps each
  tier to the remaining share (primary 60%, secondary/cloud 100%) under
  OLLAMA_TIMEOUT_SECONDS. A hung model can no longer blow the PreCompact hook
  timeout and lose the ENTIRE handoff (cascade ran before any write); it fails
  OPEN to rule-based fallback. summarize_primary/secondary/cloud_cascade grew
  `timeout=` / `timeout_total=` params.
- precompact/command.py 284L → ALLOWLIST (cohesive end-to-end pipeline + budget
  orchestration; splitting would fracture the late-binding monkeypatch contract).
- 226 pytest green (+11: 5 redaction precision/idempotency, 6 budget),
  ruff lint+format clean. Two isolated e2e smokes via the live shim with real
  Ollama primary: active route wrote activeContext (Decisions line showed
  "Rotate " preserved + value masked), foreign route correct.
- 2026-07-15T01:34:50Z | status:completed | Objective grounding is project-local first; the legacy global objective is used only when the local registry is absent, never when a present local record is invalid or terminal. Regression coverage and full validation pass.
- 2026-07-15T02:28:08Z | status:completed | Second pass confines grounding reads to resolved targets under their project/state root and rejects oversized memory/objective files. Outside-project objective symlinks and over-64KB objectives now fail closed with regressions.

## 2026-07-14 — observability topic + smoke subcommand

- `features/observability/command.py` (165L, new): append-only JSON-line event
  log for PreCompact. Default OFF (`SMART_TRIM_OBSERVABILITY=1` to enable).
  Records `method`, `route`, `trigger`, `latency_ms`, `in`/`out` bytes,
  `model_chain` (every tier actually attempted, not just the winner), and a
  sha256[:12] session hash (48-bit fingerprint, not reversible). No prompt
  content, no paths, no error strings — only counters + structural metadata.
  Topic is `topics/compact-events.md`; auto-registered in `topics/_index.md`
  on first write. Failures are debug-only (the recorder must never block
  compaction, even when the topic disk is full).
- Orchestrator wiring: `_resolve_summary` now returns
  `(text, method, preserved, model_chain)`; `_try_local` and `_try_cloud`
  return `(text, method, attempted_chain)` so the recorder sees a hung
  primary even when secondary ultimately succeeded. `handle_precompact`
  records both the active and skipped paths with wall-clock latency from
  `time.monotonic()`. Existing tests updated to the new return shapes; no
  external API change (handle_precompact still returns the same dict).
- `capabilities command.py` gained the `smoke` subcommand. It spawns the
  wired shim (`~/.claude/hooks/smart-trim.py`) with a synthetic PreCompact
  payload and exits 0 on a valid hook contract, 2 on missing shim, 3 on
  timeout, 5 on unparseable stdout. Tests intercept `subprocess.run` so
  CI runners without the shim path still pass.
- 248 pytest green (+22 new: 11 observability, 8 capabilities, 3 re-anchored
  precompact return-shape), ruff lint+format clean, layout gate clean.
  precompact/command.py 284L → 358L; ALLOWLIST comment updated to mention
  observability event recording. Live e2e via the Claude shim wrote one
  compact-events.md entry on a synthetic payload.

## 2026-07-15 — second review: observability + capabilities hardening

Second-pass review found 3 issues in the previous commit:

1. **Dead code**: `_DEFAULT_ENABLED = False` in observability/command.py was a
   leftover constant never referenced anywhere (the gate reads env at call
   time via `observability_enabled()`). Removed.

2. **Collision math wrong**: `session_hash` docstring claimed "0.3%" collision
   probability at 10k events — off by ~4 orders of magnitude. Correct birthday
   bound is N²/2^49 ≈ 1.8 × 10^-5 at N=10k. Fixed in docstring and module
   docstring.

3. **Non-int latency_ms crash risk**: `CompactEvent` fields are typed `int` but
   Python does not enforce at runtime. A caller passing `"500"` or `None`
   would crash `int()` inside `record_compact_event`. Outer `try/except` in
   `_record_event` masks it but logs noise at debug level. Added `_safe_int`
   defensive coercion (returns 0 on TypeError/ValueError) + 2 new tests
   (`test_safe_int_coerces_string_numeric`, `test_safe_int_falls_back_on_nonsense`).

Total: 260 pytest green (+2: _safe_int coercion tests), ruff lint+format
clean, layout gate clean.

## 2026-07-15 — fail-open, CI, and harness integration audit

- Session ingestion now drops valid JSON scalars/lists instead of letting them
  reach dict-only extraction, treats negative tail-byte configuration as an
  error rather than an accidental unbounded read, tolerates non-string text
  blocks, and ignores one unreadable JSONL while selecting the newest readable
  session.
- Unexpected local Ollama client exceptions now fall through to the remaining
  cloud/rule-based tiers. Observability integer coercion is Mypy-clean and
  absorbs non-finite floats without violating its best-effort contract.
- CI now exercises Python 3.11, 3.12, and 3.13 and enforces at least 95% source
  coverage. Project docs now describe the diagnostic console entry and no
  longer claim byte identity with the v3.2 monolith.
- Harness drift corrected: Codex base reasoning matches the documented Sol
  `medium` default, and the live Claude shim is a symlink to the tracked
  template; Codex and Gemini continue to chain through that same path.
- The `smoke` subcommand now clears live Claude session variables and runs
  against a temporary bank with a terminal local objective, preventing the
  global objective fallback from overwriting real handoffs. A live smoke was
  verified by before/after checksums of both active and deep handoff files.
- Final validation: 256 tests collected, 98.69% coverage, Ruff lint/format,
  Mypy, Pyright, Semgrep, Gitleaks, Vulture, diff/YAML checks, wheel build, and
  live Claude/Codex shim smokes all green.
- 2026-07-15T16:22:33Z | status:completed | 2026-07-15 cross-CLI integration validated: smart-trim remains the single PreCompact continuity layer for Claude and the protocol-compatible Codex/Gemini path used by Antigravity; objective-aware handoff behavior is preserved while UserPromptSubmit composition and coordination stay in cli-orchestration. Full project gates plus graduated Claude/Codex shim E2E and global hook resolution pass.

## 2026-07-15 — handoff truncation + context/model tuning (2-pass review)

Codex incident: `.memory-bank/activeContext.md` shipped with literal `…[recortado]…`
markers glued mid-line + head/tail semantic overlap. Two review passes:
- **writer/active.py**: `compact_value` else-branch was head+tail (overlap) →
  tail-truncate with `…` + word-boundary. New `compact_items` (item-aware):
  dedup + whole items joined ` | ` + `(+N omitted)` tag that displaces whole
  items (never fragments one). Bug caught in review: the tag's `out[:room]`
  sliced the last item mid-token → rewritten to pop whole items. active.py
  ALLOWLISTed (309L, cohesive renderer).
- **summarize + shared/config (context)**: `num_ctx` was 32768 but gemma4-e2b
  is 128K-native/3.4GB → raised to 65536 (env `SMART_TRIM_NUM_CTX`, fail-open
  parse). Second review found the REAL bottleneck: `extract_context_for_summary`
  capped input at `MAX_CONTEXT_FOR_SUMMARY=20000` chars before the model, so the
  bigger num_ctx was moot — raised to 50000 (env `SMART_TRIM_MAX_CONTEXT_LOCAL`).
  ollama-bench RANKING.md confirms cascade (e2b #1 11.81 → cryptidbleh #2 → cloud)
  already optimal; gemma4-12b NOT promoted (lower score, slower, 256K window
  unneeded). ollama-client reviewed: num_ctx propagation verified, 122 tests +
  ruff green, API frozen.
- Validation: full suite green (261+ tests), ruff clean, e2e smoke shows clean
  teaser (whole paths, no `[recortado]`) + topic keeps the full set. Hook
  re-fired in runtime and produced `(+N omitted)` output — fix live.

## 2026-07-15 — third review: tag-overflow truncation-flag loss

Third adversarial pass on `compact_items` caught a subtle flag bug: the
`(+N omitted)` tag's `while kept` loop could empty `kept` entirely when one
whole item fit but the tag did not, falling back to `compact_value(unique[0])`
which returns `truncated=False` — silently dropping the omission signal and the
count. Fix: stop popping at `len(kept) >= 2`, so a single fitting item is kept
whole (without a tag when one won't fit) and `truncated` stays True. Regression
test `test_compact_items_keeps_whole_item_and_flag_when_tag_does_not_fit`.
Suite green, ruff clean.

## 2026-07-15 — fourth review: fuzz-found len<=limit contract breach

Adversarial fuzz (60k cases) of `compact_items` + `compact_value` found that
`_truncate_at_tail` always appended the ` …` elision (2 chars) even when that
pushed `len(result) > limit` for tiny limits (limit 1-3). Never triggered in
production (`_FIELD_LIMITS` are all >= 100) but it broke the hard contract
`len(result) <= limit`, which `render_active_fields` relies on to avoid its
`ValueError` that would lose the whole handoff. Fix: `budget <= 0` hard-
truncates to the limit, and a trailing `[:limit]` safety net. Added
`test_compact_respects_len_limit_for_tiny_limits` (limits 1-11). Re-fuzz:
0 violations across 60k cases. Fuzz false positives (substring-count dedup
check) identified and discarded.

## 2026-07-15 — ecosystem ollama context audit + ollama-summarize fix

Audited every ollama consumer for the smart-trim context bug (input cap
disconnected from num_ctx + silent truncation). Findings:
- **smart-trim**: was the only outlier — now fixed (cap+num_ctx aligned).
- **pdf-extract-structured / diff-review / extract-tool-output**: already follow
  the correct pattern (input cap + num_ctx scaled/aligned + truncation marked).
  pdf-extract even documents the anti-pattern smart-trim had.
- **codeq**: BODY_BUDGET 2.5KB cap is intentional + marked (`[NOTE: BODY
  TRUNCATED]`) for a 4B model on one-function context. Sane.
- **prompt-improve**: no input cap (prompt is small by nature) + explicit
  num_ctx 8K/16K. Sane.
- **ollama-summarize.py**: `--context-size 12K` cap but called `generate()`
  WITHOUT num_ctx → depended on the model's Modelfile default (fragile). Fixed:
  pass `num_ctx=8192` aligned to the 12K-char cap (~4K tokens). Single script,
  low risk.
- **cheap-llm**: NOT touched — graduated/frozen helper, 7 consumers; its design
  is to delegate context to the caller. Forcing num_ctx would change behavior
  for all consumers. Documented, left intact.
- compact_value evidence-retention: a planned improvement turned out unnecessary
  — `_evidence` already self-caps at `max(24, limit//2)`, so oversized evidence
  never reaches the head+tail path. Regression test added anyway
  (`test_compact_value_error_evidence_preserved_when_too_long_for_head_tail`).

## 2026-07-15 — ecosystem cap alignment (maximize model context, RTX 5080)

User directive: caps that degrade ollama-model quality must be raised to the
model's native window + VRAM ceiling, not left at arbitrary low defaults.
Audited every consumer and raised the sub-optimal caps (each verified within
its project's tests):

| Project | Cap | Before → After | Rationale |
|---|---|---|---|
| codeq `shared/llm.py` | BODY_BUDGET | 2500 → 6000 | real model is 9B (TeichAI/Qwen3.5-9B-Fable), not "4B" (stale comment fixed); 6KB fits num_ctx 8192 |
| diff-review.py | MAX_DIFF_FOR_LLM | 26000 → 60000 | ~18K tokens, within num_ctx 32768; large diffs reviewed whole |
| ollama-summarize.py | --context-size | 12000 → 40000 | cryptidbleh 128K-native/3.4GB; + num_ctx 8192→16384 |
| ollama-summarize.py | num_ctx | 8192 → 16384 | aligned to 40K-char cap (~12K tokens) |
| web-research `config.py` | WEB_SYNTH_MAX_CONTEXT_CHARS | 14000 → 40000 | feeds synth LLM (web_synth 9B 128K-native) |
| web-research research | --max-chars | 4000 → 12000 | per-result extraction to fill the wider synth budget |

Untouched (correct already or frozen): pdf-extract-structured (60K, num_ctx
scaled), extract-tool-output (60K, head+tail+matches), prompt-improve
(small-input, explicit num_ctx), cheap-llm (graduated/frozen helper, 7
consumers — delegates context by design). Found pre-existing debt:
web-research `build_parser` 99L (vertical-slice guard) — not introduced by
these literal edits; left for the web-research project to address.
- 2026-07-17T15:51:29Z | status:completed | Hardened numeric/Ollama configuration and concurrent memory writes; restored the 250-line layout gate and verified the complete pytest, Ruff, formatting, hook, security, and secret-scan gates.
- 2026-07-17T16:20:20Z | status:completed | 2026-07-17 completion pass: generalized local endpoint validation to all literal loopback IPs, reduced global always-on rules to 10,797/12,000 tokens, pinned active MCP packages, anchored stable uv/uvx paths, and disabled Antigravity non-workspace access. Full suites, cross-CLI authority/hooks/shims/model/RTK audits and codescan all are clean.
- 2026-07-24T01:51:44Z | status:completed | Doctor now validates AST-level shim delegation plus sanitized Claude/Codex PreCompact commands and timeout headroom; live wiring is green, with 327 tests and 97.4% coverage.
