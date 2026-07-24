"""``doctor`` — one-shot health check for the smart-trim runtime.

``smoke`` proves the offline fallback path end-to-end, but it cannot tell
whether the LLM tier is actually wired (Ollama up, primary/secondary models
pulled). ``doctor`` fills that gap on a fresh native-Ubuntu install: it probes
the local Ollama ``/api/tags``, confirms the cascade models are installed,
verifies the optional ``agent-memory`` import, checks cascade helpers
(``ollama_client`` / ``cheap_complete``), the PreCompact shim path, and that
the Claude/Codex hook wiring and timeout, the memory bank + summary archive are
writable, and the cascade budget is sane.

Zero non-stdlib dependencies (``urllib`` only). Runs solely on explicit
``smart-trim doctor`` invocation — never on the PreCompact hook path.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, TextIO
from urllib.error import URLError
from urllib.request import Request, urlopen

from smart_trim.features.diagnostics import wiring as _wiring
from smart_trim.features.summarize import command as _summarize
from smart_trim.shared import paths as _paths
from smart_trim.shared.config import CASCADE_BUDGET_SECONDS, CASCADE_MIN_TIER_SECONDS, OLLAMA_BASE

_OK = "[OK]  "
_WARN = "[WARN]"
_FAIL = "[FAIL]"


def _ollama_installed_models(timeout: float = 2.0) -> set[str] | None:
    """Return installed Ollama model tags, or ``None`` if the endpoint is unreachable.

    ``None`` (not an empty set) means "could not reach Ollama", so the caller can
    distinguish "reachable but no models" from "daemon down".
    """
    try:
        req = Request(f"{OLLAMA_BASE}/api/tags", headers={"Accept": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (URLError, OSError, ValueError):
        return None
    models = payload.get("models", []) if isinstance(payload, dict) else []
    return {str(m["name"]) for m in models if isinstance(m, dict) and m.get("name")}


def _agent_memory_available() -> bool:
    """True if the optional ``agent-memory`` package imports (grounding freshness)."""
    try:
        import importlib

        importlib.import_module("agent_memory")
    except Exception:
        return False
    return True


def _cascade_helpers() -> dict[str, bool]:
    """Report which harness helpers ``shared.compat`` resolved in this process."""
    # Import inside the probe so doctor stays lazy for unit tests that only
    # exercise Ollama/fs checks; compat already ran on package import.
    from smart_trim.shared import compat as _compat

    return {
        "ollama_client": _compat.ollama_client is not None,
        "cheap_complete": _compat.cheap_complete is not None,
        "cg_reset": _compat.cg_reset is not None,
    }


def _dir_writable(path: Path) -> bool:
    """True if a temp probe file can be created and removed inside ``path``."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path, prefix=".doctor-", suffix=".tmp")
        os.close(fd)
        Path(name).unlink()
    except OSError:
        return False
    return True


def collect_checks(project_root: Path | None = None) -> dict[str, Any]:
    """Run every probe and return a machine-readable report (no I/O to streams)."""
    root = project_root or _paths.get_project_root()
    checks: list[dict[str, Any]] = []

    def add(level: str, name: str, detail: str, **extra: Any) -> None:
        row: dict[str, Any] = {"level": level, "name": name, "detail": detail}
        row.update(extra)
        checks.append(row)

    installed = _ollama_installed_models()
    primary = _summarize.primary_model()
    secondary = _summarize.secondary_model()
    if installed is None:
        add("warn", "ollama", "unreachable — cascade degrades to cloud/rule-based")
    else:
        add("ok", "ollama", "reachable", models=sorted(installed)[:20])
        add(
            "ok" if primary in installed else "warn",
            "primary_model",
            primary,
            installed=primary in installed,
        )
        add(
            "ok" if secondary in installed else "warn",
            "secondary_model",
            secondary,
            installed=secondary in installed,
        )

    am_ok = _agent_memory_available()
    add(
        "ok" if am_ok else "warn",
        "agent_memory",
        (
            "importable (freshness filter)"
            if am_ok
            else "not importable in this Python — install agent-memory into this env "
            f"({sys.executable}); hook may still see it via system site-packages"
        ),
    )

    helpers = _cascade_helpers()
    for key, ok in helpers.items():
        add(
            "ok" if ok else "warn",
            f"helper_{key}",
            "available" if ok else "missing — local/cloud cascade tier degraded",
        )

    checks.extend(_wiring.collect_runtime_checks(CASCADE_BUDGET_SECONDS))

    memory_dir = root / ".memory-bank"
    mem_ok = _dir_writable(memory_dir)
    add(
        "ok" if mem_ok else "fail",
        "memory_bank",
        f"{'writable' if mem_ok else 'unwritable'}: {memory_dir}",
        path=str(memory_dir),
    )

    archive = _paths.default_summaries_dir()
    arch_ok = _dir_writable(archive)
    add(
        "ok" if arch_ok else "warn",
        "summary_archive",
        f"{'writable' if arch_ok else 'unwritable'}: {archive}",
        path=str(archive),
    )

    if CASCADE_BUDGET_SECONDS <= CASCADE_MIN_TIER_SECONDS:
        add(
            "fail",
            "cascade_budget",
            f"{CASCADE_BUDGET_SECONDS}s <= min tier {CASCADE_MIN_TIER_SECONDS}s — no tier can run",
        )
    else:
        add(
            "ok",
            "cascade_budget",
            f"{CASCADE_BUDGET_SECONDS}s > min tier {CASCADE_MIN_TIER_SECONDS}s",
        )

    failures = sum(1 for c in checks if c["level"] == "fail")
    warnings = sum(1 for c in checks if c["level"] == "warn")
    return {
        "command": "doctor",
        "schema_version": 1,
        "project": str(root),
        "python": sys.executable,
        "ollama_endpoint": OLLAMA_BASE,
        "checks": checks,
        "failures": failures,
        "warnings": warnings,
        "ok": failures == 0,
    }


def run_doctor(
    project_root: Path | None = None,
    *,
    stream: TextIO | None = None,
    as_json: bool = False,
) -> int:
    """Run every health check; print one status line per check (or JSON).

    Returns ``1`` if any check FAILs (the hook's core persist function is
    broken), ``0`` otherwise. WARNs (graceful degradation — Ollama down, a model
    not pulled, ``agent-memory`` missing) do not fail the doctor, because the
    cascade still produces a handoff via cloud or rule-based fallback.

    ``stream`` defaults to stdout and is injectable for tests.
    """
    report = collect_checks(project_root)
    out = stream or sys.stdout
    if as_json:
        out.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
        return 0 if report["ok"] else 1

    level_tag = {"ok": _OK, "warn": _WARN, "fail": _FAIL}
    out.write(f"smart-trim doctor (project: {report['project']})\n")
    out.write(f"  python: {report['python']}\n")
    out.write(f"  ollama endpoint: {report['ollama_endpoint']}\n")
    for check in report["checks"]:
        tag = level_tag.get(check["level"], _WARN)
        name = check["name"].replace("_", " ")
        out.write(f"  {tag} {name}: {check['detail']}\n")
    out.write(f"Result: {report['failures']} failure(s), {report['warnings']} warning(s)\n")
    return 0 if report["ok"] else 1


__all__ = ["collect_checks", "run_doctor"]
