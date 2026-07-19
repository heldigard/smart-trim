"""atomic write + write_active safety."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from contextlib import contextmanager  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import cast  # noqa: F401

import pytest

from smart_trim.features.writer import active as active_renderer  # noqa: F401
from smart_trim.features.writer import command as writer  # noqa: F401


def test_write_active_limits_lines(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    # Create a summary with 40 lines
    long_summary = "\n".join(f"line {i}" for i in range(40))
    writer.update_agent_memory(long_summary, "fallback", "sess-1", project_root=project)
    active = project / ".memory-bank" / "activeContext.md"
    assert active.exists()
    content = active.read_text(encoding="utf-8")
    lines = content.splitlines()
    # The header has 2 lines + at most 26 summary lines = max 28 lines total
    assert len(lines) <= 28


def test_write_active_prioritizes_critical_fields_before_verbose_optional(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    summary = (
        "**Current**: " + ("verbose progress " * 200) + "\n"
        "**Files**: " + (f"{project}/noise.py " * 100) + "\n"
        "## Preserved Negative Constraints\n"
        "- never bypass safety checks\n"
        "**Task**: fix parser correctness\n"
        "**Acceptance**: all regression cases pass\n"
        "**Verified**: targeted pytest is green\n"
        "**Errors**: ParserError E_PARSE_17\n"
        "**Next**: run the full suite"
    )
    writer.update_agent_memory(summary, "fallback", "s", project_root=project)
    active = (project / ".memory-bank" / "activeContext.md").read_text(encoding="utf-8")

    assert len(active) <= active_renderer.ACTIVE_CONTEXT_MAX_CHARS
    assert len(active.splitlines()) <= active_renderer.ACTIVE_CONTEXT_MAX_LINES
    for expected in (
        "never bypass safety checks",
        "fix parser correctness",
        "all regression cases pass",
        "targeted pytest is green",
        "ParserError E_PARSE_17",
        "run the full suite",
    ):
        assert expected in active
    assert active_renderer.ACTIVE_DETAIL_POINTER in active


# --- compact_items -----------------------------------------------------------


def test_atomic_active_write_failure_preserves_previous_file(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    memory = project / ".memory-bank"
    memory.mkdir(parents=True)
    active = memory / "activeContext.md"
    active.write_text("previous-complete-handoff\n", encoding="utf-8")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(active_renderer.os, "replace", fail_replace)
    writer.update_agent_memory(
        "**Task**: replacement must fail", "fallback", "s", project_root=project
    )

    assert active.read_text(encoding="utf-8") == "previous-complete-handoff\n"
    assert not list(memory.glob(".activeContext.md.*.tmp"))


def test_atomic_write_text_unlink_oserror(tmp_path, monkeypatch):
    import tempfile

    original_mkstemp = tempfile.mkstemp

    def fake_mkstemp(*args, **kwargs):
        fd, name = original_mkstemp(*args, **kwargs)
        original_unlink = Path.unlink

        def fake_unlink(self, *a, **k):
            if self.name == Path(name).name:
                raise OSError("Simulated unlink failure")
            return original_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", fake_unlink)
        return fd, name

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)

    def fake_replace(*args, **kwargs):
        raise OSError("Simulated replace failure")

    monkeypatch.setattr(active_renderer.os, "replace", fake_replace)

    with pytest.raises(OSError, match="Simulated replace failure"):
        active_renderer.atomic_write_text(tmp_path / "target", "content")
