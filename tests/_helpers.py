"""Shared precompact test helpers + monkeypatch-path constants (extracted monolith)."""

from __future__ import annotations

import json
from pathlib import Path

from smart_trim.features.precompact import command as precompact


def _seed_session(tmp_path: Path, user_content: str = "fix the parser") -> Path:
    """Write a minimal session JSONL the orchestrator can read."""
    session_file = tmp_path / "session.jsonl"
    session_file.write_text(
        json.dumps({"message": {"role": "user", "content": user_content}}) + "\n",
        encoding="utf-8",
    )
    return session_file


def _disable_external(monkeypatch):
    """Stop the hook from touching real Ollama / context-guard / cloud."""
    monkeypatch.setattr(f"{_COMPAT}.cg_reset", None)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: False)
    monkeypatch.setattr(f"{_SUMMARIZE}.summarize_cloud_cascade", lambda *a, **k: None)


# --- negative-constraint injection (from original test suite) ----------------


def _routed_precompact(tmp_path, monkeypatch, route):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "edit /tmp/x.py")
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )
    monkeypatch.setattr(f"{_WRITER}.update_agent_memory", lambda *a, **k: route)
    return precompact.handle_precompact({"trigger": "auto", "sessionId": "s", "cwd": str(project)})


_SESSION = "smart_trim.features.session.command"


_SUMMARIZE = "smart_trim.features.summarize.command"


_WRITER = "smart_trim.features.writer.command"


_OLLAMA = "smart_trim.shared.ollama"


_COMPAT = "smart_trim.shared.compat"
