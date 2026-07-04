"""Time-window helpers for staleness filtering (no feature deps).

Used by ``grounding`` to decide whether ``current-objective.json`` is fresh
enough to inject into a compact handoff. Window is overridable via env so tests
can pin it (``OBJECTIVE_INJECTION_WINDOW_HOURS`` /
``MEMORY_INJECTION_ACTIVE_WINDOW_HOURS``).
"""

from __future__ import annotations

import os
from datetime import datetime


def objective_injection_window_hours() -> float:
    """Maximum age (hours) for current-objective.json injection into compact handoffs."""
    raw = os.environ.get(
        "OBJECTIVE_INJECTION_WINDOW_HOURS",
        os.environ.get("MEMORY_INJECTION_ACTIVE_WINDOW_HOURS", "24"),
    )
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 24.0


def hours_since_iso(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
    return (now - dt).total_seconds() / 3600.0


__all__ = ["objective_injection_window_hours", "hours_since_iso"]
