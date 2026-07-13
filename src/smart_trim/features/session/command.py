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
import re
from pathlib import Path
from typing import Any

# Re-exported for API stability: precompact reaches it as _session.extract...,
# and tests import it from the session package. The implementation lives in
# content.py (extraction is a separate responsibility from discovery).
from smart_trim.features.session.content import extract_context_for_summary

_SAFE_SESSION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


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
    for project_dir in _project_dirs(projects_root):
        try:
            out.extend(project_dir.glob("*.jsonl"))
        except OSError:
            continue
    return out


def _project_dirs(projects_root: Path) -> list[Path]:
    """List readable project directories without failing the whole lookup."""
    directories: list[Path] = []
    try:
        for entry in projects_root.iterdir():
            try:
                if entry.is_dir():
                    directories.append(entry)
            except OSError:
                continue
    except OSError:
        return directories
    return directories


def get_session_file(input_data: dict[str, Any] | None = None) -> Path | None:
    """Get current session file path (see module docstring for resolution order)."""
    # 1. Try env var (works in SessionStart)
    session_file = os.environ.get("CLAUDE_SESSION_FILE")
    if session_file and Path(session_file).exists():
        return Path(session_file)
    # 2. Use the transcript path provided by Claude/Codex hook payloads.
    if input_data:
        transcript = input_data.get("transcript_path") or input_data.get("transcriptPath")
        if transcript:
            candidate = Path(str(transcript)).expanduser()
            if candidate.is_file() and candidate.suffix == ".jsonl":
                return candidate
    # 3. Build from stdin sessionId + cwd (Claude PreCompact fallback)
    if input_data:
        found = _resolve_from_stdin(input_data)
        if found is not None:
            return found
    # 4. Last resort: most recent JSONL across all Claude projects
    return find_latest_session_jsonl()


def _resolve_from_stdin(input_data: dict[str, Any]) -> Path | None:
    """Resolve a session file from the stdin payload (sessionId + cwd)."""
    raw_session_id = (
        input_data.get("sessionId")
        or input_data.get("session_id")
        or os.environ.get("CLAUDE_SESSION_ID")
    )
    cwd = input_data.get("cwd") or os.environ.get("PWD", str(Path.cwd()))
    session_id = _validated_session_id(raw_session_id)
    if not (session_id and cwd):
        return None
    candidate = _candidate_from_cwd(session_id, cwd)
    if candidate is not None:
        return candidate
    return _search_session_id_all_projects(session_id)


def _candidate_from_cwd(session_id: str, cwd: str) -> Path | None:
    """Build the session JSONL path from cwd's encoded project dir."""
    validated_session_id = _validated_session_id(session_id)
    if validated_session_id is None:
        return None
    try:
        resolved = str(Path(cwd).resolve())
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    encoded = "-" + resolved.lstrip("/").replace("/", "-")
    candidate = Path.home() / ".claude" / "projects" / encoded / f"{validated_session_id}.jsonl"
    return candidate if candidate.exists() else None


def _search_session_id_all_projects(session_id: str) -> Path | None:
    """cwd may not match the session's project dir — search all projects."""
    validated_session_id = _validated_session_id(session_id)
    if validated_session_id is None:
        return None
    projects_root = Path.home() / ".claude" / "projects"
    for project_dir in _project_dirs(projects_root):
        sid_candidate = project_dir / f"{validated_session_id}.jsonl"
        if sid_candidate.exists():
            return sid_candidate
    return None


def _validated_session_id(value: Any) -> str | None:
    """Return a filename-safe Claude session ID, rejecting lossy mappings."""
    if value is None:
        return None
    session_id = str(value)
    return session_id if _SAFE_SESSION_ID_RE.fullmatch(session_id) else None


def get_session_id(input_data: dict[str, Any] | None = None) -> str:
    """Get current session ID from env var or stdin data."""
    sid = os.environ.get("CLAUDE_SESSION_ID")
    if sid:
        return sid
    if input_data:
        sid = input_data.get("sessionId") or input_data.get("session_id")
        if sid:
            return str(sid)
    return "unknown"


# Summarization is newest-first and capped (MAX_CONTEXT_FOR_CLOUD chars), so
# only the tail of a large session JSONL can ever reach the LLM. 4 MiB is ~40x
# the extraction cap — reading more just burns memory/latency at compact time.
_SESSION_TAIL_BYTES_DEFAULT = 4 * 1024 * 1024


def _session_tail_bytes() -> int:
    try:
        return int(
            os.environ.get("SMART_TRIM_SESSION_TAIL_BYTES", str(_SESSION_TAIL_BYTES_DEFAULT))
        )
    except ValueError:
        return _SESSION_TAIL_BYTES_DEFAULT


def read_session(session_file: Path) -> list[dict[str, Any]]:
    """Read session messages from JSONL, bounded to the newest tail.

    Skips blank/malformed lines. Files larger than the tail budget are read
    from the end (the partial first line is dropped); set
    ``SMART_TRIM_SESSION_TAIL_BYTES=0`` to force a full read.
    """
    try:
        size = session_file.stat().st_size
    except OSError:
        return []
    cap = _session_tail_bytes()
    try:
        with open(session_file, "rb") as f:
            if 0 < cap < size:
                f.seek(size - cap)
                f.readline()  # drop the partial line at the seek boundary
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
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
    "read_session",
    "extract_context_for_summary",
]
