"""Focused tests for runtime hook wiring inspection."""

from __future__ import annotations

import json
from pathlib import Path

from smart_trim.features.diagnostics import wiring


def _write_settings(
    path: Path,
    *,
    command: str,
    timeout: int | float | None = 90,
) -> None:
    hook: dict[str, object] = {"type": "command", "command": command}
    if timeout is not None:
        hook["timeout"] = timeout
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"hooks": {"PreCompact": [{"matcher": "", "hooks": [hook]}]}}),
        encoding="utf-8",
    )


def _write_shim(path: Path, *, delegates: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"from {wiring.REQUIRED_MODULE} import main\nmain()\n"
        if delegates
        else "print('legacy standalone hook')\n"
    )
    path.write_text(body, encoding="utf-8")


def test_inspect_shim_requires_package_delegate(tmp_path):
    shim = tmp_path / "smart-trim.py"
    _write_shim(shim)
    assert wiring.inspect_shim(shim).ok is True

    _write_shim(shim, delegates=False)
    result = wiring.inspect_shim(shim)
    assert result.ok is False
    assert "does not delegate" in result.detail


def test_inspect_shim_rejects_comment_or_import_without_call(tmp_path):
    shim = tmp_path / "smart-trim.py"
    required_import = f"from {wiring.REQUIRED_MODULE} import main"
    shim.write_text(f"# {required_import}\n", encoding="utf-8")
    assert wiring.inspect_shim(shim).ok is False

    shim.write_text(f"{required_import}\n", encoding="utf-8")
    result = wiring.inspect_shim(shim)
    assert result.ok is False
    assert "does not invoke" in result.detail


def test_inspect_shim_handles_missing_file(tmp_path):
    result = wiring.inspect_shim(tmp_path / "missing.py")
    assert result.ok is False
    assert "unreadable" in result.detail


def test_inspect_precompact_config_finds_expected_command_and_timeout(tmp_path):
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        command='python3 "$HOME/.claude/hooks/smart-trim.py"',
        timeout=90,
    )

    result = wiring.inspect_precompact_config(
        settings,
        expected_suffix=".claude/hooks/smart-trim.py",
    )

    assert result.configured is True
    assert result.timeout_seconds == 90.0
    assert result.matches == 1


def test_inspect_precompact_config_uses_shortest_matching_timeout(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreCompact": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 ~/.claude/hooks/smart-trim.py",
                                    "timeout": 90,
                                },
                                {
                                    "type": "command",
                                    "command": "python3 /home/user/.claude/hooks/smart-trim.py",
                                    "timeout": 55,
                                },
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result = wiring.inspect_precompact_config(
        settings,
        expected_suffix=".claude/hooks/smart-trim.py",
    )

    assert result.configured is True
    assert result.matches == 2
    assert result.timeout_seconds == 55.0


def test_inspect_precompact_config_does_not_echo_wrong_command(tmp_path):
    settings = tmp_path / "settings.json"
    private_command = "python3 /private/location/other-hook.py"
    _write_settings(settings, command=private_command)

    result = wiring.inspect_precompact_config(
        settings,
        expected_suffix=".claude/hooks/smart-trim.py",
    )

    assert result.configured is False
    assert private_command not in result.detail


def test_inspect_precompact_config_requires_directory_boundary(tmp_path):
    settings = tmp_path / "settings.json"
    _write_settings(
        settings,
        command="python3 /private/not.claude/hooks/smart-trim.py",
    )

    result = wiring.inspect_precompact_config(
        settings,
        expected_suffix=".claude/hooks/smart-trim.py",
    )

    assert result.configured is False


def test_inspect_precompact_config_handles_malformed_json(tmp_path):
    settings = tmp_path / "settings.json"
    settings.write_text("{bad json", encoding="utf-8")

    result = wiring.inspect_precompact_config(
        settings,
        expected_suffix=".claude/hooks/smart-trim.py",
    )

    assert result.configured is False
    assert "invalid JSON" in result.detail


def test_collect_runtime_checks_all_green(tmp_path):
    claude_shim = tmp_path / ".claude" / "hooks" / "smart-trim.py"
    codex_shim = tmp_path / ".codex" / "hooks" / "smart-trim.py"
    _write_shim(claude_shim)
    _write_shim(codex_shim)
    _write_settings(
        tmp_path / ".claude" / "settings.json",
        command="python3 ~/.claude/hooks/smart-trim.py",
        timeout=90,
    )
    _write_settings(
        tmp_path / ".codex" / "hooks.json",
        command="/usr/bin/python3 /home/user/.codex/hooks/smart-trim.py",
        timeout=90,
    )

    checks = wiring.collect_runtime_checks(40.0, home=tmp_path)

    assert {check["name"] for check in checks} == {
        "precompact_shim",
        "claude_precompact",
        "codex_shim",
        "codex_precompact",
    }
    assert all(check["level"] == "ok" for check in checks)
    serialized = json.dumps(checks)
    assert "python3 ~/.claude" not in serialized
    assert "/usr/bin/python3" not in serialized


def test_collect_runtime_checks_fails_on_under_budget_claude_timeout(tmp_path):
    _write_shim(tmp_path / ".claude" / "hooks" / "smart-trim.py")
    _write_settings(
        tmp_path / ".claude" / "settings.json",
        command="python3 ~/.claude/hooks/smart-trim.py",
        timeout=40,
    )

    checks = wiring.collect_runtime_checks(40.0, home=tmp_path)
    by_name = {check["name"]: check for check in checks}

    assert by_name["claude_precompact"]["level"] == "fail"
    assert "must exceed" in by_name["claude_precompact"]["detail"]


def test_collect_runtime_checks_warns_when_timeout_is_unknown(tmp_path):
    _write_shim(tmp_path / ".claude" / "hooks" / "smart-trim.py")
    _write_settings(
        tmp_path / ".claude" / "settings.json",
        command="python3 ~/.claude/hooks/smart-trim.py",
        timeout=None,
    )

    checks = wiring.collect_runtime_checks(40.0, home=tmp_path)
    by_name = {check["name"]: check for check in checks}

    assert by_name["claude_precompact"]["level"] == "warn"
    assert "timeout is missing" in by_name["claude_precompact"]["detail"]


def test_collect_runtime_checks_omits_absent_optional_codex_config(tmp_path):
    _write_shim(tmp_path / ".claude" / "hooks" / "smart-trim.py")
    _write_settings(
        tmp_path / ".claude" / "settings.json",
        command="python3 ~/.claude/hooks/smart-trim.py",
    )

    names = {check["name"] for check in wiring.collect_runtime_checks(40.0, home=tmp_path)}

    assert "codex_precompact" not in names
    assert "codex_shim" not in names


def test_collect_runtime_checks_warns_on_broken_optional_codex_wiring(tmp_path):
    _write_shim(tmp_path / ".claude" / "hooks" / "smart-trim.py")
    _write_settings(
        tmp_path / ".claude" / "settings.json",
        command="python3 ~/.claude/hooks/smart-trim.py",
    )
    _write_settings(
        tmp_path / ".codex" / "hooks.json",
        command="python3 /somewhere/else.py",
    )

    checks = wiring.collect_runtime_checks(40.0, home=tmp_path)
    by_name = {check["name"]: check for check in checks}

    assert by_name["codex_shim"]["level"] == "warn"
    assert by_name["codex_precompact"]["level"] == "warn"
