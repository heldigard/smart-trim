"""Help and capability discovery that never enters the compaction pipeline."""

from __future__ import annotations

import json
from typing import Any

CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "name": "precompact",
        "purpose": "Create a grounded durable handoff before context compaction.",
        "read_only": False,
        "destructive": False,
        "idempotent": False,
        "open_world": True,
        "cost": "event-driven",
        "writes": ".memory-bank/activeContext.md plus bounded summary archive",
    },
    {
        "name": "capabilities",
        "purpose": "Describe smart-trim side effects and operating envelope.",
        "read_only": True,
        "destructive": False,
        "idempotent": True,
        "open_world": False,
        "cost": "cheap",
        "writes": "none",
    },
)


def capabilities_payload() -> dict[str, Any]:
    return {
        "command": "capabilities",
        "schema_version": 1,
        "hook_event": "PreCompact",
        "degradation": "local cascade -> optional cloud fallback -> deterministic summary",
        "capabilities": [dict(item) for item in CAPABILITIES],
    }


def help_text() -> str:
    return """usage: smart-trim [--help] [--version] [capabilities [--json]]

PreCompact hook that preserves a grounded project handoff before context
compression. Normal hook mode reads one JSON event from stdin.

commands:
  capabilities          show side effects, cost, and degradation contract

options:
  -h, --help            show this help
  --version             show package version

hook smoke:
  printf '{"trigger":"manual","sessionId":"smoke","cwd":"/project"}' | smart-trim
"""


def handle_cli(args: list[str]) -> bool:
    """Handle explicit discovery args; return False for normal hook mode."""
    if args in (["-h"], ["--help"]):
        print(help_text(), end="")
        return True
    if args and args[0] == "capabilities":
        payload = capabilities_payload()
        if "--json" in args[1:]:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print("name          ro  open  cost          writes  purpose")
            for item in CAPABILITIES:
                print(
                    f"{item['name']:<13} "
                    f"{'yes' if item['read_only'] else 'no':<3} "
                    f"{'yes' if item['open_world'] else 'no':<5} "
                    f"{item['cost']:<13} {item['writes']}  {item['purpose']}"
                )
        return True
    return False


__all__ = ["CAPABILITIES", "capabilities_payload", "handle_cli", "help_text"]
