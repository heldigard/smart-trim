"""Archive rotation + hygiene warnings for ~/.claude/summaries/.

``cleanup_old_summaries`` enforces a "keep newest N" invariant (write-then-trim,
so the post-write state equals ``max_files`` rather than ``max_files + 1``).
``check_memory_hygiene`` surfaces a warning only when that rotation is clearly
not keeping up (count > max_files), avoiding a permanent inactionable nag.

The archive directory itself lives in ``shared.paths.default_summaries_dir`` so
the writer (``precompact``) and the rotator (``hygiene``) cannot disagree on
the location — drift here would silently break the rotation invariant.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from smart_trim.shared.paths import default_summaries_dir

_log = logging.getLogger("smart_trim.hygiene")


def cleanup_old_summaries(
    max_age_days: int = 30, max_files: int = 150, summary_dir: Path | None = None
) -> None:
    """Remove summaries older than max_age_days. Keep at most max_files.

    ``summary_dir`` is injectable for tests; production callers leave it None so
    the canonical archive directory is used.
    """
    summary_dir = summary_dir if summary_dir is not None else default_summaries_dir()
    try:
        if not summary_dir.is_dir():
            return
        cutoff = datetime.now().timestamp() - (max_age_days * 86400)
        removed = _remove_aged(summary_dir, cutoff)
        removed += _enforce_cap(summary_dir, max_files)
        if removed:
            _log.info("cleaned %d old summaries", removed)
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
    # If still too many, keep only the newest readable max_files. An entry
    # whose metadata cannot be read is retained, but must not prevent healthy
    # entries from being rotated.
    readable: list[tuple[float, Path]] = []
    for path in summary_dir.glob("*.md"):
        try:
            readable.append((path.stat().st_mtime, path))
        except OSError:
            continue
    remaining = [path for _, path in sorted(readable, key=lambda item: item[0], reverse=True)]
    removed = 0
    for f in remaining[max(0, max_files) :]:
        if _safe_unlink(f):
            removed += 1
    return removed


def _safe_unlink(f: Path) -> bool:
    try:
        f.unlink()
        return True
    except OSError:
        return False


def check_memory_hygiene(max_files: int = 150, summary_dir: Path | None = None) -> str | None:
    """Check if summaries directory is getting large."""
    summary_dir = summary_dir if summary_dir is not None else default_summaries_dir()
    try:
        if not summary_dir.exists():
            return None
        count = len(list(summary_dir.glob("*.md")))
        # cleanup_old_summaries already limits to max_files — only warn if that
        # cleanup is failing (previously >100 = permanent inactionable nag).
        if count <= max_files:
            return None
        return f"Note: {count} session summaries stored — cleanup_old_summaries is not keeping up."
    except Exception:
        return None


__all__ = ["check_memory_hygiene", "cleanup_old_summaries"]
