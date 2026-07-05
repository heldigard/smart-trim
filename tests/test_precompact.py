"""Tests for features/precompact (orchestrator, late-binding monkeypatch).

handle_precompact reaches sibling features via MODULE attribute access
(_summarize.summarize_primary, not a direct import), so monkeypatch on the
origin module's function resolves at call time.
"""

from __future__ import annotations

import json
from pathlib import Path

from smart_trim.features.precompact import command as precompact

# Module paths for monkeypatch (late-binding targets).
_SESSION = "smart_trim.features.session.command"
_SUMMARIZE = "smart_trim.features.summarize.command"
_WRITER = "smart_trim.features.writer.command"
_OLLAMA = "smart_trim.shared.ollama"
_COMPAT = "smart_trim.shared.compat"


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


def test_injects_negative_constraints_into_grounding(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "Fix the parser. Do not edit generated files.")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: True)
    monkeypatch.setattr(f"{_SUMMARIZE}.summarize_secondary", lambda context, grounding="": None)

    seen: dict[str, str] = {}

    def primary(context, grounding=""):
        seen["grounding"] = grounding
        return "**Task**: Fix parser\n**Next**: Run tests"

    monkeypatch.setattr(f"{_SUMMARIZE}.summarize_primary", primary)
    monkeypatch.setattr(f"{_WRITER}.update_project_memory", lambda *a, **k: None)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "sess-neg", "cwd": str(project)})

    assert "Preserved Negative Constraints" in seen["grounding"]
    assert "Do not edit generated files" in seen["grounding"]


# --- payload cwd drives memory write (from original test suite) -------------


def test_uses_payload_cwd_for_memory_write(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_SESSION_FILE", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    _disable_external(monkeypatch)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    result = precompact.handle_precompact(
        {"trigger": "manual", "sessionId": "sess-1", "cwd": str(project)}
    )

    assert result == {"continue": True}
    active = project / ".memory-bank" / "activeContext.md"
    assert active.exists()
    assert "Session sess-1 compacted" in active.read_text(encoding="utf-8")
    assert not (home / ".memory-bank" / "activeContext.md").exists()


# --- method label propagation (from original test suite) -------------------


def test_primary_method_label(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "fix smart trim")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        f"{_SUMMARIZE}.summarize_primary", lambda context, grounding="": "primary summary"
    )
    monkeypatch.setattr(f"{_SUMMARIZE}.summarize_secondary", lambda context, grounding="": None)

    seen: dict[str, str] = {}

    def capture(summary, method, session_id="unknown", project_root=None):
        seen["method"] = method
        seen["project_root"] = str(project_root)

    monkeypatch.setattr(f"{_WRITER}.update_project_memory", capture)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    result = precompact.handle_precompact(
        {"trigger": "auto", "sessionId": "sess-2", "cwd": str(project)}
    )

    assert result["continue"] is True
    assert seen["method"] == "ollama-setneuf-qwopus3.5"
    assert seen["project_root"] == str(project)


# --- fallback + cloud + minimal paths ---------------------------------------


def test_falls_back_to_rule_based_when_all_llm_fail(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "edit /tmp/x.py error: boom failed")
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr(
        f"{_WRITER}.update_project_memory",
        lambda summary, method, session_id="unknown", project_root=None: seen.update(method=method),
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "s", "cwd": str(project)})
    assert seen["method"] == "fallback"


def test_cloud_tier_used_when_ollama_down(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "work")
    monkeypatch.setattr(f"{_COMPAT}.cg_reset", None)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: False)
    monkeypatch.setattr(
        f"{_SUMMARIZE}.summarize_cloud_cascade", lambda context, grounding="": "cloud handoff" * 10
    )
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr(
        f"{_WRITER}.update_project_memory",
        lambda summary, method, session_id="unknown", project_root=None: seen.update(method=method),
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "s", "cwd": str(project)})
    assert seen["method"] == "deepseek-cloud"


def test_minimal_handoff_when_no_session(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: None)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr(
        f"{_WRITER}.update_project_memory",
        lambda summary, method, session_id="unknown", project_root=None: seen.update(method=method),
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "sx", "cwd": str(project)})
    assert seen["method"] == "minimal"


# --- return shape -----------------------------------------------------------


def test_returns_continue_true_with_systemmessage_on_auto(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: None)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )
    monkeypatch.setattr(f"{_WRITER}.update_project_memory", lambda *a, **k: None)

    result = precompact.handle_precompact(
        {"trigger": "auto", "sessionId": "s", "cwd": str(project)}
    )
    assert result["continue"] is True
    assert "systemMessage" in result


def test_precompact_safe_reset_cg_exception(monkeypatch):
    def fake_cg_reset():
        raise RuntimeError("boom")

    monkeypatch.setattr(precompact._compat, "cg_reset", fake_cg_reset)
    # Should not raise exception
    precompact._safe_reset_cg()


def test_precompact_build_grounding_variations(tmp_path, monkeypatch):
    # Mock grounding load to return empty, and objective registry to return something
    monkeypatch.setattr(precompact._grounding, "load_memory_grounding", lambda r: "")
    monkeypatch.setattr(precompact._grounding, "load_objective_registry", lambda r: "obj-block")
    g, obj = precompact._build_grounding(tmp_path)
    assert g == "obj-block"
    assert obj == "obj-block"


def test_precompact_minimal_handoff_empty_messages(tmp_path, monkeypatch):
    session_file = tmp_path / "session.jsonl"
    session_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(precompact._session, "read_session", lambda f: [])
    monkeypatch.setattr(precompact._grounding, "extract_negative_constraints", lambda g: "")

    text, method, preserved = precompact._resolve_summary(
        session_file, grounding="", session_id="s", trigger="auto"
    )
    assert method == "minimal"


def test_precompact_secondary_ollama_success(tmp_path, monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        precompact._summarize, "summarize_primary", lambda context, grounding="": None
    )
    monkeypatch.setattr(
        precompact._summarize, "summarize_secondary", lambda context, grounding="": "secondary ok"
    )

    text, method = precompact._try_local("context", "grounding")
    assert text == "secondary ok"
    assert method == "ollama-qwen3.5:4b"


def test_precompact_archive_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    precompact._archive_summary("summary-text", "method-name", "auto", "session-id")

    archive_dir = tmp_path / ".claude" / "summaries"
    assert archive_dir.is_dir()
    files = list(archive_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "summary-text" in content
    assert "method-name" in content

    # Test exception handling (mkdir raises OSError)
    def fake_mkdir(self, *args, **kwargs):
        raise OSError("Permission denied")

    monkeypatch.setattr(Path, "mkdir", fake_mkdir)
    # Should not raise exception
    precompact._archive_summary("summary-text", "method-name", "auto", "session-id")


def test_precompact_returns_warning_on_auto(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: None)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    # Return a warning
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene",
        lambda *a, **k: "Hygiene warning",
    )
    monkeypatch.setattr(f"{_WRITER}.update_project_memory", lambda *a, **k: None)

    result = precompact.handle_precompact(
        {"trigger": "auto", "sessionId": "s", "cwd": str(project)}
    )
    assert result["continue"] is True
    assert "Hygiene warning" in result["systemMessage"]


def test_precompact_main_entry(monkeypatch, capsys):
    import io
    import sys

    import pytest

    # 1. Valid dict input
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"trigger":"manual","sessionId":"s"}'))
    monkeypatch.setattr(precompact, "handle_precompact", lambda data: {"continue": True})

    precompact.main()
    captured = capsys.readouterr()
    assert '{"continue": true}' in captured.out

    # 2. Non-dict input (should exit early silently)
    monkeypatch.setattr(sys, "stdin", io.StringIO("[]"))
    with pytest.raises(SystemExit) as e:
        precompact.main()
    assert e.value.code == 0

    # 3. Bad JSON (should exit early silently)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{bad json}"))
    with pytest.raises(SystemExit) as e:
        precompact.main()
    assert e.value.code == 0


def test_precompact_try_local_returns_none_none(monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        precompact._summarize, "summarize_primary", lambda context, grounding="": None
    )
    monkeypatch.setattr(
        precompact._summarize, "summarize_secondary", lambda context, grounding="": None
    )

    text, method = precompact._try_local("context", "grounding")
    assert text is None
    assert method is None


def test_precompact_augment_objective():
    summary = "some summary"
    obj = "objective block text"
    res = precompact._augment(summary, preserved="", objective_block=obj)
    assert res == f"{obj}\n\n{summary}"


def test_precompact_join_grounding():
    assert precompact._join_grounding("grounding", "") == "grounding"
    assert precompact._join_grounding("", "preserved") == "preserved"
    assert precompact._join_grounding("", "") == ""
    assert precompact._join_grounding("grounding", "preserved") == "grounding\n\npreserved"
