"""Tests for the observability event recorder."""

from __future__ import annotations

import json

import pytest

from smart_trim.features.observability import command as obs
from smart_trim.features.observability.command import CompactEvent


@pytest.fixture(autouse=True)
def _gate_on(monkeypatch):
    monkeypatch.setenv("SMART_TRIM_OBSERVABILITY", "1")


def test_disabled_when_gate_off(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_TRIM_OBSERVABILITY", "0")
    wrote = obs.record_compact_event(
        tmp_path,
        CompactEvent(method="ollama-x", route="active", trigger="manual", latency_ms=10),
    )
    assert wrote is False
    assert not (tmp_path / ".memory-bank" / "topics" / "compact-events.md").exists()


def test_writes_topic_and_index_on_first_event(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    obs.record_compact_event(
        project, CompactEvent(method="ollama-x", route="active", trigger="manual")
    )
    topic = project / ".memory-bank" / "topics" / "compact-events.md"
    assert topic.exists()
    index = project / ".memory-bank" / "topics" / "_index.md"
    assert "compact-events.md" in index.read_text(encoding="utf-8")


def test_appends_one_json_line_per_call(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    obs.record_compact_event(
        project,
        CompactEvent(method="ollama-x", route="active", trigger="manual", latency_ms=42),
    )
    obs.record_compact_event(
        project,
        CompactEvent(method="fallback", route="foreign", trigger="auto", latency_ms=5),
    )
    lines = (
        (project / ".memory-bank" / "topics" / "compact-events.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    # 1 header + 2 events
    json_lines = [ln for ln in lines if ln.startswith("{")]
    assert len(json_lines) == 2
    parsed = [json.loads(ln) for ln in json_lines]
    assert parsed[0]["method"] == "ollama-x"
    assert parsed[0]["route"] == "active"
    assert parsed[0]["trigger"] == "manual"
    assert parsed[0]["latency_ms"] == 42
    assert parsed[1]["method"] == "fallback"
    assert parsed[1]["route"] == "foreign"


def test_session_hash_is_short_and_stable():
    h1 = obs.session_hash("sess-abc-123")
    h2 = obs.session_hash("sess-abc-123")
    h3 = obs.session_hash("sess-xyz-999")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 12


def test_session_hash_handles_empty_and_non_ascii():
    assert len(obs.session_hash("")) == 12
    h = obs.session_hash("sess-é-ñ")
    assert len(h) == 12


def test_records_model_chain(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    obs.record_compact_event(
        project,
        CompactEvent(
            method="fallback",
            route="active",
            trigger="auto",
            model_chain=("ollama-primary", "ollama-secondary", "deepseek-cloud"),
        ),
    )
    lines = (
        (project / ".memory-bank" / "topics" / "compact-events.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    payload = json.loads(next(ln for ln in lines if ln.startswith("{")))
    assert payload["chain"] == ["ollama-primary", "ollama-secondary", "deepseek-cloud"]


def test_negative_counters_clamped_to_zero(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    obs.record_compact_event(
        project,
        CompactEvent(
            method="x",
            route="x",
            trigger="x",
            latency_ms=-5,
            input_bytes=-3,
            output_bytes=-10,
        ),
    )
    lines = (
        (project / ".memory-bank" / "topics" / "compact-events.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    payload = json.loads(next(ln for ln in lines if ln.startswith("{")))
    assert payload["latency_ms"] == 0
    assert payload["in"] == 0
    assert payload["out"] == 0


def test_empty_labels_redacted(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    obs.record_compact_event(
        project,
        CompactEvent(method="", route="", trigger=""),
    )
    lines = (
        (project / ".memory-bank" / "topics" / "compact-events.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    payload = json.loads(next(ln for ln in lines if ln.startswith("{")))
    assert payload["method"] == "[REDACTED]"
    assert payload["route"] == "[REDACTED]"
    assert payload["trigger"] == "[REDACTED]"


def test_long_label_truncated(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    long = "a" * 200
    obs.record_compact_event(
        project,
        CompactEvent(method=long, route="r", trigger="t"),
    )
    lines = (
        (project / ".memory-bank" / "topics" / "compact-events.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    payload = json.loads(next(ln for ln in lines if ln.startswith("{")))
    assert len(payload["method"]) == 64


def test_index_registration_idempotent(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    for _ in range(3):
        obs.record_compact_event(project, CompactEvent(method="x", route="x", trigger="x"))
    index = project / ".memory-bank" / "topics" / "_index.md"
    text = index.read_text(encoding="utf-8")
    assert text.count("(compact-events.md)") == 1


def test_unwritable_root_returns_false_not_raises(tmp_path):
    # A regular file masquerading as a project root — the parent's mkdir works
    # but .memory-bank/ cannot be created as a child of a file.
    file_root = tmp_path / "not_a_dir"
    file_root.write_text("x", encoding="utf-8")
    # record_compact_event swallows exceptions internally; assert no raise + False.
    wrote = obs.record_compact_event(
        file_root,
        CompactEvent(method="x", route="x", trigger="x"),
    )
    assert wrote is False
