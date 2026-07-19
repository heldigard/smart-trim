"""active-field rendering + summary parsing."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from contextlib import contextmanager  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import cast  # noqa: F401

import pytest

from smart_trim.features.writer import active as active_renderer  # noqa: F401
from smart_trim.features.writer import command as writer  # noqa: F401


def test_active_renderer_preserves_middle_error_id_and_path(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    error = ("noise " * 80) + "E_PARSE_MIDDLE /srv/app/parser.py:42 " + ("tail " * 80)
    summary = f"**Task**: diagnose parser\n**Errors**: {error}\n**Files**: {project}/src/parser.py"
    writer.update_agent_memory(summary, "fallback", "s", project_root=project)
    active = (project / ".memory-bank" / "activeContext.md").read_text(encoding="utf-8")

    assert "E_PARSE_MIDDLE" in active
    assert "/srv/app/parser.py:42" in active
    assert "…" in active and "[recortado]" not in active


def test_parser_rejects_malformed_bold_label_without_corrupting_task():
    fields, notes = active_renderer.parse_summary_fields("**Task:** malformed\n**Task**: canonical")
    assert fields["Task"] == ["canonical"]
    assert "**Task:** malformed" in notes


def test_parse_summary_fields_generic_header():
    summary = "## Some Other Header\n**Task**: fix it"
    fields, notes = active_renderer.parse_summary_fields(summary)
    assert fields["Task"] == ["fix it"]


def test_render_active_fields_critical_does_not_fit():
    header = ["# Active Context"] * 28
    summary = "**Task**: this task will not fit in the lines budget"
    with pytest.raises(ValueError, match="critical active-context field did not fit"):
        active_renderer.render_active_fields(summary, header)


def test_render_active_fields_detail_pointer_does_not_fit():
    header = ["# Active Context"] * 27
    summary = "**Task**: fit\n**Decisions**: choice"
    with pytest.raises(ValueError, match="active-context detail pointer did not fit"):
        active_renderer.render_active_fields(summary, header)


def test_render_active_fields_character_budget_exceeded():
    header = ["x" * 1250]
    summary = ""
    with pytest.raises(ValueError, match="character budget"):
        active_renderer.render_active_fields(summary, header)


def test_render_active_fields_detail_pointer_pops_non_critical():
    header = ["# Active Context"] * 26
    summary = "**Task**: fit\n**Decisions**: choice1\n**Objective**: choice2"
    res = active_renderer.render_active_fields(summary, header)
    assert any("Task" in r for r in res)
    assert any("Detail" in r for r in res)
    assert not any(r.startswith("- **Decisions**:") for r in res)
