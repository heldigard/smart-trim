"""Path resolution + text redaction utilities (no feature deps).

``get_project_root`` resolves the project containing ``.memory-bank/`` (or the
git toplevel) without depending on shell aliases. ``redact_sensitive`` strips
likely secret-bearing lines before they reach project memory or cloud.
``slugify`` produces filesystem-safe topic slugs.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from smart_trim.shared.config import SECRET_RE


def _has_memory_bank(parent: Path) -> bool:
    try:
        return (parent / ".memory-bank").is_dir()
    except OSError:
        return False


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def _bank_ancestor(start: Path) -> Path | None:
    for parent in [start, *start.parents]:
        if _has_memory_bank(parent):
            return parent
        if parent == parent.parent:
            break
    return None


def get_project_root(start: str | Path | None = None) -> Path:
    """Resolve project root without depending on shell aliases."""
    try:
        cwd = Path(start or Path.cwd()).expanduser().resolve()
    except (OSError, ValueError):
        cwd = Path.cwd()
    if _has_memory_bank(cwd):
        return cwd
    top = _git_toplevel(cwd)
    if top is not None:
        return top
    return _bank_ancestor(cwd) or cwd


def redact_sensitive(text: str) -> str:
    """Redact likely secret-bearing lines before writing project memory."""
    clean_lines = []
    for line in text.splitlines():
        if SECRET_RE.search(line):
            clean_lines.append("[REDACTED: possible secret-bearing line]")
        else:
            clean_lines.append(line)
    return "\n".join(clean_lines)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    return slug or "session-handoffs"


__all__ = ["get_project_root", "redact_sensitive", "slugify"]
