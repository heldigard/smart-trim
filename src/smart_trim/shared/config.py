"""Configuration constants and compiled regexes for smart-trim.

Single source of truth for tunables shared across features. No runtime side
effects, no imports beyond stdlib — safe to import from anywhere.
"""

from __future__ import annotations

import os
import re

# --- Ollama endpoint -------------------------------------------------------
OLLAMA_BASE = "http://localhost:11434"
OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
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

# than local's 20K cap — preserves early decisions
# / root-causes in long sessions approaching compact.
MAX_FALLBACK_SUMMARY = 3000  # Max chars for rule-based fallback


# --- Redaction / constraint patterns ---------------------------------------
SECRET_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|"
    r"private[_-]?key|BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9_-]{20,})",
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
