"""Help and capability discovery that never enters the compaction pipeline.

The ``smoke`` subcommand spawns the wired shim path
(``~/.claude/hooks/smart-trim.py``) with a synthetic PreCompact payload so
the smoke catches shim / sys.path / dependency drift alongside orchestrator
bugs — calling the in-process orchestrator directly would not.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
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
    {
        "name": "smoke",
        "purpose": "End-to-end hook smoke with a synthetic PreCompact payload.",
        "read_only": False,
        "destructive": False,
        "idempotent": True,
        "open_world": True,
        "cost": "fast",
        "writes": "temporary isolated memory bank only",
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
    return """usage: smart-trim [--help] [--version] [capabilities [--json]] [smoke]

PreCompact hook that preserves a grounded project handoff before context
compression. Normal hook mode reads one JSON event from stdin.

commands:
  capabilities          show side effects, cost, and degradation contract
  smoke                 run a synthetic PreCompact payload end-to-end (debug aid)

options:
  -h, --help            show this help
  --version             show package version

hook smoke:
  printf '{"trigger":"manual","sessionId":"smoke","cwd":"/project"}' | smart-trim
"""


def run_smoke(extra_env: dict[str, str] | None = None) -> int:
    """Run the wired shim with a synthetic payload and print OK/FAIL line.

    Returns the subprocess exit code. The synthetic payload carries
    ``sessionId="smoke"`` so the deterministic offline fallback path produces
    a minimal handoff without requiring a real Claude/Ollama session.
    """
    shim = Path.home() / ".claude" / "hooks" / "smart-trim.py"
    if not shim.is_file():
        print(f"[smoke] FAIL: shim not found at {shim}", file=sys.stderr)
        return 2
    env = dict(os.environ)
    env["SMART_TRIM_OBSERVABILITY"] = "0"
    if extra_env:
        env.update(extra_env)
    for name in ("CLAUDE_SESSION_FILE", "CLAUDE_SESSION_ID", "CLAUDE_PROJECT_DIR"):
        env.pop(name, None)
    try:
        with tempfile.TemporaryDirectory(prefix="smart-trim-smoke-") as temp_dir:
            smoke_root = Path(temp_dir)
            # A present terminal local objective suppresses the legacy global
            # objective fallback. The synthetic no-transcript path then skips
            # persistence, so smoke cannot overwrite a real project handoff.
            objective = smoke_root / ".memory-bank" / "control-plane" / "current-objective.json"
            objective.parent.mkdir(parents=True)
            objective.write_text('{"status":"completed"}', encoding="utf-8")
            payload = json.dumps(
                {"trigger": "manual", "sessionId": "smoke", "cwd": str(smoke_root)}
            )
            result = subprocess.run(
                [sys.executable, str(shim)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
    except subprocess.TimeoutExpired:
        print("[smoke] FAIL: hook timed out after 30s", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"[smoke] FAIL: {exc}", file=sys.stderr)
        return 4
    stdout = (result.stdout or "").strip()
    try:
        parsed = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        parsed = None
    if result.returncode != 0:
        print(f"[smoke] FAIL: exit={result.returncode}\n{result.stderr}", file=sys.stderr)
        return result.returncode or 1
    if not isinstance(parsed, dict) or "continue" not in parsed:
        print(f"[smoke] FAIL: unparseable stdout: {stdout[:200]!r}", file=sys.stderr)
        return 5
    print(f"[smoke] OK: continue={parsed.get('continue')} method={parsed.get('method', '-')}")
    return 0


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
    if args and args[0] == "smoke":
        raise SystemExit(run_smoke())
    return False


__all__ = ["CAPABILITIES", "capabilities_payload", "handle_cli", "help_text", "run_smoke"]
