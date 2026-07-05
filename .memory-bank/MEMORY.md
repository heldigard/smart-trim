# Memory

- smart-trim graduated from monolith `~/.claude/hooks/smart-trim.py` (1114L, v3.2)
  to vertical-slice package v3.3.0 on 2026-07-03. Backup at
  `smart-trim.py.pre-split.bak` (root of this repo).
- The hook is a PreCompact event handler, NOT a CLI. Entry = thin shim at
  `~/.claude/hooks/smart-trim.py` → `smart_trim.features.precompact.command:main`.
- 2026-07-05 audit: 4 real bugs + DRY refactor landed (label derivation,
  nested-project match, shared archive dir, hygiene logging). The
  byte-identical-to-v3.2 contract no longer holds for the persisted
  `method` label — the audit intentionally made it env-aware. Behavior
  change lives in this commit; no version bump (no user-visible API change).
