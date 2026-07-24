"""Inspect the on-disk hook wiring used to reach smart-trim.

The explicit ``doctor`` command uses these probes; the PreCompact hot path does
not import this module. Settings inspection is intentionally narrow and never
returns raw hook commands, so diagnostics cannot disclose unrelated local
configuration.
"""

from __future__ import annotations

import ast
import json
import math
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_MODULE = "smart_trim.features.precompact.command"


@dataclass(frozen=True, slots=True)
class ShimInspection:
    """Whether a shim is readable and delegates to the package entry."""

    ok: bool
    detail: str


@dataclass(frozen=True, slots=True)
class HookWiring:
    """Sanitized result of inspecting one runtime's PreCompact settings."""

    configured: bool
    timeout_seconds: float | None
    matches: int
    detail: str


def inspect_shim(path: Path) -> ShimInspection:
    """Check that ``path`` contains the current package delegate."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ShimInspection(False, "missing or unreadable")
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ShimInspection(False, "contains invalid Python")
    imports_main = any(
        isinstance(node, ast.ImportFrom)
        and node.module == REQUIRED_MODULE
        and any(alias.name == "main" and alias.asname is None for alias in node.names)
        for node in ast.walk(tree)
    )
    if not imports_main:
        return ShimInspection(False, "does not delegate to the package entry")
    calls_main = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "main"
        for node in ast.walk(tree)
    )
    if not calls_main:
        return ShimInspection(False, "imports the package entry but does not invoke main")
    return ShimInspection(True, "delegates to the package entry")


def _command_targets_suffix(command: object, expected_suffix: str) -> bool:
    if not isinstance(command, str):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    suffix = expected_suffix.replace("\\", "/").strip("/")
    return any(
        (normalized := token.replace("\\", "/").rstrip("/")) == suffix
        or normalized.endswith(f"/{suffix}")
        for token in tokens
    )


def _positive_timeout(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def inspect_precompact_config(path: Path, *, expected_suffix: str) -> HookWiring:
    """Inspect only ``hooks.PreCompact`` and return no raw command content."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HookWiring(False, None, 0, "settings file is missing")
    except OSError:
        return HookWiring(False, None, 0, "settings file is unreadable")
    except (UnicodeError, json.JSONDecodeError):
        return HookWiring(False, None, 0, "settings contain invalid JSON")

    if not isinstance(payload, dict):
        return HookWiring(False, None, 0, "settings root is not an object")
    hooks = payload.get("hooks")
    precompact = hooks.get("PreCompact") if isinstance(hooks, dict) else None
    if not isinstance(precompact, list):
        return HookWiring(False, None, 0, "PreCompact hook list is missing")

    timeouts: list[float] = []
    timeout_unknown = False
    matches = 0
    for group in precompact:
        if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
            continue
        for hook in group["hooks"]:
            if (
                not isinstance(hook, dict)
                or hook.get("type") != "command"
                or not _command_targets_suffix(hook.get("command"), expected_suffix)
            ):
                continue
            matches += 1
            timeout = _positive_timeout(hook.get("timeout"))
            if timeout is None:
                timeout_unknown = True
            else:
                timeouts.append(timeout)

    if not matches:
        return HookWiring(False, None, 0, "no matching PreCompact command")
    timeout = None if timeout_unknown else min(timeouts, default=None)
    return HookWiring(True, timeout, matches, f"{matches} matching command(s)")


def _hook_check(
    *,
    name: str,
    label: str,
    config_path: Path,
    expected_suffix: str,
    cascade_budget_seconds: float,
    broken_level: str,
) -> dict[str, Any]:
    wiring = inspect_precompact_config(config_path, expected_suffix=expected_suffix)
    base: dict[str, Any] = {
        "name": name,
        "path": str(config_path),
        "configured": wiring.configured,
        "matches": wiring.matches,
    }
    if not wiring.configured:
        return {
            **base,
            "level": broken_level,
            "detail": f"{label} wiring invalid: {wiring.detail}",
        }
    if wiring.timeout_seconds is None:
        return {
            **base,
            "level": "warn",
            "detail": f"{label} wired, but timeout is missing or invalid",
        }
    base["timeout_seconds"] = wiring.timeout_seconds
    base["cascade_budget_seconds"] = cascade_budget_seconds
    if wiring.timeout_seconds <= cascade_budget_seconds:
        return {
            **base,
            "level": broken_level,
            "detail": (
                f"{label} timeout {wiring.timeout_seconds:g}s must exceed "
                f"cascade budget {cascade_budget_seconds:g}s"
            ),
        }
    return {
        **base,
        "level": "ok",
        "detail": (
            f"{label} wired with {wiring.timeout_seconds:g}s timeout "
            f"(cascade budget {cascade_budget_seconds:g}s)"
        ),
    }


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def collect_runtime_checks(
    cascade_budget_seconds: float,
    *,
    home: Path | None = None,
) -> list[dict[str, Any]]:
    """Return sanitized shim/config checks for installed runtimes."""
    runtime_home = home or Path.home()
    checks: list[dict[str, Any]] = []

    claude_shim = runtime_home / ".claude" / "hooks" / "smart-trim.py"
    shim = inspect_shim(claude_shim)
    checks.append(
        {
            "level": "ok" if shim.ok else "fail",
            "name": "precompact_shim",
            "detail": f"{shim.detail}: {claude_shim}",
            "path": str(claude_shim),
        }
    )
    checks.append(
        _hook_check(
            name="claude_precompact",
            label="Claude PreCompact",
            config_path=runtime_home / ".claude" / "settings.json",
            expected_suffix=".claude/hooks/smart-trim.py",
            cascade_budget_seconds=cascade_budget_seconds,
            broken_level="fail",
        )
    )

    codex_config = runtime_home / ".codex" / "hooks.json"
    if _is_file(codex_config):
        codex_shim = runtime_home / ".codex" / "hooks" / "smart-trim.py"
        shim = inspect_shim(codex_shim)
        checks.append(
            {
                "level": "ok" if shim.ok else "warn",
                "name": "codex_shim",
                "detail": f"{shim.detail}: {codex_shim}",
                "path": str(codex_shim),
            }
        )
        checks.append(
            _hook_check(
                name="codex_precompact",
                label="Codex PreCompact",
                config_path=codex_config,
                expected_suffix=".codex/hooks/smart-trim.py",
                cascade_budget_seconds=cascade_budget_seconds,
                broken_level="warn",
            )
        )

    return checks
