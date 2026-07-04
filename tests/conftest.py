"""Shared pytest fixtures for smart-trim."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure src/ is importable when running pytest from a checkout that has not
# been `pip install -e`'d yet (pyproject [tool.pytest] pythonpath also does it,
# but this makes IDE/standalone runs work too).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
