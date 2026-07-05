#!/usr/bin/env python3
"""Smart Trim hook shim — delegates to the ``smart_trim`` package (~/smart-trim/).

The package is ``pip install -e``'d, so ``import smart_trim`` resolves from any
CWD. This shim preserves the wired path ``~/.claude/hooks/smart-trim.py`` so
``~/.claude/settings.json`` (PreCompact) and the Gemini symlink
``~/.gemini/hooks/smart-trim.py`` keep resolving untouched.

Source of truth: ``~/smart-trim/src/smart_trim/``. History/changelog there.
If the package ever fails to import, fail OPEN (never block compaction).
"""
import sys

try:
    from smart_trim.features.precompact.command import main
except Exception as exc:  # pragma: no cover — never block compaction
    sys.stderr.write(f"[smart-trim] shim import failed; falling back to no-op: {exc}\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
