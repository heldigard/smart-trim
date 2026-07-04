"""Ollama liveness check.

``is_ollama_alive`` is a quick TCP probe cached per invocation (a single compact
calls it once; the cache avoids repeated 0.5s timeouts when the daemon is down).
"""

from __future__ import annotations

import socket

from smart_trim.shared.config import OLLAMA_HOST, OLLAMA_LIVENESS_TIMEOUT, OLLAMA_PORT

# Per-invocation liveness cache. Cleared only by process restart, which for a
# hook is every compact — exactly the granularity we want.
_OLLAMA_ALIVE: bool | None = None


def is_ollama_alive() -> bool:
    """Quick TCP check if Ollama is listening. Cached per invocation."""
    global _OLLAMA_ALIVE
    if _OLLAMA_ALIVE is not None:
        return _OLLAMA_ALIVE
    try:
        sock = socket.create_connection((OLLAMA_HOST, OLLAMA_PORT), timeout=OLLAMA_LIVENESS_TIMEOUT)
        sock.close()
        _OLLAMA_ALIVE = True
    except OSError:
        _OLLAMA_ALIVE = False
    return _OLLAMA_ALIVE


__all__ = ["is_ollama_alive"]
