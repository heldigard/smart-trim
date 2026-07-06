"""Tests for features/grounding (read-side)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from smart_trim.features.grounding import command as grounding

# --- load_memory_grounding ---------------------------------------------------


def test_load_grounding_empty_when_no_bank(tmp_path):
    assert grounding.load_memory_grounding(tmp_path) == ""


def test_load_grounding_reads_current_task(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: None)
    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    (bank / "currentTask.md").write_text("# Task\nfix the parser", encoding="utf-8")

    out = grounding.load_memory_grounding(tmp_path)
    assert "Current Task" in out
    assert "fix the parser" in out


def test_load_grounding_filters_stale_active_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMORY_INJECTION_ACTIVE_WINDOW_HOURS", "12")
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: None)

    class _StubHelper:
        def filter_lines_for_injection(self, name, lines):
            # Simulate the real helper dropping status:active lines older than the window.
            return [ln for ln in lines if "stale" not in ln]

    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    (bank / "currentTask.md").write_text(
        "- 2020-01-01T00:00:00Z | status:active | stale task\n"
        "- 2026-01-01T00:00:00Z | status:live | live task\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: _StubHelper())

    out = grounding.load_memory_grounding(tmp_path)
    assert "stale task" not in out
    assert "live task" in out


def test_load_grounding_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: None)
    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    (bank / "currentTask.md").write_text("api_key=ABCDEF123456 here", encoding="utf-8")

    out = grounding.load_memory_grounding(tmp_path)
    assert "REDACTED" in out
    assert "ABCDEF123456" not in out


# --- extract_negative_constraints -------------------------------------------


def test_negative_constraints_detects_prohibitions():
    text = "Normal detail.\nNever read .env files.\nNo edites archivos fuera de src/."
    block = grounding.extract_negative_constraints(text)
    assert "Preserved Negative Constraints" in block
    assert "Never read .env files" in block
    assert "No edites archivos fuera de src/" in block


def test_negative_constraints_returns_empty_when_none():
    assert grounding.extract_negative_constraints("just a normal plan") == ""


def test_negative_constraints_caps_items():
    text = "\n".join(f"never do thing {i}" for i in range(20))
    block = grounding.extract_negative_constraints(text, max_items=3)
    assert block.count("\n- ") == 3


def test_negative_constraints_redacts_secret_in_constraint():
    block = grounding.extract_negative_constraints("never leak api_key=sk-secretvalue123")
    assert "REDACTED" in block or "sk-secretvalue123" not in block


def test_negative_constraints_ignores_worker_and_postcompact_noise():
    text = "\n".join(
        [
            "- [FUSION_PANEL][NO_DELEGATE][NO_TOOLS] You are a deliberation panelist.",
            "- Do NOT use tools, APIs, or further delegation.",
            "- 1. DO NOT re-read files you already know from this summary",
            "- 2. DO NOT read screenshots/images into context",
            "- 4. DO NOT re-read rules files - they are already loaded",
            "- Never read .env files.",
        ]
    )
    block = grounding.extract_negative_constraints(text)
    assert "Never read .env files" in block
    assert "FUSION_PANEL" not in block
    assert "NO_DELEGATE" not in block
    assert "DO NOT re-read" not in block
    assert "screenshots/images" not in block


# --- load_objective_registry -------------------------------------------------


def _write_objective(home: Path, data: dict) -> None:
    state = home / ".claude" / "state"
    state.mkdir(parents=True)
    (state / "current-objective.json").write_text(json.dumps(data), encoding="utf-8")


def test_objective_registry_empty_when_no_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    assert grounding.load_objective_registry(tmp_path / "proj") == ""


def test_objective_registry_filters_stale(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBJECTIVE_INJECTION_WINDOW_HOURS", "12")
    _write_objective(
        home,
        {"task": "stale", "project_root": str(project), "updated_at": "2020-01-01T00:00:00+00:00"},
    )
    assert grounding.load_objective_registry(project) == ""


def test_objective_registry_keeps_fresh_same_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OBJECTIVE_INJECTION_WINDOW_HOURS", "12")
    fresh = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    _write_objective(
        home,
        {
            "task": "fresh global objective",
            "next": "run focused tests",
            "project_root": str(project),
            "updated_at": fresh,
        },
    )
    out = grounding.load_objective_registry(project)
    assert "fresh global objective" in out
    assert "run focused tests" in out


def test_objective_registry_skips_terminal_status(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    fresh = datetime.now(UTC).isoformat()
    _write_objective(
        home,
        {
            "task": "done thing",
            "status": "shipped",
            "project_root": str(project),
            "updated_at": fresh,
        },
    )
    assert grounding.load_objective_registry(project) == ""


def test_objective_registry_skips_foreign_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    other = tmp_path / "other"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    fresh = datetime.now(UTC).isoformat()
    _write_objective(
        home,
        {"task": "other project", "project_root": str(other), "updated_at": fresh},
    )
    assert grounding.load_objective_registry(project) == ""


# --- grounding.py additional tests -------------------------------------------


def test_load_grounding_read_text_oserror(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: None)
    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    task_file = bank / "currentTask.md"
    task_file.write_text("dummy", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(self, *args, **kwargs):
        if self.name == "currentTask.md":
            raise OSError("Permission denied")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)
    out = grounding.load_memory_grounding(tmp_path)
    assert "Current Task" not in out


def test_load_grounding_helper_exception(tmp_path, monkeypatch):
    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    task_file = bank / "currentTask.md"
    task_file.write_text("line one\nline two", encoding="utf-8")

    class BadHelper:
        def filter_lines_for_injection(self, name, lines):
            raise RuntimeError("helper failed")

    monkeypatch.setattr(grounding, "_load_project_memory", lambda: BadHelper())
    out = grounding.load_memory_grounding(tmp_path)
    assert "line one" in out


def test_load_grounding_from_end_slice(tmp_path, monkeypatch):
    monkeypatch.setattr(grounding, "_load_project_memory", lambda: None)
    bank = tmp_path / ".memory-bank"
    bank.mkdir()
    long_text = "A" * 500 + "B" * 1000
    (bank / "progress.md").write_text(long_text, encoding="utf-8")

    out = grounding.load_memory_grounding(tmp_path)
    assert "Recent Progress" in out
    # Only the last 1000 characters should be in the output
    assert "A" not in out
    assert "B" in out


def test_load_project_memory_real_load(tmp_path, monkeypatch):
    # Reset the cache
    monkeypatch.setattr(grounding, "_PROJECT_MEMORY", None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # 1. file does not exist
    assert grounding._load_project_memory() is None

    # 2. file exists but spec or loader fails
    scripts_dir = tmp_path / ".claude" / "scripts"
    scripts_dir.mkdir(parents=True)
    pm_file = scripts_dir / "project-memory.py"
    pm_file.write_text(
        "def filter_lines_for_injection(name, lines):\n    return ['filtered']\n",
        encoding="utf-8",
    )

    # This should load successfully and cache it
    helper = grounding._load_project_memory()
    assert helper is not None
    assert helper.filter_lines_for_injection("name", []) == ["filtered"]

    # Call again, should return cached
    assert grounding._load_project_memory() is helper


def test_is_constraint_candidate_lengths():
    # Candidates must be between 8 and 260 chars.
    # Short candidate: "never" (len 5)
    assert grounding.extract_negative_constraints("Never.") == ""
    # Long candidate: "never " + "x"*300
    assert grounding.extract_negative_constraints("never " + "x" * 300) == ""


def test_objective_registry_bad_json(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    state = home / ".claude" / "state"
    state.mkdir(parents=True)
    # Bad JSON
    (state / "current-objective.json").write_text("{bad json}", encoding="utf-8")
    assert grounding.load_objective_registry(tmp_path) == ""


def test_objective_registry_missing_task_and_next(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write_objective(home, {"status": "in-progress", "updated_at": datetime.now(UTC).isoformat()})
    assert grounding.load_objective_registry(tmp_path) == ""


def test_objective_registry_with_phase_and_files(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write_objective(
        home,
        {
            "task": "my task",
            "next": "my next",
            "phase": "plan",
            "acceptance": "criteria",
            "files": ["a.py", "b.py"],
            "project_root": str(tmp_path),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )
    out = grounding.load_objective_registry(tmp_path)
    assert "**Task**: my task" in out
    assert "**Phase**: plan" in out
    assert "**Acceptance**: criteria" in out
    assert "**Next**: my next" in out
    assert "**Files**: a.py, b.py" in out


def test_objective_registry_stale_age_none(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    _write_objective(
        home, {"task": "my task", "project_root": str(tmp_path), "updated_at": "invalid-date"}
    )
    assert grounding.load_objective_registry(tmp_path) == ""


def test_same_or_nested_project_errors():
    from pathlib import Path

    assert not grounding._same_or_nested_project("\x00", Path("."))
    assert not grounding._same_or_nested_project("", Path("."))


def test_same_or_nested_project_nested_current(tmp_path):
    """Current nested under recorded -> True (worktree / subdir sessions)."""
    recorded = tmp_path  # /tmp/abc
    nested = tmp_path / "sub" / "deeper"
    nested.mkdir(parents=True)
    assert grounding._same_or_nested_project(str(recorded), nested) is True


def test_same_or_nested_project_equal(tmp_path):
    """Identity -> True."""
    assert grounding._same_or_nested_project(str(tmp_path), tmp_path) is True


def test_same_or_nested_project_unrelated(tmp_path):
    """Sibling trees -> False."""
    other = tmp_path / "other-project"
    other.mkdir()
    assert grounding._same_or_nested_project(str(other), tmp_path) is False


def test_load_project_memory_spec_fails(tmp_path, monkeypatch):
    import importlib.util

    # Reset the cache
    monkeypatch.setattr(grounding, "_PROJECT_MEMORY", None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Create the script file so is_file() passes
    scripts_dir = tmp_path / ".claude" / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "project-memory.py").write_text(
        "def filter_lines_for_injection(name, lines):\n    return ['filtered']\n", encoding="utf-8"
    )

    # Mock spec_from_file_location to return None
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *a, **k: None)
    assert grounding._load_project_memory() is None
