"""Tests for features/writer (write-side)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from smart_trim.features.writer import command as writer

# --- update_project_memory ---------------------------------------------------


def test_update_writes_active_context(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    writer.update_project_memory(
        "**Task**: fix bug\n**Next**: ship it", "fallback", "sess-1", project_root=project
    )
    active = project / ".memory-bank" / "activeContext.md"
    assert active.exists()
    content = active.read_text(encoding="utf-8")
    assert "fix bug" in content
    assert "fallback" in content


def test_update_appends_session_handoffs_topic(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    writer.update_project_memory("body here", "fallback", "sess-2", project_root=project)
    topic = project / ".memory-bank" / "topics" / "session-handoffs.md"
    assert topic.exists()
    assert "body here" in topic.read_text(encoding="utf-8")


def test_update_routes_foreign_session_to_foreign_topic(tmp_path):
    project = tmp_path / "host"
    project.mkdir()
    # Summary mentions only paths OUTSIDE project -> foreign.
    summary = "worked on /tmp/totally/elsewhere/src/app.py"
    writer.update_project_memory(summary, "fallback", "sess-3", project_root=project)
    foreign = project / ".memory-bank" / "topics" / "foreign-sessions.md"
    active = project / ".memory-bank" / "activeContext.md"
    assert foreign.exists()
    assert not active.exists()  # host activeContext NOT clobbered


def test_update_keeps_local_session_in_active(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    summary = f"worked on {project}/src/app.py"
    writer.update_project_memory(summary, "fallback", "sess-4", project_root=project)
    active = project / ".memory-bank" / "activeContext.md"
    assert active.exists()


def test_update_redacts_secrets(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    writer.update_project_memory(
        "api_key=sk-secretvalue123456 task", "fallback", "s", project_root=project
    )
    active = (project / ".memory-bank" / "activeContext.md").read_text(encoding="utf-8")
    assert "REDACTED" in active
    assert "sk-secretvalue123456" not in active


def test_update_never_raises_on_bad_root(tmp_path):
    # Read-only / non-creatable root -> best-effort, must not raise.
    writer.update_project_memory("x", "fallback", "s", project_root=Path("/nonexistent/readonly/x"))


# --- append_project_topic + index -------------------------------------------


def test_append_topic_creates_file_and_index(tmp_path):
    topics = tmp_path / "topics"
    topics.mkdir()
    writer.append_project_topic(tmp_path, "My Topic", "entry one")
    topic = topics / "my-topic.md"
    assert topic.exists()
    assert "My Topic" in topic.read_text(encoding="utf-8")
    assert "entry one" in topic.read_text(encoding="utf-8")
    idx = (topics / "_index.md").read_text(encoding="utf-8")
    assert "(my-topic.md)" in idx


def test_update_topic_index_dedups(tmp_path):
    topics = tmp_path / "topics"
    topics.mkdir()
    writer.update_topic_index(topics, "x", "X")
    writer.update_topic_index(topics, "x", "X")  # second call must NOT duplicate
    idx = (topics / "_index.md").read_text(encoding="utf-8")
    assert idx.count("(x.md)") == 1


# --- _is_foreign_session -----------------------------------------------------


def test_foreign_session_true_when_paths_outside(tmp_path):
    assert writer._is_foreign_session("edit /elsewhere/x.py", tmp_path) is True


def test_foreign_session_false_when_path_inside(tmp_path):
    summary = f"edit {tmp_path}/x.py"
    assert writer._is_foreign_session(summary, tmp_path) is False


def test_foreign_session_false_when_no_paths(tmp_path):
    # Conceptual session, no file paths -> treated as host-local.
    assert writer._is_foreign_session("just thinking about the design", tmp_path) is False


def test_write_active_limits_lines(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # Create a summary with 40 lines
    long_summary = "\n".join(f"line {i}" for i in range(40))
    writer.update_project_memory(long_summary, "fallback", "sess-1", project_root=project)
    active = project / ".memory-bank" / "activeContext.md"
    assert active.exists()
    content = active.read_text(encoding="utf-8")
    lines = content.splitlines()
    # The header has 2 lines + at most 26 summary lines = max 28 lines total
    assert len(lines) <= 28


def test_is_foreign_session_resolve_oserror(monkeypatch):
    class FakePath:
        def __init__(self, path_str):
            self.path_str = path_str

        def resolve(self):
            raise OSError("Access denied")

        def __str__(self):
            return self.path_str

    # Passing FakePath to _is_foreign_session should fall back to str(project_root) without raising
    # edit a path that is not under "/dummy"
    fake_root = cast(Path, FakePath("/dummy"))
    assert writer._is_foreign_session("edit /elsewhere/x.py", fake_root) is True
    assert writer._is_foreign_session("edit /dummy/x.py", fake_root) is False
