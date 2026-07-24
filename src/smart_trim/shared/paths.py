"""Path resolution + text redaction utilities (no feature deps).

``get_project_root`` resolves the project containing ``.memory-bank/`` (or the
git toplevel) without depending on shell aliases. ``redact_sensitive`` strips
likely secret-bearing lines before they reach agent memory or cloud.
``slugify`` produces filesystem-safe topic slugs. ``default_summaries_dir`` is
the canonical location for archived PreCompact summaries — shared between the
``hygiene`` (rotate / cap) and ``precompact`` (write) features so they can
never disagree on where the archive lives.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from smart_trim.shared.config import SECRET_KEYWORD_RE, SECRET_VALUE_RE


def _has_memory_bank(parent: Path) -> bool:
    try:
        return (parent / ".memory-bank").is_dir()
    except OSError:
        return False


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def _bank_ancestor(start: Path) -> Path | None:
    for parent in [start, *start.parents]:
        if _has_memory_bank(parent):
            return parent
        if parent == parent.parent:
            break
    return None


def get_project_root(start: str | Path | None = None) -> Path:
    """Resolve project root without depending on shell aliases."""
    try:
        cwd = Path(start or Path.cwd()).expanduser().resolve()
    except (OSError, ValueError):
        cwd = Path.cwd()
    if _has_memory_bank(cwd):
        return cwd
    top = _git_toplevel(cwd)
    if top is not None:
        return top
    return _bank_ancestor(cwd) or cwd


def redact_sensitive(text: str) -> str:
    """Redact likely secret-bearing spans before writing agent memory.

    Two-tier masking so a handoff keeps its context instead of losing whole
    lines (the old behavior nuked any line mentioning ``password``/``secret``
    as a word, which silently deleted LLM decisions like "rotate the api_key
    weekly"):

    1. High-confidence secret VALUES (prefixed tokens, PEM headers, JWTs) are
       masked at the matched span only — the surrounding sentence survives.
    2. Loose keyword LABELS (``api_key``/``password``/``secret``/...) are masked
       from the keyword to end-of-line. The regex matches the label, not the
       value, so masking to EOL is the conservative choice that still catches a
       prose-form secret ("the secret is hunter2") without leaking it.
    """
    cleaned: list[str] = []
    for line in text.splitlines():
        line = SECRET_VALUE_RE.sub("[REDACTED]", line)
        match = SECRET_KEYWORD_RE.search(line)
        if match:
            # Placeholder wording avoids every trigger keyword so a second
            # pass (the writer redacts again after the orchestrator already
            # did) is a no-op — redaction stays idempotent.
            line = f"{line[: match.start()]}[REDACTED: possible sensitive value]"
        cleaned.append(line)
    return "\n".join(cleaned)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.strip().lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-._")
    return slug or "session-handoffs"


def default_summaries_dir() -> Path:
    """Canonical archive directory for PreCompact summaries.

    Single source of truth — ``hygiene`` (rotate / cap) and ``precompact``
    (write) MUST agree on the location or the rotation invariant breaks.
    """
    return Path.home() / ".claude" / "summaries"


__all__ = ["default_summaries_dir", "get_project_root", "redact_sensitive", "slugify"]
