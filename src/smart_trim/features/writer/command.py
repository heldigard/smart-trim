"""Write-side: persist the compact handoff to the project memory bank.

Writes ``.memory-bank/activeContext.md`` (reloaded by SessionStart) and appends
a deep-copy entry to ``.memory-bank/topics/session-handoffs.md``. Cross-project
sessions (file paths outside this bank's root) are routed to a
``foreign-sessions`` topic so the host activeContext stays clean.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from smart_trim.shared.paths import get_project_root, redact_sensitive, slugify


def update_project_memory(
    summary: str,
    method: str,
    session_id: str = "unknown",
    project_root: Path | None = None,
) -> None:
    """Write compact and deep handoffs to the shared project memory bank."""
    try:
        project_root = project_root or get_project_root()
        memory_dir = project_root / ".memory-bank"
        memory_dir.mkdir(parents=True, exist_ok=True)
        safe_summary = redact_sensitive(summary)
        handoff_body = f"Method: {method}\nSession: {session_id}\n\n{safe_summary}"
        if _is_foreign_session(safe_summary, project_root):
            _append_topic(memory_dir, "foreign-sessions", handoff_body)
            return
        _write_active(memory_dir, safe_summary, method)
        _append_topic(memory_dir, "session-handoffs", handoff_body)
    except Exception:
        # Memory update is best-effort; never block compaction.
        pass


def _write_active(memory_dir: Path, safe_summary: str, method: str) -> None:
    active = memory_dir / "activeContext.md"
    compact = re.sub(r"\n{3,}", "\n\n", safe_summary.strip())[:1200]
    lines = [
        "# Active Context",
        f"- {datetime.now().date()}: Smart trim summary ({method}).",
    ]
    for line in compact.splitlines():
        line = line.strip()
        if line:
            lines.append(f"- {line[:180]}")
        if len(lines) >= 28:
            break
    active.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_topic(memory_dir: Path, title: str, content: str) -> None:
    """Append to ``topics/<slug>.md`` + register in ``topics/_index.md``.

    Thin wrapper around append_project_topic kept for the foreign/handoff split.
    """
    append_project_topic(memory_dir, title, content)


def append_project_topic(memory_dir: Path, title: str, content: str) -> None:
    topics_dir = memory_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(title)
    topic = topics_dir / f"{slug}.md"
    if not topic.exists():
        topic.write_text(
            f"# {title}\n> Deep memory topic. Read on demand; keep entries factual.\n",
            encoding="utf-8",
        )
    update_topic_index(topics_dir, slug, title)
    with topic.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {datetime.now().isoformat(timespec='seconds')}\n")
        handle.write(content.strip()[:4000] + "\n")


def update_topic_index(topics_dir: Path, slug: str, title: str) -> None:
    index = topics_dir / "_index.md"
    if not index.exists():
        index.write_text(
            "# Topic Index\n> Deep project memory. Search/read on demand; "
            "do not load all topics by default.\n\n## Topics\n",
            encoding="utf-8",
        )
    content = index.read_text(encoding="utf-8", errors="replace")
    if f"({slug}.md)" not in content:
        with index.open("a", encoding="utf-8") as handle:
            handle.write(f"- [{title}]({slug}.md)\n")


def _is_foreign_session(summary: str, project_root: Path) -> bool:
    """True when the session touches files outside this bank's project root.

    Extract absolute paths from the summary. If at least one path exists and NONE
    fall under project_root, the session is foreign (e.g. working on
    /mnt/wsl/.../Elogix from a ~ host dir). Sessions with no paths (conceptual
    work) are treated as host-local — keep writing them.
    """
    try:
        root = str(project_root.resolve())
    except OSError:
        root = str(project_root)
    paths = re.findall(r"/[A-Za-z0-9._/-]+\.[A-Za-z0-9]+", summary)
    paths += re.findall(r"[A-Za-z]:\\[A-Za-z0-9._\\-]+", summary)
    if not paths:
        return False
    return not _any_path_under_root(paths, root)


def _any_path_under_root(paths: list[str], root: str) -> bool:
    norm_root = root
    for p in paths:
        pn = p.replace("\\", "/")
        if pn.startswith(norm_root + "/") or pn == norm_root:
            return True
    return False


__all__ = ["update_project_memory", "append_project_topic", "update_topic_index"]
