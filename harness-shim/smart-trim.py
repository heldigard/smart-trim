#!/usr/bin/env python3
"""Smart Trim hook shim — delegates to the ``smart_trim`` package (~/smart-trim/).

The shim bootstraps the source tree directly, so it still works when a worker
uses an isolated ``HOME`` and Python cannot see user-site editable installs.
This preserves the wired path ``~/.claude/hooks/smart-trim.py`` so
``~/.claude/settings.json`` (PreCompact) and the Gemini symlink
``~/.gemini/hooks/smart-trim.py`` keep resolving untouched.

Source of truth: ``~/smart-trim/src/smart_trim/``. History/changelog there.
If the package ever fails to import, fail OPEN (never block compaction).
"""

import os
import sys
from pathlib import Path


def _bootstrap_source() -> None:
    candidates = []
    if home := os.environ.get("SMART_TRIM_HOME"):
        candidates.append(Path(home))
    here = Path(__file__).resolve()
    candidates.extend([here.parent, here.parent.parent])
    try:
        candidates.append(here.parents[2] / "smart-trim")
    except IndexError:
        pass
    candidates.append(Path.home() / "smart-trim")

    for project in candidates:
        src = project / "src"
        if src.exists():
            sys.path.insert(0, str(src))
            return


_bootstrap_source()

try:
    from smart_trim.features.precompact.command import main
except Exception as exc:  # pragma: no cover — never block compaction
    sys.stderr.write(f"[smart-trim] shim import failed; falling back to no-op: {exc}\n")
    sys.exit(0)

if __name__ == "__main__":
    main()
