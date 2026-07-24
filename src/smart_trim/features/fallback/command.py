"""Rule-based fallback summary — always succeeds, no LLM needed.

Last-resort handoff when the entire LLM cascade (Ollama primary/secondary +
cloud tertiary) is unavailable. Extracts file paths, error lines and decision
cues from the raw messages with plain regex so it works offline and in <1ms.
"""

from __future__ import annotations

import json
import re
from typing import Any

from smart_trim.shared.config import MAX_FALLBACK_SUMMARY


def generate_fallback_summary(messages: list[dict[str, Any]], session_id: str = "unknown") -> str:
    """Generate basic summary without LLM (last resort)."""
    # Normalize: unwrap 'message' envelope for all messages
    normalized: list[dict[str, Any]] = []
    for m in messages:
        inner = m.get("message", m)
        if isinstance(inner, dict) and inner.get("role"):
            normalized.append(inner)

    user_msgs = [m for m in normalized if m.get("role") == "user"]

    file_paths = _extract_file_paths(normalized)
    errors = _extract_errors(normalized)
    decisions = _extract_decisions(normalized)

    error_str = "\n".join([f"- {e}" for e in errors]) if errors else "None detected"
    decision_str = "\n".join([f"- {d}" for d in decisions]) if decisions else "None detected"

    summary = f"""**Task**: Session with {len(user_msgs)} user requests
**Files**: {", ".join(file_paths[:8]) if file_paths else "None"}
**Errors**: {error_str}
**Decisions**: {decision_str}
**Session**: {session_id}"""

    return summary[:MAX_FALLBACK_SUMMARY]


def _extract_file_paths(normalized: list[dict[str, Any]]) -> list[str]:
    """Pull unix + windows file paths out of message content and tool inputs."""
    file_paths: list[str] = []
    seen: set[str] = set()
    for msg in normalized:
        raw = str(msg.get("content", ""))
        raw += " " + json.dumps(msg.get("input", {}), ensure_ascii=False)
        for path in _paths_in(raw):
            if path not in seen:
                seen.add(path)
                file_paths.append(path)
    return file_paths


def _paths_in(raw: str) -> list[str]:
    paths = re.findall(r"/[\w/.-]+\.\w+", raw)
    paths.extend(re.findall(r"[A-Za-z]:\\[\w\\.-]+", raw))
    return paths[:10]


_ERROR_CUES = ("error", "exception", "failed", "traceback")


def _extract_errors(normalized: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for msg in normalized:
        raw = str(msg.get("content", ""))
        if _text_has_any(raw, _ERROR_CUES):
            errors.extend(_error_lines(raw))
        if len(errors) >= 3:
            return errors[:3]
    return errors


def _error_lines(raw: str) -> list[str]:
    cues = ("error", "exception", "failed")
    return [line.strip()[:200] for line in raw.split("\n") if _text_has_any(line, cues)]


def _text_has_any(text: str, cues: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(cue in low for cue in cues)


_DECISION_CUES = ("decided", "decision", "agreed", "chose")


def _extract_decisions(normalized: list[dict[str, Any]]) -> list[str]:
    decisions: list[str] = []
    for msg in normalized:
        if len(decisions) >= 3:
            break
        raw = str(msg.get("content", ""))
        if _text_has_any(raw, _DECISION_CUES):
            decisions.append(raw[:150])
    return decisions


__all__ = ["generate_fallback_summary"]
