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
discarded, so the summary is saved to the agent memory bank and surfaced via
``systemMessage``. ``memory-inject.sh`` reloads it on the next SessionStart.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from smart_trim import __version__
from smart_trim.features.capabilities import command as _capabilities
from smart_trim.features.fallback import command as _fallback
from smart_trim.features.grounding import command as _grounding
from smart_trim.features.hygiene import command as _hygiene
from smart_trim.features.observability import command as _observability
from smart_trim.features.precompact import policy as _policy
from smart_trim.features.session import command as _session
from smart_trim.features.summarize import command as _summarize
from smart_trim.features.writer import command as _writer
from smart_trim.shared import compat as _compat
from smart_trim.shared import ollama as _ollama
from smart_trim.shared import paths as _paths
from smart_trim.shared.config import (
    CASCADE_BUDGET_SECONDS,
    CASCADE_MIN_TIER_SECONDS,
    MAX_CONTEXT_FOR_CLOUD,
    OLLAMA_TIMEOUT_SECONDS,
)


def handle_precompact(input_data: dict[str, Any]) -> dict[str, Any]:
    """Handle PreCompact event - called before Claude's compression."""
    trigger = input_data.get("trigger", "unknown")
    _safe_reset_cg()
    start = time.monotonic()

    session_file = _session.get_session_file(input_data)
    project_root = _paths.get_project_root(input_data.get("cwd") or os.environ.get("PWD"))
    grounding, objective_block = _build_grounding(project_root)
    session_id = _session.get_session_id(input_data)
    input_bytes = len(grounding) + len(objective_block)

    summary_text, method, preserved, model_chain = _resolve_summary(
        session_file, grounding, session_id, trigger
    )
    if _policy.is_unusable_minimal(summary_text, method, objective_block):
        # Never replace a useful durable handoff with "session unknown / no
        # JSONL". This occurs when a hook fires outside Claude or the runtime
        # omits its transcript. Preserving the previous activeContext is more
        # informative than writing a synthetic empty summary.
        _record_event(
            project_root,
            _observability.CompactEvent(
                method=method,
                route="skipped",
                trigger=trigger,
                latency_ms=_elapsed_ms(start),
                input_bytes=input_bytes,
                output_bytes=len(summary_text),
                model_chain=tuple(model_chain),
                session_id=session_id,
            ),
        )
        return _policy.skipped_message(trigger)
    summary_text = _augment(summary_text, preserved, objective_block)
    # One sanitized representation feeds every persistence sink. Previously the
    # standalone archive received raw model/session text before writer redaction.
    summary_text = _writer.mark_handoff_non_authoritative(_paths.redact_sensitive(summary_text))
    output_bytes = len(summary_text)

    _archive_summary(summary_text, method, trigger, session_id)
    # Rotate AFTER writing so the "keep newest N" invariant holds.
    _hygiene.cleanup_old_summaries()
    route = (
        _writer.update_agent_memory(summary_text, method, session_id, project_root=project_root)
        or "active"
    )

    _record_event(
        project_root,
        _observability.CompactEvent(
            method=method,
            route=route,
            trigger=trigger,
            latency_ms=_elapsed_ms(start),
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            model_chain=tuple(model_chain),
            session_id=session_id,
        ),
    )

    return _policy.final_message(method, trigger, _hygiene.check_memory_hygiene(), route)


def _safe_reset_cg() -> None:
    """Reset context-guard turn counter so warnings start fresh post-compact."""
    if _compat.cg_reset is None:
        return
    try:
        _compat.cg_reset()
    except Exception:
        pass


def _elapsed_ms(start_monotonic: float) -> int:
    """Wall-clock elapsed since ``start_monotonic`` as an int milliseconds."""
    return int((time.monotonic() - start_monotonic) * 1000)


def _record_event(project_root: Path, event: _observability.CompactEvent) -> None:
    """Best-effort observability append. Never raises; gate is checked inside.

    Wrapped in a try/except so the recorder (an opt-in side channel) cannot
    ever convert a successful compaction into a failure. Five lines, not a
    fancier abstraction — the call site already knows every field.
    """
    try:
        _observability.record_compact_event(project_root, event)
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
) -> tuple[str, str, str, list[str]]:
    """Run the LLM cascade when there is a session, else minimal handoff.

    Returns ``(summary_text, method, preserved_constraints, model_chain)``. The
    model_chain lists every tier that was attempted in order — empty for the
    minimal handoff, ``["rule-based"]`` for the rule-based fallback. The
    observability recorder uses this to feed ``topics/compact-events.md``.
    """
    preserved = _grounding.extract_negative_constraints(grounding)
    if not (session_file and session_file.exists()):
        return _minimal_handoff(session_id, trigger), "minimal", preserved, []
    messages = _session.read_session(session_file)
    if not messages:
        return _minimal_handoff(session_id, trigger), "minimal", preserved, []
    return _cascade(messages, grounding, preserved, session_id)


def _minimal_handoff(session_id: str, trigger: str) -> str:
    return (
        f"**Task**: Session {session_id} compacted ({trigger})\n"
        "**Notes**: No session JSONL available; using minimal handoff.\n"
        "**Next**: Reload from agent memory bank if needed."
    )


def _cascade(
    messages: list, grounding: str, preserved: str, session_id: str
) -> tuple[str, str, str, list[str]]:
    """Primary -> secondary -> cloud -> rule-based.

    Returns ``(text, method, preserved, model_chain)`` where ``model_chain``
    records every tier actually tried (so an observability event shows a hung
    or rejected primary even when the secondary ultimately succeeded).
    """
    context = _session.extract_context_for_summary(messages)
    preserved = _maybe_update_preserved(preserved, _grounding.extract_negative_constraints(context))
    summary_grounding = _join_grounding(grounding, preserved)

    # One wall-clock budget for the whole LLM cascade. A hung model cannot blow
    # the PreCompact hook timeout this way — each tier's timeout shrinks with
    # the remaining budget, and exhaustion fails OPEN to rule-based fallback.
    deadline = time.monotonic() + CASCADE_BUDGET_SECONDS
    chain: list[str] = []
    text, method, local_chain = _try_local(context, summary_grounding, deadline)
    chain.extend(local_chain)
    if text is None:
        text, method, cloud_chain = _try_cloud(messages, grounding, preserved, deadline)
        chain.extend(cloud_chain)
    if text is None or method is None:
        text = _fallback.generate_fallback_summary(messages, session_id)
        method = "fallback"
        chain.append("rule-based")
    return text, method, preserved, chain


def _tier_timeout(deadline: float, share: float = 1.0) -> float | None:
    """Remaining budget clamped to the per-call ceiling; ``None`` when exhausted.

    ``share`` lets a caller reserve part of the remaining budget for a later
    tier (primary takes 60% so secondary still gets a turn if primary fails).
    Below ``CASCADE_MIN_TIER_SECONDS`` we return ``None`` — starting a call
    that cannot finish just wastes a round-trip.
    """
    remaining = deadline - time.monotonic()
    if remaining < CASCADE_MIN_TIER_SECONDS:
        return None
    return min(OLLAMA_TIMEOUT_SECONDS, remaining * share)


def _try_local(
    context: str, summary_grounding: str, deadline: float | None = None
) -> tuple[str | None, str | None, list[str]]:
    """Ollama primary then secondary. Returns ``(text, method, attempted_chain)``.

    ``attempted_chain`` lists every tier that was actually tried (so a hung or
    rejected primary is visible in observability even when the secondary
    ultimately succeeded). The ``method`` label, when non-None, is derived
    from the active model tag (env-aware) so overrides keep
    ``.memory-bank/activeContext.md`` truthful.
    """
    attempted: list[str] = []
    if deadline is None:
        deadline = time.monotonic() + CASCADE_BUDGET_SECONDS
    if not _ollama.is_ollama_alive():
        return None, None, attempted
    # Primary gets 60% of the remaining budget so secondary still has a turn if
    # primary fails; both per-call caps stay under OLLAMA_TIMEOUT_SECONDS.
    primary_timeout = _tier_timeout(deadline, share=0.6)
    primary_label = _summarize.primary_label()
    if primary_timeout is not None:
        attempted.append(primary_label)
        text = _summarize.summarize_primary(
            context, grounding=summary_grounding, timeout=primary_timeout
        )
        if text:
            return text, primary_label, attempted
    secondary_timeout = _tier_timeout(deadline, share=1.0)
    secondary_label = _summarize.secondary_label()
    if secondary_timeout is not None:
        attempted.append(secondary_label)
        text = _summarize.summarize_secondary(
            context, grounding=summary_grounding, timeout=secondary_timeout
        )
        if text:
            return text, secondary_label, attempted
    return None, None, attempted


def _try_cloud(
    messages: list, grounding: str, preserved: str, deadline: float | None = None
) -> tuple[str | None, str | None, list[str]]:
    """Cloud cascade tier (re-extracts at the larger cap for DeepSeek 1M ctx).

    Returns ``(text, method, attempted_chain)`` — chain lists the cloud label
    when the budget permitted a call, empty otherwise.
    """
    attempted: list[str] = []
    if deadline is None:
        deadline = time.monotonic() + CASCADE_BUDGET_SECONDS
    cloud_timeout = _tier_timeout(deadline, share=1.0)
    if cloud_timeout is None:
        return None, None, attempted
    cloud_label = _summarize.cloud_label()
    attempted.append(cloud_label)
    cloud_context = _session.extract_context_for_summary(messages, max_length=MAX_CONTEXT_FOR_CLOUD)
    new_preserved = _grounding.extract_negative_constraints(cloud_context)
    summary_grounding = _join_grounding(grounding, new_preserved or preserved)
    text = _summarize.summarize_cloud_cascade(
        cloud_context, grounding=summary_grounding, timeout_total=cloud_timeout
    )
    if text:
        return text, cloud_label, attempted
    return None, None, attempted


def _augment(summary_text: str, preserved: str, objective_block: str) -> str:
    """Ensure the handoff carries constraints + objective even if the LLM omitted them."""
    if preserved and preserved not in summary_text:
        summary_text = f"{preserved}\n\n{summary_text}"
    if objective_block:
        summary_text = f"{objective_block}\n\n{summary_text}"
    return summary_text


def _archive_summary(summary_text: str, method: str, trigger: str, session_id: str) -> None:
    """Persist to the canonical archive dir for ad-hoc retrieval (best-effort).

    The directory lives in ``shared.paths.default_summaries_dir`` — the writer
    (``precompact``) and the rotator (``hygiene``) MUST share the same path,
    otherwise rotation silently no-ops on the wrong tree.
    """
    try:
        summary_dir = _paths.default_summaries_dir()
        summary_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S-%f")
        session_label = _paths.slugify(str(session_id))[:80]
        nonce = secrets.token_hex(4)
        summary_file = summary_dir / f"{session_label}-{timestamp}-{nonce}.md"
        header = f"<!-- {now.isoformat()} | {method} | trigger={trigger} -->\n\n"
        summary_file.write_text(header + summary_text, encoding="utf-8")
    except Exception:
        # Summary archive is best-effort; never block compaction.
        pass


def _maybe_update_preserved(current: str, new: str) -> str:
    return new if new else current


def _join_grounding(grounding: str, preserved: str) -> str:
    if grounding and preserved:
        return f"{grounding}\n\n{preserved}"
    return preserved or grounding


def main() -> None:
    """Main hook entry point for PreCompact event."""
    if sys.argv[1:] == ["--version"]:
        print(f"smart-trim {__version__}")
        return
    if _capabilities.handle_cli(sys.argv[1:]):
        return
    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, ValueError):
        sys.exit(0)
    if not isinstance(input_data, dict):
        sys.exit(0)
    try:
        output = handle_precompact(input_data)
    except Exception as exc:
        # Fail OPEN: a summarization bug must never block or noise up the
        # user's compaction. The memory-bank handoff is lost for this compact,
        # but the error stays visible on stderr for diagnosis.
        print(f"[smart-trim] precompact failed: {exc!r}", file=sys.stderr)
        output = {"continue": True}
    print(json.dumps(output, ensure_ascii=False))


__all__ = ["handle_precompact", "main"]
