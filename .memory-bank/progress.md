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
- `_load_project_memory`: `__file__`-relative path → ABSOLUTE `~/.claude/scripts/project-memory.py` (the relative path broke after `__file__` moved into the package).
- `post_json` helper: dropped (dead code — defined in v3.2 but never called; summarize uses ollama_client.chat / cheap_complete).
- `cleanup_old_summaries` / `check_memory_hygiene`: added injectable `summary_dir` param for testability without global Path.home monkeypatch.
- `compat.py`: sys.path inserts now use ABSOLUTE `~/.claude/{scripts,hooks}` (the `__file__`-relative inserts would have pointed at the wrong dirs from inside the package).
- 2026-07-04T01:09:12Z | status:completed | session:f089faa9-d9d2-4541-885e-a672096d9aab | claude: session done
- 2026-07-04T01:17:30Z | status:completed | session:7092ed22-555a-434f-8c1c-3205cfebe549 | gemini: reviewed project, achieved 100% test coverage across all features/shared modules, fixed lint/format warnings, implemented dictionary tool_result serialization, added env var overrides for models/context caps, and verified layout gate compliance.
- 2026-07-05T02:30:00Z | status:completed | audit: fixed 4 real bugs + DRY refactor — README model-order inverted (now matches code), `_same_or_nested_project` only checked equality (now uses `relative_to` so worktree subdirs match), `_try_local` hardcoded labels decoupled from env-overridden models (new `summarize.primary_label/secondary_label` derive from `_PRIMARY_MODEL/_SECONDARY_MODEL`, strip quantization suffixes), `_archive_summary` and `hygiene._default_summary_dir` duplicated the archive path (now shared via `paths.default_summaries_dir()`). Logging: stderr `print` → `logging.getLogger`. Tests: 148 → 160 (label derivation × 4, nested project × 3, shared dir × 1). Hook smoke + layout gate + ruff all green.

- 2026-07-05T20:00:48Z | 2026-07-05: Updated canonical harness-shim/smart-trim.py to bootstrap ~/smart-trim/src by shim location/env override so isolated-HOME workers keep real PreCompact behavior; pytest+ruff passed.
- 2026-07-06T22:58:02Z | status:completed | 2026-07-06: Fixed automatic memory-bank noise in PreCompact flow. smart-trim now writes only the handoff summary to project memory and no longer persists transient POST-COMPACT RULES into activeContext/session-handoffs.
- 2026-07-08T00:49:42Z | status:completed | Memory hygiene: removed compact-session prompt rules and corrupted handoff fragments from activeContext; retained only durable smart-trim facts.
