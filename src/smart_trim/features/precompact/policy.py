"""Hook return-dict policy: skip decisions and route-aware final messages."""

from __future__ import annotations

from typing import Any


def is_unusable_minimal(summary_text: str, method: str, objective_block: str) -> bool:
    """True only for the synthetic no-transcript handoff with no live objective."""
    return (
        method == "minimal" and not objective_block and "No session JSONL available" in summary_text
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


def final_message(
    method: str, trigger: str, memory_warning: str | None, route: str = "active"
) -> dict[str, Any]:
    """Build the PreCompact return dict (manual /compact stays silent).

    ``route`` comes from the writer so the message never claims an
    activeContext update that was actually routed elsewhere or failed.
    """
    if trigger == "manual":
        return {"continue": True}
    if route == "foreign":
        saved = (
            f"[smart-trim] {method} summary routed to "
            ".memory-bank/topics/foreign-sessions.md (cross-project session)"
        )
        suffix = "."
    elif route == "error":
        saved = (
            f"[smart-trim] {method} summary archived to ~/.claude/summaries; "
            "memory-bank write failed"
        )
        suffix = "."
    else:
        saved = f"[smart-trim] {method} summary saved to .memory-bank/activeContext.md"
        suffix = " (will reload on next SessionStart)."
    if memory_warning:
        return {"continue": True, "systemMessage": f"{saved}. {memory_warning}"}
    return {"continue": True, "systemMessage": f"{saved}{suffix}"}


__all__ = ["final_message", "is_unusable_minimal", "skipped_message"]
