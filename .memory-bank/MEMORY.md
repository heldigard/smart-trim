# Memory

- smart-trim graduated from monolith `~/.claude/hooks/smart-trim.py` (1114L, v3.2)
  to vertical-slice package v3.3.0 on 2026-07-03. Backup at
  `smart-trim.py.pre-split.bak` (root of this repo).
- The primary runtime is a PreCompact event handler. Entry = thin shim at
  `~/.claude/hooks/smart-trim.py` → `smart_trim.features.precompact.command:main`;
  the installed console surface is limited to diagnostics/smoke plus
  hook-compatible stdin.
- 2026-07-05 audit: 4 real bugs + DRY refactor landed (label derivation,
  nested-project match, shared archive dir, hygiene logging). The
  byte-identical-to-v3.2 contract no longer holds for the persisted
  `method` label — the audit intentionally made it env-aware. Behavior
  change lives in this commit; no version bump (no user-visible API change).
- 2026-07-15 audit: session parsing and the local LLM tier fail open across
  malformed-but-valid JSON and helper exceptions; `smart-trim smoke` is isolated
  from live sessions/objectives and must not mutate real project handoffs.
