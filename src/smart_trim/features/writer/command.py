"""Write-side: persist the compact handoff to the agent memory bank.

Writes ``.memory-bank/activeContext.md`` (reloaded by SessionStart) and appends
a deep-copy entry to ``.memory-bank/topics/session-handoffs.md``. Cross-project
sessions (file paths outside this bank's root) are routed to a
``foreign-sessions`` topic so the host activeContext stays clean.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from smart_trim.features.writer.active import (
    ACTIVE_AUTHORITY_LINE,
    ACTIVE_CONTEXT_MAX_LINES,
    atomic_write_text,
    mark_handoff_non_authoritative,
    render_active_fields,
)
from smart_trim.shared import filelock
from smart_trim.shared.paths import get_project_root, redact_sensitive, slugify


def update_agent_memory(
    summary: str,
    method: str,
    session_id: str = "unknown",
    project_root: Path | None = None,
) -> str:
    """Write compact and deep handoffs to the shared agent memory bank.

    Returns the persistence route so the hook message stays truthful:
    ``"active"`` (activeContext updated), ``"foreign"`` (routed to
    ``topics/foreign-sessions.md``), or ``"error"`` (best-effort write failed;
    compaction proceeds regardless).
    """
    try:
        project_root = project_root or get_project_root()
        memory_dir = project_root / ".memory-bank"
        memory_dir.mkdir(parents=True, exist_ok=True)
        safe_summary = mark_handoff_non_authoritative(redact_sensitive(summary))
        handoff_body = f"Method: {method}\nSession: {session_id}\n\n{safe_summary}"
        if _is_foreign_session(safe_summary, project_root):
            append_project_topic(memory_dir, "foreign-sessions", handoff_body)
            return "foreign"
        # Create the recovery target before publishing an active-context
        # pointer to it. If either write fails, the previous active handoff is
        # left intact by the outer best-effort boundary.
        append_project_topic(memory_dir, "session-handoffs", handoff_body)
        _write_active(memory_dir, safe_summary, method)
        return "active"
    except Exception:
        # Memory update is best-effort; never block compaction.
        return "error"


def _write_active(memory_dir: Path, safe_summary: str, method: str) -> None:
    active = memory_dir / "activeContext.md"
    lines = [
        "# Active Context",
        f"- {datetime.now().date()}: Smart trim summary ({method[:80]}).",
        ACTIVE_AUTHORITY_LINE,
    ]
    lines.extend(render_active_fields(safe_summary, lines))
    atomic_write_text(active, "\n".join(lines[:ACTIVE_CONTEXT_MAX_LINES]) + "\n")


def append_project_topic(memory_dir: Path, title: str, content: str) -> None:
    topics_dir = memory_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    topic = topics_dir / f"{slug}.md"
    with (
        topic.open("a+", encoding="utf-8") as handle,
        filelock.try_exclusive_lock(handle, timeout_seconds=0.25) as acquired,
    ):
        if not acquired:
            return
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(f"# {title}\n> Deep memory topic. Read on demand; keep entries factual.\n")
        handle.write(f"\n## {datetime.now().isoformat(timespec='seconds')}\n")
        handle.write(content.strip()[:4000] + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    update_topic_index(topics_dir, slug, title)


def update_topic_index(topics_dir: Path, slug: str, title: str) -> None:
    index = topics_dir / "_index.md"
    with (
        index.open("a+", encoding="utf-8") as handle,
        filelock.try_exclusive_lock(handle, timeout_seconds=0.25) as acquired,
    ):
        if not acquired:
            return
        handle.seek(0)
        content = handle.read()
        if not content:
            handle.write(
                "# Topic Index\n> Deep agent memory. Search/read on demand; "
                "do not load all topics by default.\n\n## Topics\n"
            )
        if f"({slug}.md)" not in content:
            handle.seek(0, os.SEEK_END)
            handle.write(f"- [{title}]({slug}.md)\n")
        handle.flush()
        os.fsync(handle.fileno())


# Harness/meta signals. The HOME meta bank is a catch-all for sessions launched
# from ~, so a home-rooted session is meta (not foreign) ONLY when its summary
# references the harness itself. Otherwise project work described by NAME (no
# absolute path) clobbers the shared meta activeContext. (Bug fixed 2026-07-13:
# an elogix Codex session run from home polluted the meta bank because its
# summary named the project without any absolute path.)
_META_SIGNALS = (
    ".claude",
    ".codex",
    ".gemini",
    ".kimi",
    ".qwen",
    ".opencode",
    "hooks/",
    "skills/",
    "rules/",
    "settings.json",
    "config.toml",
    "CLAUDE.md",
    "AGENTS.md",
    "agent-memory",
    "skill-router",
    "fusion-local",
    "fusion",
    "cli-orchestration",
    "cheap-llm",
    "prompt-improve",
    "smart-trim",
    "codeq",
    "codescan",
    "web-research",
    "ollama-client",
    "memory-bank",
)

# Parents whose immediate children are real project roots. Used to confirm a
# foreign session by project NAME when the summary carries no absolute path.
# Bounded to one readdir per parent; guarded so a slow/unmounted volume cannot
# block compaction.
_PROJECT_PARENTS = (
    "/mnt/ext4disk",
    "/mnt/ext4disk/ProyectosGP",
    "/mnt/ext4disk/ProyectosP",
    "/mnt/c/Users",
)


def _is_home_meta_bank(project_root: Path) -> bool:
    """True when the bank root IS the user home (the shared meta/home bank)."""
    try:
        return project_root.resolve() == Path.home().resolve()
    except OSError:
        return False


def _child_bank_name(child: Path) -> str | None:
    """Lowercased basename if ``child`` is a project dir with its own bank."""
    try:
        if child.is_dir() and (child / ".memory-bank").is_dir():
            return child.name.lower()
    except OSError:
        return None
    return None


def _known_project_names() -> set[str]:
    """Lowercased basenames of project dirs (outside $HOME) with their own bank."""
    names: set[str] = set()
    for parent in _PROJECT_PARENTS:
        pdir = Path(parent)
        if not pdir.is_dir():
            continue
        try:
            children = list(pdir.iterdir())
        except OSError:
            continue
        for child in children:
            name = _child_bank_name(child)
            if name:
                names.add(name)
    return names


def _is_foreign_session(summary: str, project_root: Path) -> bool:
    """True when the session touches files outside this bank's project root.

    Absolute-path detection first: if the summary carries any path and none fall
    under project_root, the session is foreign (e.g. working on
    /mnt/ext4disk/.../Elogix from a ~ host dir).

    Name/home guard: a HOME-rooted session (the shared meta bank) is foreign
    unless its summary references the harness. This stops project work described
    only by name from overwriting the meta activeContext.
    """
    try:
        root = str(project_root.resolve())
    except OSError:
        root = str(project_root)
    # Expand ~ and $HOME so a meta session editing ~/.claude/... is recognized as
    # inside the HOME root instead of extracting a misleading "/.claude/..." path.
    probe = summary.replace("~", str(Path.home())).replace("$HOME", str(Path.home()))
    paths = re.findall(r"/[A-Za-z0-9._/-]+\.[A-Za-z0-9]+", probe)
    paths += re.findall(r"[A-Za-z]:\\[A-Za-z0-9._\\-]+", probe)
    if paths:
        return not _any_path_under_root(paths, root)
    # No absolute paths. Only the HOME meta bank needs the extra guard: a normal
    # project bank is already scoped correctly by its directory.
    if not _is_home_meta_bank(project_root):
        return False
    low = summary.lower()
    if any(sig in low for sig in _META_SIGNALS):
        return False  # genuine harness/meta work launched from home
    if any(name and name in low for name in _known_project_names()):
        return True  # names a real project that has its own bank
    # Home-rooted, no path, no meta signal, no known project name: route to the
    # foreign topic rather than risk clobbering the shared meta activeContext.
    return True


def _any_path_under_root(paths: list[str], root: str) -> bool:
    norm_root = root
    for p in paths:
        pn = p.replace("\\", "/")
        if pn.startswith(norm_root + "/") or pn == norm_root:
            return True
    return False


__all__ = [
    "append_project_topic",
    "mark_handoff_non_authoritative",
    "update_agent_memory",
    "update_topic_index",
]
