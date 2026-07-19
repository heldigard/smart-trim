"""``doctor`` — one-shot health check for the smart-trim runtime.

``smoke`` proves the offline fallback path end-to-end, but it cannot tell
whether the LLM tier is actually wired (Ollama up, primary/secondary models
pulled). ``doctor`` fills that gap on a fresh native-Ubuntu install: it probes
the local Ollama ``/api/tags``, confirms the cascade models are installed,
verifies the optional ``agent-memory`` import, and checks that the memory bank
+ summary archive are writable and the cascade budget is sane.

Zero non-stdlib dependencies (``urllib`` only). Runs solely on explicit
``smart-trim doctor`` invocation — never on the PreCompact hook path.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import TextIO
from urllib.error import URLError
from urllib.request import Request, urlopen

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


def run_doctor(project_root: Path | None = None, *, stream: TextIO | None = None) -> int:
    """Run every health check; print one status line per check.

    Returns ``1`` if any check FAILs (the hook's core persist function is
    broken), ``0`` otherwise. WARNs (graceful degradation — Ollama down, a model
    not pulled, ``agent-memory`` missing) do not fail the doctor, because the
    cascade still produces a handoff via cloud or rule-based fallback.

    ``stream`` defaults to stdout and is injectable for tests.
    """
    out = stream or sys.stdout
    root = project_root or _paths.get_project_root()
    failures = 0
    warnings = 0

    def emit(level: str, message: str) -> None:
        nonlocal failures, warnings
        out.write(f"  {level} {message}\n")
        if level == _FAIL:
            failures += 1
        elif level == _WARN:
            warnings += 1

    out.write(f"smart-trim doctor (project: {root})\n")
    out.write(f"  ollama endpoint: {OLLAMA_BASE}\n")

    installed = _ollama_installed_models()
    primary = _summarize.primary_model()
    secondary = _summarize.secondary_model()
    if installed is None:
        emit(_WARN, "ollama unreachable — cascade degrades to cloud/rule-based")
    else:
        emit(_OK, "ollama reachable")
        emit(_OK if primary in installed else _WARN, f"primary model installed: {primary}")
        emit(_OK if secondary in installed else _WARN, f"secondary model installed: {secondary}")

    emit(
        _OK if _agent_memory_available() else _WARN,
        "agent-memory importable (freshness filter)",
    )

    memory_dir = root / ".memory-bank"
    # memory-bank unwritable defeats the hook's core purpose (persisting the
    # handoff) — the only hard FAIL besides a self-defeating cascade budget.
    emit(_OK if _dir_writable(memory_dir) else _FAIL, f"memory-bank writable: {memory_dir}")

    archive = _paths.default_summaries_dir()
    emit(_OK if _dir_writable(archive) else _WARN, f"summary archive writable: {archive}")

    if CASCADE_BUDGET_SECONDS <= CASCADE_MIN_TIER_SECONDS:
        emit(
            _FAIL,
            f"cascade budget {CASCADE_BUDGET_SECONDS}s <= min tier {CASCADE_MIN_TIER_SECONDS}s"
            " — no tier can run",
        )
    else:
        emit(
            _OK,
            f"cascade budget {CASCADE_BUDGET_SECONDS}s > min tier {CASCADE_MIN_TIER_SECONDS}s",
        )

    out.write(f"Result: {failures} failure(s), {warnings} warning(s)\n")
    return 1 if failures else 0


__all__ = ["run_doctor"]
