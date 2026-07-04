"""Tests for features/grounding (read-side)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
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
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
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
    fresh = datetime.now(timezone.utc).isoformat()
    _write_objective(
        home,
        {"task": "done thing", "status": "shipped", "project_root": str(project), "updated_at": fresh},
    )
    assert grounding.load_objective_registry(project) == ""


def test_objective_registry_skips_foreign_project(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    other = tmp_path / "other"
    project.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    fresh = datetime.now(timezone.utc).isoformat()
    _write_objective(
        home,
        {"task": "other project", "project_root": str(other), "updated_at": fresh},
    )
    assert grounding.load_objective_registry(project) == ""
