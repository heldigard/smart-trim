"""Tests for features/hygiene."""
from __future__ import annotations

import os
import time
from pathlib import Path

from smart_trim.features.hygiene import command as hygiene


def _touch(path: Path, age_days: float = 0) -> None:
    path.write_text("summary", encoding="utf-8")
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(path, (old, old))


def test_cleanup_removes_aged_files(tmp_path):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    _touch(summaries / "old.md", age_days=60)
    _touch(summaries / "new.md", age_days=0)

    hygiene.cleanup_old_summaries(max_age_days=30, summary_dir=summaries)

    assert not (summaries / "old.md").exists()
    assert (summaries / "new.md").exists()


def test_cleanup_enforces_max_files(tmp_path):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    for i in range(5):
        _touch(summaries / f"s{i}.md", age_days=0)

    hygiene.cleanup_old_summaries(max_age_days=30, max_files=2, summary_dir=summaries)

    remaining = list(summaries.glob("*.md"))
    assert len(remaining) == 2  # newest 2 kept


def test_cleanup_noop_when_dir_missing(tmp_path):
    # No summaries dir -> returns silently.
    hygiene.cleanup_old_summaries(summary_dir=tmp_path / "nope")  # must not raise


def test_check_hygiene_warns_when_over_limit(tmp_path):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    for i in range(5):
        _touch(summaries / f"s{i}.md")

    warning = hygiene.check_memory_hygiene(max_files=3, summary_dir=summaries)
    assert warning is not None
    assert "session summaries" in warning


def test_check_hygiene_silent_under_limit(tmp_path):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    for i in range(2):
        _touch(summaries / f"s{i}.md")

    assert hygiene.check_memory_hygiene(max_files=150, summary_dir=summaries) is None


def test_check_hygiene_none_when_dir_missing(tmp_path):
    assert hygiene.check_memory_hygiene(summary_dir=tmp_path / "nope") is None
