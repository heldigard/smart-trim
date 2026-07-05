"""PreCompact orchestrator + hook entry point.

``handle_precompact`` is the end-to-end pipeline for the PreCompact event:
resolve the session, ground the summary, run the LLM cascade, augment with
negative constraints + objective, archive, rotate, persist to the memory bank.

It imports sibling feature modules (not their functions) and reaches attributes
through them at call time — **late binding by module** — so pytest
``monkeypatch.setattr`` on the origin module's function resolves correctly
post-split. (Direct ``from ..summarize import summarize_primary`` would bind the
name into this module's namespace and defeat the monkeypatch.)

PreCompact hook output schema: only top-level ``continue`` / ``systemMessage`` /
``reason`` are accepted; ``hookSpecificOutput`` is rejected and silently
discarded, so the summary is saved to the project memory bank and surfaced via
``systemMessage``. ``memory-inject.sh`` reloads it on the next SessionStart.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from smart_trim.features.fallback import command as _fallback
from smart_trim.features.grounding import command as _grounding
from smart_trim.features.hygiene import command as _hygiene
from smart_trim.features.session import command as _session
from smart_trim.features.summarize import command as _summarize
from smart_trim.features.writer import command as _writer
from smart_trim.shared import compat as _compat
from smart_trim.shared import ollama as _ollama
from smart_trim.shared import paths as _paths
from smart_trim.shared.config import MAX_CONTEXT_FOR_CLOUD

_POST_COMPACT_RULES = (
    "\n---\n"
    "POST-COMPACT RULES (next 3 turns):\n"
    "1. DO NOT re-read files you already know from this summary\n"
    "2. DO NOT read screenshots/images into context\n"
    "3. Use grep/find to locate, read ONLY needed lines (max 50)\n"
    "4. DO NOT re-read rules files — they are already loaded\n"
    "5. Work from this summary, not from scratch\n"
)


def handle_precompact(input_data: dict[str, Any]) -> dict[str, Any]:
    """Handle PreCompact event - called before Claude's compression."""
    trigger = input_data.get("trigger", "unknown")
    _safe_reset_cg()

    session_file = _session.get_session_file(input_data)
    project_root = _paths.get_project_root(input_data.get("cwd") or os.environ.get("PWD"))
    grounding, objective_block = _build_grounding(project_root)
    session_id = _session.get_session_id(input_data)

    summary_text, method, preserved = _resolve_summary(session_file, grounding, session_id, trigger)
    summary_text = _augment(summary_text, preserved, objective_block)

    _archive_summary(summary_text, method, trigger, session_id)
    # Rotate AFTER writing so the "keep newest N" invariant holds.
    _hygiene.cleanup_old_summaries()
    _writer.update_project_memory(
        summary_text + _POST_COMPACT_RULES, method, session_id, project_root=project_root
    )

    return _final_message(method, trigger, _hygiene.check_memory_hygiene())


def _safe_reset_cg() -> None:
    """Reset context-guard turn counter so warnings start fresh post-compact."""
    if _compat.cg_reset is None:
        return
    try:
        _compat.cg_reset()
    except Exception:
        pass


def _build_grounding(project_root: Path) -> tuple[str, str]:
    """Return (grounding_text, objective_block) anchoring the summary."""
    grounding = _grounding.load_memory_grounding(project_root)
    objective_block = _grounding.load_objective_registry(project_root)
    if objective_block:
        grounding = f"{grounding}\n\n{objective_block}" if grounding else objective_block
    return grounding, objective_block


def _resolve_summary(
    session_file: Path | None,
    grounding: str,
    session_id: str,
    trigger: str,
) -> tuple[str, str, str]:
    """Run the LLM cascade when there is a session, else minimal handoff.

    Returns ``(summary_text, method, preserved_constraints)``. The cascade
    selection only needs ``grounding`` (for negative-constraint extraction);
    ``objective_block`` is carried separately by ``handle_precompact`` and
    merged into the output by ``_augment``.
    """
    preserved = _grounding.extract_negative_constraints(grounding)
    if not (session_file and session_file.exists()):
        return _minimal_handoff(session_id, trigger), "minimal", preserved
    messages = _session.read_session(session_file)
    if not messages:
        return _minimal_handoff(session_id, trigger), "minimal", preserved
    return _cascade(messages, grounding, preserved, session_id)


def _minimal_handoff(session_id: str, trigger: str) -> str:
    return (
        f"**Task**: Session {session_id} compacted ({trigger})\n"
        "**Notes**: No session JSONL available; using minimal handoff.\n"
        "**Next**: Reload from project memory bank if needed."
    )


def _cascade(
    messages: list, grounding: str, preserved: str, session_id: str
) -> tuple[str, str, str]:
    """Primary -> secondary -> cloud -> rule-based, returning (text, method, preserved)."""
    context = _session.extract_context_for_summary(messages)
    preserved = _maybe_update_preserved(preserved, _grounding.extract_negative_constraints(context))
    summary_grounding = _join_grounding(grounding, preserved)

    text, method = _try_local(context, summary_grounding)
    if text is None:
        text, method = _try_cloud(messages, grounding, preserved)
    if text is None or method is None:
        text = _fallback.generate_fallback_summary(messages, session_id)
        method = "fallback"
    return text, method, preserved


def _try_local(context: str, summary_grounding: str) -> tuple[str | None, str | None]:
    """Ollama primary then secondary. Returns (text, method) or (None, None)."""
    if not _ollama.is_ollama_alive():
        return None, None
    text = _summarize.summarize_primary(context, grounding=summary_grounding)
    if text:
        # label must track summarize._PRIMARY_MODEL (SetneufPT/Qwopus3.5-4B-Coder-MTP)
        return text, "ollama-setneuf-qwopus3.5"
    text = _summarize.summarize_secondary(context, grounding=summary_grounding)
    if text:
        # label must track summarize._SECONDARY_MODEL (qwen3.5:4b)
        return text, "ollama-qwen3.5:4b"
    return None, None


def _try_cloud(messages: list, grounding: str, preserved: str) -> tuple[str | None, str | None]:
    """Cloud cascade tier (re-extracts at the larger cap for DeepSeek 1M ctx)."""
    cloud_context = _session.extract_context_for_summary(messages, max_length=MAX_CONTEXT_FOR_CLOUD)
    new_preserved = _grounding.extract_negative_constraints(cloud_context)
    summary_grounding = _join_grounding(grounding, new_preserved or preserved)
    text = _summarize.summarize_cloud_cascade(cloud_context, grounding=summary_grounding)
    if text:
        return text, "deepseek-cloud"
    return None, None


def _augment(summary_text: str, preserved: str, objective_block: str) -> str:
    """Ensure the handoff carries constraints + objective even if the LLM omitted them."""
    if preserved and preserved not in summary_text:
        summary_text = f"{preserved}\n\n{summary_text}"
    if objective_block:
        summary_text = f"{objective_block}\n\n{summary_text}"
    return summary_text


def _archive_summary(summary_text: str, method: str, trigger: str, session_id: str) -> None:
    """Persist to ~/.claude/summaries/ for archive and ad-hoc retrieval (best-effort)."""
    try:
        summary_dir = Path.home() / ".claude" / "summaries"
        summary_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        summary_file = summary_dir / f"{session_id}-{timestamp}.md"
        header = f"<!-- {datetime.now().isoformat()} | {method} | trigger={trigger} -->\n\n"
        summary_file.write_text(header + summary_text, encoding="utf-8")
    except Exception:
        # Summary archive is best-effort; never block compaction.
        pass


def _final_message(method: str, trigger: str, memory_warning: str | None) -> dict[str, Any]:
    """Build the PreCompact return dict (manual /compact stays silent)."""
    is_manual = trigger == "manual"
    saved = f"[smart-trim] {method} summary saved to .memory-bank/activeContext.md"
    if memory_warning and not is_manual:
        return {"continue": True, "systemMessage": f"{saved}. {memory_warning}"}
    if is_manual:
        return {"continue": True}
    return {"continue": True, "systemMessage": f"{saved} (will reload on next SessionStart)."}


def _maybe_update_preserved(current: str, new: str) -> str:
    return new if new else current


def _join_grounding(grounding: str, preserved: str) -> str:
    if grounding and preserved:
        return f"{grounding}\n\n{preserved}"
    return preserved or grounding


def main() -> None:
    """Main hook entry point for PreCompact event."""
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError):
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)
    output = handle_precompact(input_data)
    print(json.dumps(output, ensure_ascii=False))


__all__ = ["handle_precompact", "main"]
