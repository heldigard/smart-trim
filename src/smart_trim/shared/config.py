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
    MAX_CONTEXT_FOR_SUMMARY = int(os.environ.get("SMART_TRIM_MAX_CONTEXT_LOCAL", "50000"))
except ValueError:
    MAX_CONTEXT_FOR_SUMMARY = 50000

try:
    MAX_CONTEXT_FOR_CLOUD = int(os.environ.get("SMART_TRIM_MAX_CONTEXT_CLOUD", "100000"))
except ValueError:
    MAX_CONTEXT_FOR_CLOUD = 100000
# Cloud tier gets a larger cap than local's 50K — preserves early decisions
# / root-causes in long sessions approaching compact. Local 50K (~12-17K
# tokens) is paired with num_ctx=65536 (see summarize): gemma4-e2b (4.6B,
# 3.4GB) holds it in the RTX 5080's 16GB. Was 20K, which left num_ctx mostly
# unused; the cap is the real input bottleneck, not the model window.
MAX_FALLBACK_SUMMARY = 3000  # Max chars for rule-based fallback

# --- Cascade wall-clock budget ------------------------------------------------
# Hard ceiling on the LLM cascade (local primary -> secondary -> cloud) so a
# hung model can never exceed the PreCompact hook timeout and lose the ENTIRE
# handoff (the cascade runs before any write, so a timeout-kill means nothing
# is persisted). Each tier's per-call timeout shrinks with the remaining
# budget; once it is exhausted the cascade fails OPEN to rule-based fallback.
# Must stay below the host's PreCompact hook timeout; env-tunable.
try:
    CASCADE_BUDGET_SECONDS = float(os.environ.get("SMART_TRIM_CASCADE_BUDGET_SECONDS", "40"))
except ValueError:
    CASCADE_BUDGET_SECONDS = 40.0
# Don't start a tier with less than this left — it would just fail and waste a
# round-trip. Kept above the local generation floor so healthy summaries on a
# warm model still complete.
CASCADE_MIN_TIER_SECONDS = 3.0


# --- Redaction / constraint patterns ---------------------------------------
# Two-tier so a handoff keeps its context instead of losing whole lines.
# `redact_sensitive` (paths.py) masks VALUE spans in place and masks from a
# KEYWORD to end-of-line. Kept as separate compiled patterns (not one
# alternation) so the redactor can treat the two tiers differently.
#
# High-confidence secret VALUES (prefixed tokens, PEM headers, JWTs): the regex
# matches the secret material itself, so masking just the span removes the
# secret while preserving the surrounding sentence.
SECRET_VALUE_RE = re.compile(
    r"("
    r"BEGIN [A-Z ]*PRIVATE KEY|sk-[A-Za-z0-9_-]{20,}|"
    r"gh[pousr]_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,}|glpat-[A-Za-z0-9_-]{20,}|"
    r"AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|npm_[A-Za-z0-9]{36}|"
    r"AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]{10,}\.eyJ"
    r")",
    re.IGNORECASE,
)

# Loose keyword LABELS (api_key, password, secret, ...): the regex matches the
# label, not the value, so the redactor masks from the keyword to end-of-line.
# This still catches prose-form secrets ("the secret is hunter2") while keeping
# the context before the keyword ("Decisions: rotate the" survives a line that
# once read "Decisions: rotate the api_key weekly").
SECRET_KEYWORD_RE = re.compile(
    r"(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|private[_-]?key)",
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
