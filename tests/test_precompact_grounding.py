"""archive summary + grounding injection."""

from __future__ import annotations

from pathlib import Path

from _helpers import (  # noqa: F401
    _COMPAT,
    _OLLAMA,
    _SESSION,
    _SUMMARIZE,
    _WRITER,
    _disable_external,
    _routed_precompact,
    _seed_session,
)

from smart_trim.features.precompact import command as precompact


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


def test_archive_summary_sanitizes_session_id_and_avoids_rapid_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    precompact._archive_summary("first", "fallback", "auto", "../escaped")
    precompact._archive_summary("second", "fallback", "auto", "../escaped")

    archive_dir = tmp_path / ".claude" / "summaries"
    files = sorted(archive_dir.glob("*.md"))
    assert len(files) == 2
    assert all(path.parent == archive_dir for path in files)
    assert not list((tmp_path / ".claude").glob("escaped*"))
    contents = {path.read_text(encoding="utf-8") for path in files}
    assert any("first" in value for value in contents)
    assert any("second" in value for value in contents)


def test_precompact_augment_objective():
    summary = "some summary"
    obj = "objective block text"
    res = precompact._augment(summary, preserved="", objective_block=obj)
    assert res == f"{obj}\n\n{summary}"


def test_precompact_build_grounding_variations(tmp_path, monkeypatch):
    # Mock grounding load to return empty, and objective registry to return something
    monkeypatch.setattr(precompact._grounding, "load_memory_grounding", lambda r: "")
    monkeypatch.setattr(precompact._grounding, "load_objective_registry", lambda r: "obj-block")
    g, obj = precompact._build_grounding(tmp_path)
    assert g == "obj-block"
    assert obj == "obj-block"


def test_precompact_join_grounding():
    assert precompact._join_grounding("grounding", "") == "grounding"
    assert precompact._join_grounding("", "preserved") == "preserved"
    assert precompact._join_grounding("", "") == ""
    assert precompact._join_grounding("grounding", "preserved") == "grounding\n\npreserved"


def test_injects_negative_constraints_into_grounding(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "Fix the parser. Do not edit generated files.")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        f"{_SUMMARIZE}.summarize_secondary", lambda context, grounding="", **_kw: None
    )

    seen: dict[str, str] = {}

    def primary(context, grounding="", **kwargs):
        seen["grounding"] = grounding
        return "**Task**: Fix parser\n**Next**: Run tests"

    monkeypatch.setattr(f"{_SUMMARIZE}.summarize_primary", primary)
    monkeypatch.setattr(f"{_WRITER}.update_agent_memory", lambda *a, **k: None)
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


def test_precompact_does_not_persist_postcompact_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    active_path = project / ".memory-bank" / "activeContext.md"
    active_path.write_text("# Active Context\n- keep me\n", encoding="utf-8")
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: None)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "sx", "cwd": str(project)})

    active = active_path.read_text(encoding="utf-8")
    topic_path = project / ".memory-bank" / "topics" / "session-handoffs.md"
    assert "POST-COMPACT RULES" not in active
    assert "DO NOT re-read files" not in active
    assert active == "# Active Context\n- keep me\n"
    assert not topic_path.exists()


# --- return shape -----------------------------------------------------------


def test_precompact_minimal_handoff_empty_messages(tmp_path, monkeypatch):
    session_file = tmp_path / "session.jsonl"
    session_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(precompact._session, "read_session", lambda f: [])
    monkeypatch.setattr(precompact._grounding, "extract_negative_constraints", lambda g: "")

    text, method, preserved, chain = precompact._resolve_summary(
        session_file, grounding="", session_id="s", trigger="auto"
    )
    assert method == "minimal"
