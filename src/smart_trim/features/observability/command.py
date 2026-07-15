"""Compression observability — bounded, gated append-only event record.

Writes one JSON line per compact to ``.memory-bank/topics/compact-events.md``
so the controller can mine real-world cascade behavior (method × latency ×
route) without leaking any prompt/response content. Gated by
``SMART_TRIM_OBSERVABILITY=1`` (default OFF: writing per-event costs a
``fsync`` per compact and the topic would grow quickly for heavy users).
Tests force the gate ON.

What is recorded (no PII / no content):
  - timestamp (UTC ISO second precision)
  - method (``ollama-<bare>`` | ``deepseek-cloud`` | ``cloud-<bare>`` | ``fallback`` | ``minimal``)
  - route (``active`` | ``foreign`` | ``error``)
  - trigger (``manual`` | ``auto`` | ``unknown``)
  - input_bytes / output_bytes (counts only)
  - latency_ms (wall-clock from handle_precompact entry to archive end)
  - model_chain (ordered tier labels that were attempted, including skips)
  - session_hash (sha256[:12] of session id; reversible by no one)

What is NOT recorded: prompt content, response content, file paths, error
strings, cwd. Reversing the session hash requires brute-forcing a 48-bit space
AND knowing the session id format — not worth it for an event channel that
already gates on opt-in.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

_log = logging.getLogger("smart_trim.observability")


@dataclass(frozen=True)
class CompactEvent:
    """One compaction event. Bundling fields keeps the recorder's signature small.

    Field defaults are present so a caller can omit zero-valued counters; the
    recorder enforces non-negative ints regardless of what the caller supplies.
    """

    method: str
    route: str
    trigger: str
    latency_ms: int = 0
    input_bytes: int = 0
    output_bytes: int = 0
    model_chain: tuple[str, ...] = field(default_factory=tuple)
    session_id: str = "unknown"


# Default OFF. Test fixtures flip this on via monkeypatch.setenv.
_DEFAULT_ENABLED = False
_TOPIC_SLUG = "compact-events"
_REDACTED = "[REDACTED]"


def observability_enabled() -> bool:
    """Read the gate at call time (matches the project's late-binding pattern)."""
    raw = os.environ.get("SMART_TRIM_OBSERVABILITY", "0")
    return raw == "1"


def session_hash(session_id: str) -> str:
    """Return a non-reversible 12-char fingerprint of the session id.

    SHA-256 truncated to 48 bits is sufficient to spot a single session
    re-appearing in the topic (collision probability across 10k events ≈ 0.3%
    — the topic is per-project and rarely exceeds that scale) without making
    the id recoverable.
    """
    digest = hashlib.sha256(str(session_id).encode("utf-8", errors="replace")).hexdigest()
    return digest[:12]


def record_compact_event(project_root: Path, event: CompactEvent) -> bool:
    """Append one JSON-line event to ``topics/compact-events.md``.

    Returns True on write, False when the gate is off OR the write fails.
    Failures are logged at debug level only — observability must never block
    compaction.
    """
    if not observability_enabled():
        return False
    try:
        topic_path = _ensure_topic(project_root)
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": _safe_label(event.method),
            "route": _safe_label(event.route),
            "trigger": _safe_label(event.trigger),
            "latency_ms": max(0, int(event.latency_ms)),
            "in": max(0, int(event.input_bytes)),
            "out": max(0, int(event.output_bytes)),
            "chain": [_safe_label(m) for m in event.model_chain if m],
            "sid": session_hash(event.session_id),
        }
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with topic_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        return True
    except Exception as exc:
        _log.debug("compact event append failed: %r", exc)
        return False


def _safe_label(value: object) -> str:
    """Coerce a label to a short, file-safe string with no PII leakage."""
    text = str(value) if value is not None else ""
    text = text.strip()
    if not text:
        return _REDACTED
    # 64 chars is plenty for a method/route/trigger label and bounds the topic
    # size even if a caller passes an unstripped model string.
    return text[:64]


def _ensure_topic(project_root: Path) -> Path:
    """Create the topic file + register it in ``topics/_index.md`` on first write."""
    memory_dir = project_root / ".memory-bank"
    topics_dir = memory_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    topic = topics_dir / f"{_TOPIC_SLUG}.md"
    if not topic.exists():
        topic.write_text(
            "# Compact events\n"
            "> Append-only JSON-line event log for PreCompact observability.\n"
            "> Fields: ts, method, route, trigger, latency_ms, in, out, chain, sid.\n"
            "> Enable with `SMART_TRIM_OBSERVABILITY=1` (default off).\n",
            encoding="utf-8",
        )
        _register_topic(topics_dir, _TOPIC_SLUG, "Compact events")
    return topic


def _register_topic(topics_dir: Path, slug: str, title: str) -> None:
    """Mirror ``writer.update_topic_index`` so the topic shows up in search."""
    index = topics_dir / "_index.md"
    try:
        if not index.exists():
            index.write_text(
                "# Topic Index\n"
                "> Deep agent memory. Search/read on demand; do not load all topics by default.\n\n"
                "## Topics\n",
                encoding="utf-8",
            )
        content = index.read_text(encoding="utf-8", errors="replace")
        if f"({slug}.md)" not in content:
            with index.open("a", encoding="utf-8") as handle:
                handle.write(f"- [{title}]({slug}.md)\n")
    except Exception:
        # Index updates are best-effort; event append must still work.
        pass


__all__ = [
    "observability_enabled",
    "record_compact_event",
    "session_hash",
]
