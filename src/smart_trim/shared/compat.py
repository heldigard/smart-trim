"""Symlink-safe sys.path bootstrap + graceful imports of harness helpers.

The smart-trim hook is reached three ways:
  1. Claude Code:  ``python3 ~/.claude/hooks/smart-trim.py`` (the shim)
  2. Gemini:       ``~/.gemini/hooks/smart-trim.py`` -> symlink to the shim
  3. pytest:       ``import smart_trim`` (installed via ``pip install -e``)

The helpers ``ollama_client``, ``cheap_complete`` and
``context_guard_lib.reset_state`` live under ``~/.claude/{scripts,hooks}/`` and
are NOT on sys.path by default. The v3.2 monolith injected them with paths
relative to ``__file__`` — but after the split ``__file__`` moved into the
package, so those relative paths broke. Here we resolve the harness root
**absolutely** (``~/.claude``), which is correct for all three entry modes and
does not depend on where the source tree happens to live.

Importing this module has the side effect of extending ``sys.path`` exactly once
(it is imported by ``smart_trim/__init__.py``). Every consumer reads the
module-level names below and guards with ``is None`` checks so a missing helper
degrades gracefully to rule-based fallback rather than crashing the hook.
"""

# pyright: reportMissingImports=false
# The three harness helpers below live under ~/.claude/{scripts,hooks}/ and
# are added to sys.path at runtime by this module — Pyright cannot see them
# statically, so suppress the import-resolution diagnostics (they are
# intentionally optional, guarded by try/except).
from __future__ import annotations

import sys
from pathlib import Path

_CLAUDE_ROOT = Path.home() / ".claude"
# scripts/ first so ollama_client/cheap_llm resolve; hooks/ for context_guard_lib.
for _candidate in (_CLAUDE_ROOT / "scripts", _CLAUDE_ROOT / "hooks"):
    _s = str(_candidate)
    if _candidate.is_dir() and _s not in sys.path:
        sys.path.insert(0, _s)

try:  # Reset context-guard turn counter on compact (lives in ~/.claude/hooks/).
    from context_guard_lib import reset_state as cg_reset
except Exception:  # pragma: no cover - env-dependent
    cg_reset = None  # type: ignore[assignment]

try:  # Shared local-Ollama client (chat/generate/embed) in ~/.claude/scripts/.
    import ollama_client
except Exception:  # pragma: no cover - env-dependent
    ollama_client = None  # type: ignore[assignment]

try:
    # Scrubbing happens INSIDE cheap_complete (always, even prefer_local) — no
    # separate scrub import needed here (verified 2026-07-02 in the monolith).
    from cheap_llm import cheap_complete
except Exception:  # pragma: no cover - env-dependent
    cheap_complete = None  # type: ignore[assignment]

__all__ = ["cg_reset", "ollama_client", "cheap_complete"]
