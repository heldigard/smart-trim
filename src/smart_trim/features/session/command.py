"""Discover the active Claude Code session and extract conversation context.

Resolution order for the session file:
  1. ``CLAUDE_SESSION_FILE`` env var (SessionStart hooks)
  2. Build from ``sessionId`` + ``cwd`` in the stdin JSON (PreCompact fallback)
  3. Most recent JSONL across all projects (last resort)

Context extraction walks the JSONL newest-first, unwraps the ``message``
envelope, keeps user/assistant text + terse tool-result lines, and caps total
length so the local LLM stays within VRAM/ctx budget.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from smart_trim.shared.config import MAX_CONTEXT_FOR_SUMMARY


def find_latest_session_jsonl() -> Path | None:
    """Find the most recently modified session JSONL across ALL project dirs.

    Searches ~/.claude/projects/*/ for the newest .jsonl file. This is necessary
    because PreCompact cwd may differ from the session's actual project directory
    (e.g. cwd=~/.claude/hooks but session in -home-eldi/).
    """
    # CLI guard: only resolve from the Claude session store when actually running
    # under Claude Code. Other CLIs (Gemini via ~/.gemini/hooks/smart-trim.py)
    # have NO Claude session; without this guard they would summarize a random
    # Claude session and clobber the shared activeContext.md with wrong-CLI data.
    if not _has_claude_session_env():
        return None
    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.is_dir():
        return None
    all_jsonl = _collect_project_jsonls(projects_root)
    if not all_jsonl:
        return None
    try:
        return max(all_jsonl, key=lambda p: p.stat().st_mtime)
    except (OSError, ValueError):
        return None


def _has_claude_session_env() -> bool:
    return any(
        os.environ.get(v)
        for v in ("CLAUDE_SESSION_ID", "CLAUDE_SESSION_FILE", "CLAUDE_PROJECT_DIR")
    )


def _collect_project_jsonls(projects_root: Path) -> list[Path]:
    out: list[Path] = []
    for project_dir in projects_root.iterdir():
        if project_dir.is_dir():
            out.extend(project_dir.glob("*.jsonl"))
    return out


def get_session_file(input_data: dict[str, Any] | None = None) -> Path | None:
    """Get current session file path (see module docstring for resolution order)."""
    # 1. Try env var (works in SessionStart)
    session_file = os.environ.get("CLAUDE_SESSION_FILE")
    if session_file and Path(session_file).exists():
        return Path(session_file)
    # 2. Build from stdin sessionId + cwd (PreCompact fallback)
    if input_data:
        found = _resolve_from_stdin(input_data)
        if found is not None:
            return found
    # 3. Last resort: most recent JSONL across all projects
    return find_latest_session_jsonl()


def _resolve_from_stdin(input_data: dict[str, Any]) -> Path | None:
    """Resolve a session file from the stdin payload (sessionId + cwd)."""
    session_id = input_data.get("sessionId") or os.environ.get("CLAUDE_SESSION_ID")
    cwd = input_data.get("cwd") or os.environ.get("PWD", str(Path.cwd()))
    if not (session_id and cwd):
        return None
    candidate = _candidate_from_cwd(session_id, cwd)
    if candidate is not None:
        return candidate
    return _search_session_id_all_projects(session_id)


def _candidate_from_cwd(session_id: str, cwd: str) -> Path | None:
    """Build the session JSONL path from cwd's encoded project dir."""
    resolved = str(Path(cwd).resolve())
    encoded = "-" + resolved.lstrip("/").replace("/", "-")
    candidate = Path.home() / ".claude" / "projects" / encoded / f"{session_id}.jsonl"
    return candidate if candidate.exists() else None


def _search_session_id_all_projects(session_id: str) -> Path | None:
    """cwd may not match the session's project dir — search all projects."""
    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.is_dir():
        return None
    for project_dir in projects_root.iterdir():
        if not project_dir.is_dir():
            continue
        sid_candidate = project_dir / f"{session_id}.jsonl"
        if sid_candidate.exists():
            return sid_candidate
    return None


def get_session_id(input_data: dict[str, Any] | None = None) -> str:
    """Get current session ID from env var or stdin data."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    if input_data:
        sid = input_data.get("sessionId")
        if sid:
            return str(sid)
    return "unknown"


def get_context_usage() -> float:
    """Estimate context usage from environment. Returns percentage (0-100)."""
    context_used = os.environ.get("CLAUDE_CONTEXT_USED")
    context_total = os.environ.get("CLAUDE_CONTEXT_TOTAL")
    if context_used and context_total:
        try:
            used = int(context_used)
            total = int(context_total)
            return (used / total) * 100.0 if total > 0 else 0.0
        except (ValueError, ZeroDivisionError):
            pass
    return 0.0


def read_session(session_file: Path) -> list[dict[str, Any]]:
    """Read session from JSONL file (skip blank/malformed lines)."""
    if not session_file.exists():
        return []
    with open(session_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    parsed = [_parse_jsonl_line(ln) for ln in lines]
    return [msg for msg in parsed if msg is not None]


def _parse_jsonl_line(line: str) -> dict[str, Any] | None:
    if not line.strip():
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def extract_context_for_summary(
    messages: list[dict[str, Any]], max_length: int = MAX_CONTEXT_FOR_SUMMARY
) -> str:
    """Extract conversation context for LLM summarization.

    Prioritizes user messages, assistant text, tool calls. Handles Claude Code
    JSONL where messages are nested in a 'message' key. Walks newest-first and
    stops once ``max_length`` chars are accumulated.
    """
    context_parts: list[str] = []
    total_length = 0

    for msg in reversed(messages):
        # Skip non-conversation lines (last-prompt, mode, permission-mode, attachment)
        msg_type = msg.get("type", "")
        if msg_type in ("last-prompt", "mode", "permission-mode", "attachment"):
            continue

        # Unwrap 'message' envelope (Claude Code JSONL format)
        inner = msg.get("message", msg)
        if not isinstance(inner, dict):
            continue

        role = inner.get("role", "")
        if role not in ("user", "assistant"):
            continue

        content = inner.get("content", "")
        text = _extract_text_from_content(content, role)
        if not text:
            continue

        part = f"[{role.upper()}]: {text}"
        part_len = len(part)

        if total_length + part_len > max_length:
            break

        context_parts.insert(0, part)
        total_length += part_len

    return "\n\n".join(context_parts)


def _extract_text_from_content(content: Any, role: str) -> str:
    """Extract readable text from Claude Code content field."""
    # Slightly larger caps for the actual conversation; tool results stay terse
    # unless they contain an error, in which case we keep more context.
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


__all__ = [
    "find_latest_session_jsonl",
    "get_session_file",
    "get_session_id",
    "get_context_usage",
    "read_session",
    "extract_context_for_summary",
]
