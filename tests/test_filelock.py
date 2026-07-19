"""Tests for the best-effort file lock (shared/feature; concurrency-critical).

The lock guards concurrent PreCompact appends to ``topics/session-handoffs.md``
and ``topics/_index.md``. Its retry loop, timeout, and error paths were
previously untested — a regression here could ship silently and corrupt the
memory bank under parallel compacts. ``fcntl`` is POSIX-only; the
``fcntl = None`` branch is exercised by monkeypatch.
"""

from __future__ import annotations

import fcntl as _real_fcntl
import time
from pathlib import Path

from smart_trim.shared import filelock


def _open_handle(path: Path):
    """Open a fresh write handle the lock can take ``fileno()`` from."""
    return path.open("a+", encoding="utf-8")


def test_try_lock_acquires_when_free(tmp_path):
    handle = _open_handle(tmp_path / "topic.md")
    try:
        with filelock.try_exclusive_lock(handle) as acquired:
            assert acquired is True
    finally:
        handle.close()


def test_try_lock_without_fcntl_yields_true(tmp_path):
    """Platforms without ``fcntl`` retain pre-lock best-effort behavior (yield True)."""
    handle = _open_handle(tmp_path / "topic.md")
    original = filelock.fcntl
    filelock.fcntl = None
    try:
        with filelock.try_exclusive_lock(handle) as acquired:
            assert acquired is True
    finally:
        filelock.fcntl = original
        handle.close()


def test_try_lock_retries_then_succeeds(tmp_path):
    """A transient ``BlockingIOError`` is retried; the lock succeeds on retry."""
    handle = _open_handle(tmp_path / "topic.md")
    calls = {"n": 0}

    def flaky_flock(_fd, _op):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BlockingIOError("held by another process")

    original = filelock.fcntl.flock
    filelock.fcntl.flock = flaky_flock  # type: ignore[method-assign]
    try:
        with filelock.try_exclusive_lock(handle, timeout_seconds=1.0) as acquired:
            assert acquired is True
        # 3 routed through the mock: 1 failed acquire + 1 retry acquire + 1 unlock.
        assert calls["n"] == 3
    finally:
        filelock.fcntl.flock = original  # type: ignore[method-assign]
        handle.close()


def test_try_lock_returns_false_on_timeout(tmp_path):
    """Persistent ``BlockingIOError`` past the deadline yields ``False`` (no wait forever)."""
    handle = _open_handle(tmp_path / "topic.md")

    def busy(_fd, _op):
        raise BlockingIOError("always held")

    original = filelock.fcntl.flock
    filelock.fcntl.flock = busy  # type: ignore[method-assign]
    try:
        start = time.monotonic()
        with filelock.try_exclusive_lock(handle, timeout_seconds=0.02) as acquired:
            assert acquired is False
        # Honored the deadline rather than blocking: well under the hook budget.
        assert time.monotonic() - start < 1.0
    finally:
        filelock.fcntl.flock = original  # type: ignore[method-assign]
        handle.close()


def test_try_lock_returns_false_on_oserror(tmp_path):
    """A non-blocking ``OSError`` (not ``BlockingIOError``) fails fast with ``False``."""
    handle = _open_handle(tmp_path / "topic.md")

    def bad(_fd, _op):
        raise OSError("bad file descriptor")

    original = filelock.fcntl.flock
    filelock.fcntl.flock = bad  # type: ignore[method-assign]
    try:
        with filelock.try_exclusive_lock(handle, timeout_seconds=1.0) as acquired:
            assert acquired is False
    finally:
        filelock.fcntl.flock = original  # type: ignore[method-assign]
        handle.close()


def test_try_lock_unlock_error_is_swallowed(tmp_path):
    """A failure to release (``LOCK_UN``) must not raise out of the context manager."""
    handle = _open_handle(tmp_path / "topic.md")

    def flock_unlock_fails(_fd, op):
        # LOCK_UN == 8 in the POSIX flag set used by fcntl.
        if op & _real_fcntl.LOCK_UN:
            raise OSError("cannot release")

    original = filelock.fcntl.flock
    filelock.fcntl.flock = flock_unlock_fails  # type: ignore[method-assign]
    try:
        # Acquire + exit the block: the failing unlock in ``finally`` is swallowed.
        with filelock.try_exclusive_lock(handle) as acquired:
            assert acquired is True
    finally:
        filelock.fcntl.flock = original  # type: ignore[method-assign]
        handle.close()


def test_try_lock_zero_timeout_returns_false_when_busy(tmp_path):
    """``timeout_seconds=0`` must not busy-loop; a busy lock yields ``False`` once."""
    handle = _open_handle(tmp_path / "topic.md")

    def busy(_fd, _op):
        raise BlockingIOError("held")

    original = filelock.fcntl.flock
    filelock.fcntl.flock = busy  # type: ignore[method-assign]
    try:
        with filelock.try_exclusive_lock(handle, timeout_seconds=0.0) as acquired:
            assert acquired is False
    finally:
        filelock.fcntl.flock = original  # type: ignore[method-assign]
        handle.close()
