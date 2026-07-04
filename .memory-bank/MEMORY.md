# Memory

- smart-trim graduated from monolith `~/.claude/hooks/smart-trim.py` (1114L, v3.2)
  to vertical-slice package v3.3.0 on 2026-07-03. Backup at
  `smart-trim.py.pre-split.bak` (root of this repo).
- The hook is a PreCompact event handler, NOT a CLI. Entry = thin shim at
  `~/.claude/hooks/smart-trim.py` → `smart_trim.features.precompact.command:main`.
- Output must stay byte-identical to v3.2 for the same input — the split is pure
  reorganization. Any behavior change belongs in a separate commit + version bump.
