"""home/foreign session + project/bank resolution."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from smart_trim.features.writer import command as writer


def test_foreign_session_true_when_paths_outside(tmp_path):
    assert writer._is_foreign_session("edit /elsewhere/x.py", tmp_path) is True


def test_foreign_session_false_when_path_inside(tmp_path):
    summary = f"edit {tmp_path}/x.py"
    assert writer._is_foreign_session(summary, tmp_path) is False


def test_foreign_session_false_when_no_paths(tmp_path):
    # Conceptual session, no file paths -> treated as host-local.
    assert writer._is_foreign_session("just thinking about the design", tmp_path) is False


# --- HOME meta bank: name/home guard (bug 2026-07-13) -----------------------
# A project session run from ~ pollutes the shared meta activeContext when its
# summary names the project without any absolute path. The HOME meta bank must
# route such sessions to the foreign topic.


def test_home_bank_foreign_when_names_known_project(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "_is_home_meta_bank", lambda root: True)
    monkeypatch.setattr(writer, "_known_project_names", lambda: {"elogix"})
    summary = "revisa los flujos de elogix-api y elogix-web: DeliveryOrder CRUD"
    assert writer._is_foreign_session(summary, tmp_path) is True


def test_home_bank_foreign_when_no_signal_no_project(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "_is_home_meta_bank", lambda root: True)
    monkeypatch.setattr(writer, "_known_project_names", lambda: set())
    assert writer._is_foreign_session("explain how async works", tmp_path) is True


def test_home_bank_not_foreign_when_meta_signal(monkeypatch, tmp_path):
    monkeypatch.setattr(writer, "_is_home_meta_bank", lambda root: True)
    monkeypatch.setattr(writer, "_known_project_names", lambda: {"elogix"})
    summary = "reviewed the smart-trim hook and the skill-router rule"
    assert writer._is_foreign_session(summary, tmp_path) is False


def test_home_bank_tilde_path_treated_as_inside():
    # A meta session editing ~/.claude/... must count as inside the HOME root,
    # not extract a misleading "/.claude/..." path that looks foreign.
    summary = "edited ~/.claude/hooks/smart-trim.py and ~/.codex/config.toml"
    assert writer._is_foreign_session(summary, Path.home()) is False


def test_home_bank_routes_named_project_to_foreign_topic(monkeypatch, tmp_path):
    project = tmp_path / "host"
    project.mkdir()
    monkeypatch.setattr(writer, "_is_home_meta_bank", lambda root: True)
    monkeypatch.setattr(writer, "_known_project_names", lambda: {"elogix"})
    summary = "audited elogix-api auth flow and elogix-web state progression"
    writer.update_agent_memory(summary, "fallback", "sess-elogix", project_root=project)
    foreign = project / ".memory-bank" / "topics" / "foreign-sessions.md"
    active = project / ".memory-bank" / "activeContext.md"
    assert foreign.exists()
    assert not active.exists()  # meta activeContext NOT clobbered


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


def test_is_home_meta_bank_oserror(monkeypatch):
    def fake_resolve(self):
        raise OSError("Simulated resolve error")

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    assert writer._is_home_meta_bank(Path("/dummy")) is False


def test_child_bank_name_oserror(monkeypatch, tmp_path):
    def fake_is_dir(self):
        raise OSError("Simulated is_dir error")

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    assert writer._child_bank_name(tmp_path) is None


def test_child_bank_name_not_dir(tmp_path):
    file_path = tmp_path / "some_file.txt"
    file_path.write_text("hello")
    assert writer._child_bank_name(file_path) is None


def test_known_project_names_oserror(monkeypatch, tmp_path):
    # Non-existent parent directory (covers line 171 continue)
    non_existent = tmp_path / "nonexistent_parent"
    monkeypatch.setattr(writer, "_PROJECT_PARENTS", (str(non_existent),))
    assert writer._known_project_names() == set()

    # Iterdir raises OSError (covers line 175 continue)
    monkeypatch.setattr(writer, "_PROJECT_PARENTS", (str(tmp_path),))

    def fake_iterdir(self):
        raise OSError("Simulated iterdir error")

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    assert writer._known_project_names() == set()


def test_known_project_names_valid(monkeypatch, tmp_path):
    project_dir = tmp_path / "my_project"
    project_dir.mkdir()
    (project_dir / ".memory-bank").mkdir()
    monkeypatch.setattr(writer, "_PROJECT_PARENTS", (str(tmp_path),))
    assert writer._known_project_names() == {"my_project"}


# --- update_agent_memory route return ----------------------------------------
