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


def test_cleanup_caps_readable_files_when_one_stat_fails(tmp_path, monkeypatch):
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    unreadable = summaries / "unreadable.md"
    _touch(unreadable)
    readable = [summaries / f"s{i}.md" for i in range(4)]
    for path in readable:
        _touch(path)
    original_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if self == unreadable:
            raise OSError("permission denied")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)

    hygiene.cleanup_old_summaries(max_age_days=30, max_files=2, summary_dir=summaries)

    assert unreadable in list(summaries.iterdir())
    assert sum(path.exists() for path in readable) == 2


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


def test_default_summary_dir_via_mock(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    # This will check tmp_path / ".claude" / "summaries"
    # Create it so it exists
    expected_dir = tmp_path / ".claude" / "summaries"
    expected_dir.mkdir(parents=True)
    _touch(expected_dir / "test.md")

    # cleanup_old_summaries and check_memory_hygiene with summary_dir=None
    hygiene.cleanup_old_summaries(max_files=10, summary_dir=None)
    assert hygiene.check_memory_hygiene(max_files=150, summary_dir=None) is None


def test_cleanup_old_summaries_exception(monkeypatch):
    def fake_is_dir(*args, **kwargs):
        raise RuntimeError("failed to read dir")

    # We mock is_dir of Path
    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    # Should catch exception and return None
    hygiene.cleanup_old_summaries(summary_dir=Path("/dummy"))


def test_unlink_if_aged_stat_oserror(monkeypatch, tmp_path):
    # Mock f.stat to raise OSError
    summaries = tmp_path / "summaries"
    summaries.mkdir()
    f = summaries / "test.md"
    _touch(f)

    def fake_stat(*args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "stat", fake_stat)
    assert not hygiene._unlink_if_aged(f, 0.0)


def test_safe_unlink_oserror(monkeypatch, tmp_path):
    f = tmp_path / "test.md"
    _touch(f)

    def fake_unlink(*args, **kwargs):
        raise OSError("Read-only file system")

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    assert not hygiene._safe_unlink(f)


def test_check_memory_hygiene_exception(monkeypatch):
    # Mock exists to raise exception
    def fake_exists(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(Path, "exists", fake_exists)
    assert hygiene.check_memory_hygiene(summary_dir=Path("/dummy")) is None
