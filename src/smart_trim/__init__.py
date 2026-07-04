"""smart-trim — LLM-powered PreCompact context-compression hook.

Importing this package runs ``shared.compat`` once, which extends ``sys.path``
for the harness helpers (``ollama_client`` / ``cheap_complete`` /
``context_guard_lib`` in ``~/.claude/{scripts,hooks}/``) and binds them
gracefully. Every feature module can then ``from smart_trim.shared.compat
import ollama_client`` and get either the real module or ``None``.
"""
from __future__ import annotations

# Side effect: sys.path bootstrap + graceful helper imports. MUST run before any
# feature imports its LLM client. Imported for its side effects, not its names.
from smart_trim.shared import compat  # noqa: F401

__version__ = "3.3.0"

__all__ = ["__version__"]
