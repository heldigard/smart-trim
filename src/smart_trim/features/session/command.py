"""Discover the active Claude Code session and read its JSONL messages.

Resolution order for the session file:
  1. ``CLAUDE_SESSION_FILE`` env var (SessionStart hooks)
  2. Build from ``sessionId`` + ``cwd`` in the stdin JSON (PreCompact fallback)
  3. Most recent JSONL across all projects (last resort)

Content *extraction* (shaping messages for the LLM) lives in ``content.py`` — a
distinct sub-responsibility, kept separate so discovery stays small.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Re-exported for API stability: precompact reaches it as _session.extract...,
# and tests import it from the session package. The implementation lives in
# content.py (extraction is a separate responsibility from discovery).
from smart_trim.features.session.content import extract_context_for_summary


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
    with open(session_file, encoding="utf-8") as f:
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


__all__ = [
    "find_latest_session_jsonl",
    "get_session_file",
    "get_session_id",
    "get_context_usage",
    "read_session",
    "extract_context_for_summary",
]
