"""Tests for the shared/ infrastructure layer."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

import pytest

from smart_trim.shared import ollama, paths, timeutil


# --- get_project_root --------------------------------------------------------


def test_get_project_root_prefers_memory_bank(tmp_path):
    project = tmp_path / "project"
    nested = project / "src" / "pkg"
    (project / ".memory-bank").mkdir(parents=True)
    nested.mkdir(parents=True)

    assert paths.get_project_root(nested) == project.resolve()


def test_get_project_root_walks_to_parent_bank(tmp_path):
    project = tmp_path / "p"
    deep = project / "a" / "b" / "c"
    (project / ".memory-bank").mkdir(parents=True)
    deep.mkdir(parents=True)

    assert paths.get_project_root(deep) == project.resolve()


def test_get_project_root_fallback_cwd_when_no_bank(tmp_path, monkeypatch):
    # No .memory-bank anywhere up the tree from tmp_path's parent chain in CI
    # can be relied upon, so just assert it returns a Path and does not raise.
    monkeypatch.setattr(paths.Path, "cwd", classmethod(lambda cls: tmp_path))
    result = paths.get_project_root(str(tmp_path))
    assert isinstance(result, type(tmp_path))


# --- redact_sensitive --------------------------------------------------------


def test_redact_sensitive_passes_clean_lines():
    # "secret"/"password"/etc. are regex keywords — use text free of any.
    assert paths.redact_sensitive("the quick brown fox jumps") == "the quick brown fox jumps"


def test_redact_sensitive_redacts_api_key():
    out = paths.redact_sensitive("config: api_key=ABCDEF123456")
    assert "[REDACTED" in out
    assert "ABCDEF123456" not in out


def test_redact_sensitive_redacts_sk_token():
    out = paths.redact_sensitive("token: sk-abcdefghijklmnopqrstuvwxyz1234")
    assert "[REDACTED" in out


def test_redact_sensitive_preserves_other_lines_in_block():
    text = "line one\napi_key=secret\nline three"
    out = paths.redact_sensitive(text)
    lines = out.splitlines()
    assert lines[0] == "line one"
    assert "[REDACTED" in lines[1]
    assert lines[2] == "line three"


# --- slugify -----------------------------------------------------------------


def test_slugify_lowercases_and_dashes_spaces():
    assert paths.slugify("Session Handoffs") == "session-handoffs"


def test_slugify_strips_accents_via_fallback():
    # Non [a-z0-9._-] (including accented chars) become '-', then collapsed.
    out = paths.slugify("Sesión Handoffs!")
    assert "ñ" not in out
    assert out  # never empty


def test_slugify_empty_falls_back_to_default():
    assert paths.slugify("!!!") == "session-handoffs"


# --- is_ollama_alive (cached TCP probe) --------------------------------------


def test_is_ollama_alive_caches_success(monkeypatch):
    ollama._OLLAMA_ALIVE = None
    calls = {"n": 0}

    def fake_connect(addr, timeout):
        calls["n"] += 1

        class _Sock:
            def close(self):
                pass

        return _Sock()

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    assert ollama.is_ollama_alive() is True
    assert ollama.is_ollama_alive() is True  # cached -> no second probe
    assert calls["n"] == 1
    ollama._OLLAMA_ALIVE = None  # reset for other tests


def test_is_ollama_alive_returns_false_on_oserror(monkeypatch):
    ollama._OLLAMA_ALIVE = None

    def boom(addr, timeout):
        raise OSError("refused")

    monkeypatch.setattr(socket, "create_connection", boom)
    assert ollama.is_ollama_alive() is False
    ollama._OLLAMA_ALIVE = None


# --- timeutil ----------------------------------------------------------------


def test_objective_window_default(monkeypatch):
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    monkeypatch.delenv("MEMORY_INJECTION_ACTIVE_WINDOW_HOURS", raising=False)
    assert timeutil.objective_injection_window_hours() == 24.0


def test_objective_window_env_override(monkeypatch):
    monkeypatch.setenv("OBJECTIVE_INJECTION_WINDOW_HOURS", "6")
    assert timeutil.objective_injection_window_hours() == 6.0


def test_objective_window_falls_back_to_memory_window(monkeypatch):
    monkeypatch.delenv("OBJECTIVE_INJECTION_WINDOW_HOURS", raising=False)
    monkeypatch.setenv("MEMORY_INJECTION_ACTIVE_WINDOW_HOURS", "12")
    assert timeutil.objective_injection_window_hours() == 12.0


def test_objective_window_invalid_env_returns_default(monkeypatch):
    monkeypatch.setenv("OBJECTIVE_INJECTION_WINDOW_HOURS", "not-a-number")
    assert timeutil.objective_injection_window_hours() == 24.0


def test_hours_since_iso_z_suffix():
    # Use a far-past timestamp so it's unambiguously positive hours.
    h = timeutil.hours_since_iso("2020-01-01T00:00:00Z")
    assert h is not None and h > 0


def test_hours_since_iso_empty_returns_none():
    assert timeutil.hours_since_iso("") is None
    assert timeutil.hours_since_iso("   ") is None


def test_hours_since_iso_invalid_returns_none():
    assert timeutil.hours_since_iso("not-a-date") is None


def test_hours_since_iso_recent_is_small():
    now_iso = datetime.now(timezone.utc).isoformat()
    h = timeutil.hours_since_iso(now_iso)
    assert h is not None and h < 1.0


@pytest.mark.parametrize("inp", ["", "   ", "garbage"])
def test_hours_since_iso_none_cases(inp):
    assert timeutil.hours_since_iso(inp) is None
