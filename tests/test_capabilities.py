"""Tests for capabilities discovery + the `smart-trim smoke` subcommand."""

from __future__ import annotations

import io
import json
from unittest import mock

from smart_trim.features.capabilities import command as caps


def test_help_text_mentions_smoke_subcommand():
    assert "smoke" in caps.help_text()


def test_capabilities_payload_lists_smoke():
    payload = caps.capabilities_payload()
    names = {c["name"] for c in payload["capabilities"]}
    assert "smoke" in names
    assert "precompact" in names


def test_handle_cli_smoke_raises_system_exit():
    """`handle_cli(['smoke'])` exits with the shim subprocess exit code.

    We intercept subprocess.run so the test does not require the actual shim
    file to exist (CI runners may not have it). The shim is faked as a process
    that prints a valid hook payload.
    """
    fake_payload = json.dumps({"continue": True, "method": "minimal"})
    fake_proc = mock.Mock(
        returncode=0,
        stdout=fake_payload,
        stderr="",
    )
    with mock.patch.object(caps.subprocess, "run", return_value=fake_proc) as run_mock:
        try:
            caps.handle_cli(["smoke"])
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("SystemExit was not raised")
        called = run_mock.call_args
        # The shim path is read from HOME/.claude/hooks/ — the exact path
        # varies per host, so we only assert structure of the call.
        args, kwargs = called
        assert "smart-trim.py" in str(args[0][1])
        assert "input" in kwargs and kwargs["input"] != ""  # synthetic payload piped


def test_handle_cli_returns_false_for_unknown_args():
    assert caps.handle_cli([]) is False
    assert caps.handle_cli(["bogus"]) is False


def test_handle_cli_help_prints():
    import io

    buf = io.StringIO()
    with mock.patch.object(caps.sys, "stdout", buf):
        handled = caps.handle_cli(["--help"])
    assert handled is True
    assert "usage:" in buf.getvalue()


def test_handle_cli_capabilities_prints_human_table():
    buf = io.StringIO()
    with mock.patch.object(caps.sys, "stdout", buf):
        handled = caps.handle_cli(["capabilities"])
    assert handled is True
    out = buf.getvalue()
    assert "precompact" in out
    assert "smoke" in out


def test_run_smoke_returns_nonzero_when_shim_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(caps.Path, "home", classmethod(lambda cls: tmp_path))
    code = caps.run_smoke()
    assert code == 2  # shim-not-found code


def test_run_smoke_unparseable_stdout(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    shim = tmp_path / ".claude" / "hooks" / "smart-trim.py"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/usr/bin/env python3\nprint('not-json')\n", encoding="utf-8")
    code = caps.run_smoke()
    assert code == 5
