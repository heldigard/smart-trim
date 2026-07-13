# Progress

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
