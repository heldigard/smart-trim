"""Persistence policy for low-information PreCompact events."""

from __future__ import annotations

from typing import Any


def is_unusable_minimal(summary_text: str, method: str, objective_block: str) -> bool:
    """True only for the synthetic no-transcript handoff with no live objective."""
    return (
        method == "minimal"
        and not objective_block
        and "No session JSONL available" in summary_text
    )


def skipped_message(trigger: str) -> dict[str, Any]:
    """Keep manual compaction quiet; explain preserved state on auto compact."""
    if trigger == "manual":
        return {"continue": True}
    return {
        "continue": True,
        "systemMessage": (
            "[smart-trim] no transcript or live objective; preserved existing "
            ".memory-bank/activeContext.md."
        ),
    }


__all__ = ["is_unusable_minimal", "skipped_message"]
