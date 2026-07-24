"""Best-effort file locking for latency-sensitive hooks."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import IO

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows has no fcntl
    fcntl = None  # type: ignore[assignment]


@contextmanager
def try_exclusive_lock(handle: IO[str], *, timeout_seconds: float = 0.0) -> Iterator[bool]:
    """Acquire an exclusive lock without ever waiting.

    POSIX callers skip the optional write when another process owns the lock.
    Platforms without ``fcntl`` retain the pre-lock best-effort behavior rather
    than failing during hook import.
    """
    if fcntl is None:
        yield True
        return

    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                yield False
                return
            time.sleep(min(0.005, remaining))
        except OSError:
            yield False
            return

    try:
        yield True
    finally:
        with suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
