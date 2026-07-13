"""Read-side grounding: load agent memory + objective registry to anchor the summary.

Loads currentTask / recent progress / previous activeContext from the project's
``.memory-bank/`` so a compact preserves the real objective and verified state
instead of drifting. Also surfaces the shared ``current-objective.json`` registry
when it is fresh and belongs to this project.

The freshness filter comes from the installed ``agent_memory`` package. It is
optional at runtime: an unavailable or broken installation degrades to the raw
memory-bank lines instead of blocking compaction.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from smart_trim.shared.config import NEGATIVE_CONSTRAINT_RE
from smart_trim.shared.paths import redact_sensitive
from smart_trim.shared.timeutil import hours_since_iso, objective_injection_window_hours

try:
    from agent_memory.features.entries import (  # pyright: ignore[reportMissingImports]
        command as _agent_memory_entries,
    )
except Exception:  # pragma: no cover - optional environment dependency
    _agent_memory_entries = None  # type: ignore[assignment]

_RUNTIME_CONSTRAINT_NOISE_RE = re.compile(
    r"("
    r"\[(?:FUSION_PANEL|CODEX_WORKER|NO_DELEGATE|NO_TOOLS|NO_SWARM)\]|"
    r"POST-COMPACT RULES|"
    r"DO NOT re-read files you already know|"
    r"DO NOT read screenshots/images|"
    r"DO NOT re-read rules files|"
    r"Use grep/find to locate|"
    r"Work from this summary|"
    r"No session JSONL available|"
    r"Reload from \w+ memory bank|"
    r"You are a deliberation panelist|"
    r"Do NOT use tools, APIs, or further delegation|"
    r"Response style:"
    r")",
    re.IGNORECASE,
)


def load_memory_grounding(project_root: Path) -> str:
    """Load compact grounding from the agent memory bank (see module docstring)."""
    bank = project_root / ".memory-bank"
    if not bank.is_dir():
        return ""
    parts: list[str] = []
    _add_section(parts, bank / "currentTask.md", "Current Task (from currentTask.md)", 1500, False)
    _add_section(parts, bank / "progress.md", "Recent Progress (from progress.md)", 1000, True)
    _add_section(
        parts, bank / "activeContext.md", "Previous Handoff (from activeContext.md)", 800, True
    )
    return "\n\n".join(parts)


def _add_section(parts: list[str], path: Path, title: str, max_chars: int, from_end: bool) -> None:
    if not path.exists():
        return
    lines = _filtered_memory_lines(path.name, path)
    if not lines:
        return
    text = _take_chars(lines, max_chars, from_end=from_end)
    parts.append(f"## {title}\n{redact_sensitive(text)}")


def _filtered_memory_lines(name: str, path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if _agent_memory_entries is not None:
        try:
            return _agent_memory_entries.filter_lines_for_injection(name, lines)
        except Exception:
            return lines
    return lines


def _take_chars(lines: list[str], max_chars: int, *, from_end: bool = False) -> str:
    text = "\n".join(lines).strip()
    if from_end:
        return text[-max_chars:]
    return text[:max_chars]


def extract_negative_constraints(text: str, max_items: int = 8) -> str:
    """Preserve explicit prohibitions that generic summaries tend to drop."""
    items: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw.strip(" \t-*>`")).strip()
        if not _is_constraint_candidate(line):
            continue
        safe = redact_sensitive(line)[:220]
        key = safe.lower()
        if safe and key not in seen:
            items.append(safe)
            seen.add(key)
        if len(items) >= max_items:
            break
    if not items:
        return ""
    return "## Preserved Negative Constraints\n" + "\n".join(f"- {item}" for item in items)


def _is_constraint_candidate(line: str) -> bool:
    if not line or len(line) < 8 or len(line) > 260:
        return False
    if _RUNTIME_CONSTRAINT_NOISE_RE.search(line):
        return False
    return bool(NEGATIVE_CONSTRAINT_RE.search(line))


def load_objective_registry(project_root: Path) -> str:
    """Load the shared objective registry so compaction preserves task focus.

    The agentic-cycle-router writes ~/.claude/state/current-objective.json when
    the engineering cycle activates. Include it in the handoff so the next
    session knows the current task, acceptance criteria, and next step.
    """
    obj_file = Path.home() / ".claude" / "state" / "current-objective.json"
    if not obj_file.exists():
        return ""
    try:
        data = json.loads(obj_file.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict) or _objective_stale_for_injection(data):
        return ""
    recorded_root = str(data.get("project_root", "")).strip()
    if recorded_root and not _same_or_nested_project(recorded_root, project_root):
        return ""
    return _render_objective(data)


def _objective_stale_for_injection(data: dict[str, Any]) -> bool:
    """Hide stale global objectives from compact summaries without deleting them."""
    state = str(data.get("status") or data.get("phase") or "").strip().lower()
    if state in {"done", "complete", "completed", "shipped", "closed", "archived"}:
        return True
    task_guidance = data.get("task_guidance")
    guidance_updated = task_guidance.get("updated_at") if isinstance(task_guidance, dict) else ""
    updated_at = str(data.get("updated_at") or guidance_updated or "")
    age = hours_since_iso(updated_at)
    if age is None:
        return True
    return age > objective_injection_window_hours()


def _render_objective(data: dict[str, Any]) -> str:
    task = str(data.get("task", "")).strip()
    next_step = str(data.get("next", "")).strip()
    if not task and not next_step:
        return ""
    lines = ["## Current Objective (from current-objective.json)"]
    if task:
        lines.append(f"**Task**: {redact_sensitive(task[:500])}")
    phase = str(data.get("phase", "")).strip()
    if phase:
        lines.append(f"**Phase**: {phase}")
    acceptance = str(data.get("acceptance", "")).strip()
    if acceptance:
        lines.append(f"**Acceptance**: {redact_sensitive(acceptance[:500])}")
    if next_step:
        lines.append(f"**Next**: {redact_sensitive(next_step[:500])}")
    files = data.get("files", [])
    files_str = ", ".join(str(f) for f in files if f) if isinstance(files, list) else str(files)
    if files_str:
        lines.append(f"**Files**: {redact_sensitive(files_str[:500])}")
    return "\n".join(lines)


def _same_or_nested_project(recorded_root: str, project_root: Path) -> bool:
    """True when ``current`` equals ``recorded_root`` or is nested under it.

    Worktree sessions (cwd in a subdirectory of the original project) must still
    see the shared objective — the previous equality-only check silently dropped
    those and forced the agent to re-discover context after every compact.
    """
    if not recorded_root:
        return False
    try:
        recorded = Path(recorded_root).expanduser().resolve()
        current = project_root.expanduser().resolve()
    except (OSError, ValueError):
        return False
    # ``relative_to`` succeeds iff ``current`` is ``recorded`` or nested under it.
    try:
        current.relative_to(recorded)
        return True
    except ValueError:
        return False


__all__ = [
    "load_memory_grounding",
    "extract_negative_constraints",
    "load_objective_registry",
]
