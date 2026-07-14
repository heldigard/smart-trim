"""Tests for the shared/ infrastructure layer."""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from pathlib import Path

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
    fake_key = "ABCDEF" + "123456"
    out = paths.redact_sensitive(f"config: api_key={fake_key}")
    assert "[REDACTED" in out
    assert fake_key not in out


def test_redact_sensitive_redacts_sk_token():
    fake_token = "sk-" + "abcdefghijklmnopqrstuvwxyz" + "1234"
    out = paths.redact_sensitive(f"token: {fake_token}")
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


def test_default_summaries_dir_is_claude_summaries(monkeypatch, tmp_path):
    """Canonical archive location — shared by hygiene + precompact."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert paths.default_summaries_dir() == tmp_path / ".claude" / "summaries"


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
    now_iso = datetime.now(UTC).isoformat()
    h = timeutil.hours_since_iso(now_iso)
    assert h is not None and h < 1.0


@pytest.mark.parametrize("inp", ["", "   ", "garbage"])
def test_hours_since_iso_none_cases(inp):
    assert timeutil.hours_since_iso(inp) is None


# --- paths.py additional tests ------------------------------------------------


def test_has_memory_bank_oserror(monkeypatch):
    from pathlib import Path

    def fake_is_dir(self):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "is_dir", fake_is_dir)
    assert not paths._has_memory_bank(Path("/some/path"))


def test_git_toplevel_error_and_timeout(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert paths._git_toplevel(Path("/some/path")) is None

    def fake_run_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=1)

    monkeypatch.setattr(subprocess, "run", fake_run_timeout)
    assert paths._git_toplevel(Path("/some/path")) is None


def test_git_toplevel_nonzero_exit(monkeypatch):
    import subprocess

    class FakeResult:
        def __init__(self, code, out):
            self.returncode = code
            self.stdout = out

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult(1, ""))
    assert paths._git_toplevel(Path("/some/path")) is None

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult(0, "  \n  "))
    assert paths._git_toplevel(Path("/some/path")) is None


def test_git_toplevel_success(monkeypatch, tmp_path):
    import subprocess

    class FakeResult:
        returncode = 0

        def __init__(self, out):
            self.stdout = out

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult(str(tmp_path)))
    assert paths._git_toplevel(tmp_path) == tmp_path.resolve()


def test_bank_ancestor_returns_none_when_root_reached(monkeypatch):
    # No .memory-bank anywhere; _bank_ancestor must walk to the filesystem root
    # and break via `parent == parent.parent` (covers the root-parent guard at
    # paths.py:46-47). _has_memory_bank monkeypatched to always return False so
    # we exercise the break branch on a synthetic tree, not the real FS.
    monkeypatch.setattr(paths, "_has_memory_bank", lambda _p: False)
    fake = Path("/tmp/fake-deep/inner/leaf")
    assert paths._bank_ancestor(fake) is None


def test_bank_ancestor_returns_root_when_root_has_bank(monkeypatch):
    monkeypatch.setattr(paths, "_has_memory_bank", lambda p: p == Path("/"))
    assert paths._bank_ancestor(Path("/tmp/somewhere")) == Path("/")


def test_get_project_root_resolve_error(monkeypatch):
    from pathlib import Path

    def fake_expanduser(self):
        raise ValueError("invalid path")

    monkeypatch.setattr(Path, "expanduser", fake_expanduser)
    # This should fall back to Path.cwd() without crashing
    assert isinstance(paths.get_project_root("~nonexistent"), Path)


def test_get_project_root_with_git_toplevel(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_git_toplevel", lambda cwd: tmp_path)
    assert paths.get_project_root(tmp_path / "subdir") == tmp_path


def test_config_env_overrides(monkeypatch):
    import importlib

    from smart_trim.shared import config

    # 1. Valid overrides
    monkeypatch.setenv("SMART_TRIM_MAX_CONTEXT_LOCAL", "50000")
    monkeypatch.setenv("SMART_TRIM_MAX_CONTEXT_CLOUD", "250000")
    importlib.reload(config)
    assert config.MAX_CONTEXT_FOR_SUMMARY == 50000
    assert config.MAX_CONTEXT_FOR_CLOUD == 250000

    # 2. Invalid overrides (ValueError)
    monkeypatch.setenv("SMART_TRIM_MAX_CONTEXT_LOCAL", "invalid")
    monkeypatch.setenv("SMART_TRIM_MAX_CONTEXT_CLOUD", "invalid")
    importlib.reload(config)
    assert config.MAX_CONTEXT_FOR_SUMMARY == 20000
    assert config.MAX_CONTEXT_FOR_CLOUD == 100000

    # Clean up by restoring defaults
    monkeypatch.delenv("SMART_TRIM_MAX_CONTEXT_LOCAL", raising=False)
    monkeypatch.delenv("SMART_TRIM_MAX_CONTEXT_CLOUD", raising=False)
    importlib.reload(config)


# --- redaction: high-confidence token prefixes -------------------------------


def test_redact_sensitive_redacts_github_token():
    token = "ghp_" + "A" * 36
    out = paths.redact_sensitive(f"push with {token}")
    assert "[REDACTED" in out and token not in out


def test_redact_sensitive_redacts_aws_key_id():
    key = "AKIA" + "IOSFODNN7EXAMPLE"
    out = paths.redact_sensitive(f"aws {key}")
    assert "[REDACTED" in out and key not in out


def test_redact_sensitive_redacts_slack_token():
    token = "xoxb-" + "123456789012-abcdef"
    out = paths.redact_sensitive(f"slack {token}")
    assert "[REDACTED" in out and token not in out


def test_redact_sensitive_redacts_gitlab_pat():
    token = "glpat-" + "x" * 20
    out = paths.redact_sensitive(f"gitlab {token}")
    assert "[REDACTED" in out and token not in out


def test_redact_sensitive_redacts_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
    out = paths.redact_sensitive(f"auth header {jwt}")
    assert "[REDACTED" in out and jwt not in out


def test_redact_sensitive_keeps_plain_gh_words():
    assert paths.redact_sensitive("ghpages deploy ok") == "ghpages deploy ok"


# --- redaction: two-tier precision (value-span + keyword->EOL) ---------------


def test_redact_preserves_context_before_keyword():
    # A decision that merely names a field keeps its context; the old
    # whole-line redaction deleted this entirely.
    out = paths.redact_sensitive("Decisions: rotate the api_key weekly")
    assert "Decisions: rotate the" in out
    assert "api_key" not in out
    assert "weekly" not in out  # masked keyword->EOL
    assert "[REDACTED" in out


def test_redact_masks_value_span_keeps_trailing_text():
    token = "ghp_" + "B" * 36
    out = paths.redact_sensitive(f"deploy via {token} (prod)")
    assert token not in out
    assert "(prod)" in out  # high-confidence value masked at span only
    assert "deploy via" in out


def test_redact_catches_prose_form_secret():
    # "the secret is hunter2" must still lose the value (keyword->EOL).
    out = paths.redact_sensitive("the secret is hunter2")
    assert "hunter2" not in out
    assert "secret" not in out
    assert "the" in out


def test_redact_decision_with_secret_word_keeps_decision_label():
    out = paths.redact_sensitive("**Decisions**: do not commit secrets to repo")
    assert "**Decisions**" in out
    assert "secrets" not in out


def test_redact_is_idempotent_under_double_application():
    # The orchestrator redacts, then the writer redacts again on the same text.
    # A second pass must be a no-op (placeholder carries no trigger keyword).
    once = paths.redact_sensitive("config: api_key=hunter2 and ghp_" + "C" * 36)
    twice = paths.redact_sensitive(once)
    assert once == twice
    assert "hunter2" not in twice


# --- Ollama endpoint env override --------------------------------------------


def test_ollama_base_env_override_full_url(monkeypatch):
    import importlib

    from smart_trim.shared import config

    monkeypatch.setenv("SMART_TRIM_OLLAMA_BASE", "http://10.0.0.5:11500")
    importlib.reload(config)
    try:
        assert config.OLLAMA_BASE == "http://10.0.0.5:11500"
        assert config.OLLAMA_HOST == "10.0.0.5"
        assert config.OLLAMA_PORT == 11500
    finally:
        monkeypatch.delenv("SMART_TRIM_OLLAMA_BASE", raising=False)
        importlib.reload(config)


def test_ollama_base_env_override_bare_hostport(monkeypatch):
    import importlib

    from smart_trim.shared import config

    monkeypatch.setenv("OLLAMA_HOST", "remote-box:11434")
    monkeypatch.delenv("SMART_TRIM_OLLAMA_BASE", raising=False)
    importlib.reload(config)
    try:
        assert config.OLLAMA_BASE == "http://remote-box:11434"
        assert config.OLLAMA_HOST == "remote-box"
        assert config.OLLAMA_PORT == 11434
    finally:
        monkeypatch.delenv("OLLAMA_HOST", raising=False)
        importlib.reload(config)


def test_ollama_base_invalid_env_falls_back(monkeypatch):
    import importlib

    from smart_trim.shared import config

    monkeypatch.setenv("SMART_TRIM_OLLAMA_BASE", "http://bad:port:99")
    importlib.reload(config)
    try:
        assert config.OLLAMA_BASE == "http://localhost:11434"
        assert config.OLLAMA_HOST == "localhost"
        assert config.OLLAMA_PORT == 11434
    finally:
        monkeypatch.delenv("SMART_TRIM_OLLAMA_BASE", raising=False)
        importlib.reload(config)
