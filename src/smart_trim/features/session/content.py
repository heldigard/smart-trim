"""Conversation content extraction from Claude Code JSONL messages.

Walks messages newest-first, unwraps the ``message`` envelope, keeps
user/assistant text + terse tool-result lines (errors get a larger cap), and
stops once ``max_length`` chars are accumulated so the local LLM stays within
its VRAM/ctx budget. Distinct from session *discovery* (command.py): this
module only shapes already-loaded messages for summarization.
"""
from __future__ import annotations

import json
from typing import Any

from smart_trim.shared.config import MAX_CONTEXT_FOR_SUMMARY

# Skip these JSONL line types entirely — not conversation content.
_NON_CONVERSATION_TYPES = ("last-prompt", "mode", "permission-mode", "attachment")


def extract_context_for_summary(
    messages: list[dict[str, Any]], max_length: int = MAX_CONTEXT_FOR_SUMMARY
) -> str:
    """Extract conversation context for LLM summarization (newest-first, capped)."""
    context_parts: list[str] = []
    total_length = 0

    for msg in reversed(messages):
        if msg.get("type", "") in _NON_CONVERSATION_TYPES:
            continue
        inner = msg.get("message", msg)
        if not isinstance(inner, dict):
            continue
        role = inner.get("role", "")
        if role not in ("user", "assistant"):
            continue
        text = _extract_text_from_content(inner.get("content", ""), role)
        if not text:
            continue
        part = f"[{role.upper()}]: {text}"
        if total_length + len(part) > max_length:
            break
        context_parts.insert(0, part)
        total_length += len(part)

    return "\n\n".join(context_parts)


def _extract_text_from_content(content: Any, role: str) -> str:
    """Extract readable text from a Claude Code content field."""
    # Larger cap for the conversation; tool results stay terse unless erroring.
    text_cap = 1200 if role == "user" else 1000
    result_cap = 300

    if isinstance(content, str):
        return content[:text_cap]
    if isinstance(content, list):
        parts = _extract_from_blocks(content, text_cap, result_cap)
        return " ".join(parts)[:text_cap]
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)[:500]
    return str(content)[:500]


def _extract_from_blocks(
    blocks: list[Any], text_cap: int, result_cap: int
) -> list[str]:
    """Flatten a content-block list into text fragments (thinking blocks skipped)."""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        parts.extend(_extract_from_block(block, text_cap, result_cap))
    return parts


def _extract_from_block(block: dict[str, Any], text_cap: int, result_cap: int) -> list[str]:
    """Extract text from a single content block by its type."""
    btype = block.get("type", "")
    if btype == "text":
        return [block.get("text", "")[:text_cap]]
    if btype == "tool_use":
        name = block.get("name", "unknown")
        inp = json.dumps(block.get("input", {}), ensure_ascii=False)[:200]
        return [f"[Tool: {name}({inp})]"]
    if btype == "tool_result":
        return _extract_from_result(block, result_cap)
    # thinking / unknown -> skipped (too verbose for summary)
    return []


def _extract_from_result(block: dict[str, Any], result_cap: int) -> list[str]:
    """Extract text from a tool_result block (errors get a larger cap)."""
    is_error = bool(block.get("is_error") or block.get("error"))
    cap = 600 if is_error else result_cap
    rc = block.get("content", "")
    if isinstance(rc, list):
        return _extract_from_result_list(rc, cap)
    if isinstance(rc, str):
        return [f"[Result: {rc[:cap]}]"]
    return []


def _extract_from_result_list(items: list[Any], cap: int) -> list[str]:
    parts: list[str] = []
    for item in items:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(f"[Result: {item.get('text', '')[:cap]}]")
    return parts


__all__ = ["extract_context_for_summary"]
