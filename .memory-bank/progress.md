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
