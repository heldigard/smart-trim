"""Configuration constants and compiled regexes for smart-trim.

Single source of truth for tunables shared across features. No runtime side
effects, no imports beyond stdlib — safe to import from anywhere.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

# --- Ollama endpoint -------------------------------------------------------
_DEFAULT_OLLAMA_BASE = "http://localhost:11434"


def _resolve_ollama_base() -> str:
    """Endpoint override: ``SMART_TRIM_OLLAMA_BASE`` first, then the standard
    ``OLLAMA_HOST`` (bare ``host:port`` accepted). Invalid values fall back to
    the localhost default so a typo can never disable the local cascade AND
    the liveness probe simultaneously in inconsistent ways."""
    raw = (
        (os.environ.get("SMART_TRIM_OLLAMA_BASE") or os.environ.get("OLLAMA_HOST") or "")
        .strip()
        .rstrip("/")
    )
    if not raw:
        return _DEFAULT_OLLAMA_BASE
    if "://" not in raw:
        raw = f"http://{raw}"
    try:
        parsed = urlparse(raw)
        if not parsed.hostname:
            return _DEFAULT_OLLAMA_BASE
        parsed.port  # noqa: B018 — raises ValueError on a malformed port
    except ValueError:
        return _DEFAULT_OLLAMA_BASE
    return raw


OLLAMA_BASE = _resolve_ollama_base()
_PARSED_BASE = urlparse(OLLAMA_BASE)
OLLAMA_HOST = _PARSED_BASE.hostname or "localhost"
OLLAMA_PORT = _PARSED_BASE.port or (443 if _PARSED_BASE.scheme == "https" else 11434)
OLLAMA_TIMEOUT_SECONDS = 45.0
OLLAMA_LIVENESS_TIMEOUT = 0.5

# --- Context caps ----------------------------------------------------------
try:
    MAX_CONTEXT_FOR_SUMMARY = int(os.environ.get("SMART_TRIM_MAX_CONTEXT_LOCAL", "20000"))
except ValueError:
    MAX_CONTEXT_FOR_SUMMARY = 20000

try:
    MAX_CONTEXT_FOR_CLOUD = int(os.environ.get("SMART_TRIM_MAX_CONTEXT_CLOUD", "100000"))
except ValueError:
    MAX_CONTEXT_FOR_CLOUD = 100000
# Cloud tier gets a larger cap than local's 20K — preserves early decisions
# / root-causes in long sessions approaching compact.
MAX_FALLBACK_SUMMARY = 3000  # Max chars for rule-based fallback


# --- Redaction / constraint patterns ---------------------------------------
SECRET_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|"
    r"private[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9_-]{20,}|"
    # High-confidence token prefixes (GitHub, GitLab, AWS, Slack, npm, Google, JWT).
    r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|glpat-[A-Za-z0-9_-]{20,}|"
    r"AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|npm_[A-Za-z0-9]{36}|"
    r"AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]{10,}\.eyJ)",
    re.IGNORECASE,
)

NEGATIVE_CONSTRAINT_RE = re.compile(
    r"\b("
    r"do\s+not|don't|dont|never|must\s+not|avoid|without\s+(?:editing|modifying|changing|reading)|"
    r"no\s+(?:edites|editar|modifiques|modificar|leas|leer|cambies|cambiar|uses|usar)|"
    r"nunca|jam[aá]s|evita|sin\s+(?:editar|modificar|cambiar|leer)|"
    r"bloquead[oa]|blocked|forbidden|prohibid[oa]"
    r")\b",
    re.IGNORECASE,
)
