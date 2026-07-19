"""Tests for capabilities discovery + the `smart-trim smoke` subcommand."""

from __future__ import annotations

import io
import json
import subprocess
from unittest import mock

from smart_trim.features.capabilities import command as caps


def test_help_text_mentions_smoke_subcommand():
    assert "smoke" in caps.help_text()


def test_capabilities_payload_lists_smoke():
    payload = caps.capabilities_payload()
    names = {c["name"] for c in payload["capabilities"]}
    assert "smoke" in names
    assert "precompact" in names


def _install_fake_shim(tmp_path, monkeypatch) -> None:
    """Point Path.home at tmp and create the wired shim path (CI has no ~/.claude)."""
    monkeypatch.setattr(caps.Path, "home", classmethod(lambda cls: tmp_path))
    shim = tmp_path / ".claude" / "hooks" / "smart-trim.py"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/usr/bin/env python3\n# fake\n", encoding="utf-8")


def test_handle_cli_smoke_raises_system_exit(tmp_path, monkeypatch):
    """`handle_cli(['smoke'])` exits with the shim subprocess exit code.

    We intercept subprocess.run so the test does not require the actual hook
    process. A real shim *file* is still required (CI runners have none under
    ~/.claude), so we plant one under a fake HOME.
    """
    _install_fake_shim(tmp_path, monkeypatch)
    fake_payload = json.dumps({"continue": True, "method": "minimal"})
    fake_proc = mock.Mock(
        returncode=0,
        stdout=fake_payload,
        stderr="",
    )
    with (
        mock.patch.object(caps.subprocess, "run", return_value=fake_proc) as run_mock,
        mock.patch.dict(
            caps.os.environ,
            {
                "CLAUDE_SESSION_FILE": "/real/session.jsonl",
                "CLAUDE_SESSION_ID": "real-session",
                "CLAUDE_PROJECT_DIR": "/real/project",
            },
        ),
    ):
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
        assert json.loads(kwargs["input"])["cwd"] != str(caps.Path.cwd())
        for name in ("CLAUDE_SESSION_FILE", "CLAUDE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
            assert name not in kwargs["env"]


def test_handle_cli_returns_false_for_unknown_args():
    assert caps.handle_cli([]) is False
    assert caps.handle_cli(["bogus"]) is False


def test_handle_cli_help_prints():
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


def test_handle_cli_capabilities_json():
    buf = io.StringIO()
    with mock.patch.object(caps.sys, "stdout", buf):
        handled = caps.handle_cli(["capabilities", "--json"])
    assert handled is True
    payload = json.loads(buf.getvalue())
    assert payload["command"] == "capabilities"
    assert any(c["name"] == "doctor" for c in payload["capabilities"])


def test_run_smoke_returns_nonzero_when_shim_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(caps.Path, "home", classmethod(lambda cls: tmp_path))
    code = caps.run_smoke()
    assert code == 2  # shim-not-found code


def test_run_smoke_unparseable_stdout(tmp_path, monkeypatch):
    _install_fake_shim(tmp_path, monkeypatch)
    fake_proc = mock.Mock(returncode=0, stdout="not-json", stderr="")
    with mock.patch.object(caps.subprocess, "run", return_value=fake_proc):
        code = caps.run_smoke()
    assert code == 5


def test_run_smoke_timeout(tmp_path, monkeypatch):
    _install_fake_shim(tmp_path, monkeypatch)

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="shim", timeout=30)

    with mock.patch.object(caps.subprocess, "run", side_effect=boom):
        code = caps.run_smoke()
    assert code == 3


def test_run_smoke_oserror(tmp_path, monkeypatch):
    _install_fake_shim(tmp_path, monkeypatch)

    def boom(*_a, **_k):
        raise OSError("exec failed")

    with mock.patch.object(caps.subprocess, "run", side_effect=boom):
        code = caps.run_smoke()
    assert code == 4


def test_run_smoke_nonzero_exit(tmp_path, monkeypatch):
    _install_fake_shim(tmp_path, monkeypatch)
    fake_proc = mock.Mock(returncode=7, stdout="", stderr="boom")
    with mock.patch.object(caps.subprocess, "run", return_value=fake_proc):
        code = caps.run_smoke()
    assert code == 7


def test_run_smoke_happy_path(tmp_path, monkeypatch, capsys):
    _install_fake_shim(tmp_path, monkeypatch)
    fake_payload = json.dumps({"continue": True, "method": "minimal"})
    fake_proc = mock.Mock(returncode=0, stdout=fake_payload, stderr="")
    with mock.patch.object(caps.subprocess, "run", return_value=fake_proc):
        code = caps.run_smoke()
    assert code == 0
    assert "[smoke] OK" in capsys.readouterr().out
