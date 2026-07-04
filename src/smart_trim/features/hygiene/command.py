"""Archive rotation + hygiene warnings for ~/.claude/summaries/.

``cleanup_old_summaries`` enforces a "keep newest N" invariant (write-then-trim,
so the post-write state equals ``max_files`` rather than ``max_files + 1``).
``check_memory_hygiene`` surfaces a warning only when that rotation is clearly
not keeping up (count > max_files), avoiding a permanent inactionable nag.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def _default_summary_dir() -> Path:
    return Path.home() / ".claude" / "summaries"


def cleanup_old_summaries(
    max_age_days: int = 30, max_files: int = 150, summary_dir: Path | None = None
) -> None:
    """Remove summaries older than max_age_days. Keep at most max_files.

    ``summary_dir`` is injectable for tests; production callers leave it None so
    the real ``~/.claude/summaries`` is used.
    """
    summary_dir = summary_dir if summary_dir is not None else _default_summary_dir()
    try:
        if not summary_dir.is_dir():
            return
        cutoff = datetime.now().timestamp() - (max_age_days * 86400)
        removed = _remove_aged(summary_dir, cutoff)
        removed += _enforce_cap(summary_dir, max_files)
        if removed:
            # Log to stderr for debug visibility
            print(f"[smart-trim] cleaned {removed} old summaries", file=sys.stderr)
    except Exception:
        pass


def _remove_aged(summary_dir: Path, cutoff: float) -> int:
    removed = 0
    for f in summary_dir.glob("*.md"):
        if _unlink_if_aged(f, cutoff):
            removed += 1
    return removed


def _unlink_if_aged(f: Path, cutoff: float) -> bool:
    try:
        if f.stat().st_mtime < cutoff:
            return _safe_unlink(f)
    except OSError:
        pass
    return False


def _enforce_cap(summary_dir: Path, max_files: int) -> int:
    # If still too many, keep only the newest max_files
    remaining = sorted(
        summary_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    removed = 0
    for f in remaining[max_files:]:
        if _safe_unlink(f):
            removed += 1
    return removed


def _safe_unlink(f: Path) -> bool:
    try:
        f.unlink()
        return True
    except OSError:
        return False


def check_memory_hygiene(max_files: int = 150, summary_dir: Path | None = None) -> Optional[str]:
    """Check if summaries directory is getting large."""
    summary_dir = summary_dir if summary_dir is not None else _default_summary_dir()
    try:
        if not summary_dir.exists():
            return None
        count = len(list(summary_dir.glob("*.md")))
        # cleanup_old_summaries already limits to max_files — only warn if that
        # cleanup is failing (previously >100 = permanent inactionable nag).
        if count <= max_files:
            return None
        return (
            f"Note: {count} session summaries stored — "
            "cleanup_old_summaries is not keeping up."
        )
    except Exception:
        return None


__all__ = ["cleanup_old_summaries", "check_memory_hygiene"]
