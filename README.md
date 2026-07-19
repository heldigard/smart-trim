# smart-trim

LLM-powered **PreCompact** context-compression hook for Claude Code, with
Codex-compatible payload aliases. Compresses
the active session into a compact handoff (`Task / Acceptance / Verified /
Current / Errors / Decisions / Next / Files`) grounded in the agent memory
bank, so compaction preserves the real objective instead of drifting.

**Privacy-first**: primary + secondary summarization run on **local Ollama**
(no data leaves the machine). Cloud (`cheap_llm` cascade, secret-scrubbed) is
tier-3, reached only when both local models are down. Rule-based extraction is
the always-succeeds fallback.

## Fallback chain (quality-optimized)

1. Ollama `batiai/gemma4-e2b:q4` (local) — PRIMARY (`SMART_TRIM_PRIMARY_MODEL`, risk-weighted smart_trim #1, 2026-07-09)
2. Ollama `cryptidbleh/gemma4-claude-opus-4.6:latest` (local) — SECONDARY (`SMART_TRIM_SECONDARY_MODEL`)
3. `cheap_llm` cascade → DeepSeek (cloud, secret-scrubbed) — TERTIARY
4. Rule-based extraction (deterministic, ~0s) — FALLBACK

## Architecture

Vertical-slice package (`src/smart_trim/{shared,features}/`), graduated from a
1114-line monolith. See `CLAUDE.md`. Entry point is the thin shim
`~/.claude/hooks/smart-trim.py`.

The `smart-trim` console entry is an operational surface for capabilities,
version checks, smoke tests, a `doctor` health check, and hook-compatible
stdin; it does not replace the wired shim.

## Diagnostics

```bash
smart-trim --help          # usage (hook mode reads JSON on stdin)
smart-trim capabilities    # side effects, cost, degradation contract
smart-trim smoke           # synthetic PreCompact payload end-to-end (offline path)
smart-trim doctor          # Ollama reachability + cascade model install + writability
```

`smoke` proves the offline fallback; `doctor` verifies the LLM tier is wired
(Ollama up, primary/secondary models pulled via `/api/tags`, memory bank +
archive writable, cascade budget sane). Zero non-stdlib deps.

## Install (dev)

```bash
pip install -e ~/agent-memory
pip install -e ~/smart-trim
smart-trim --help
smart-trim capabilities --json
python3 -m pytest ~/smart-trim/tests/ -q
```

`agent-memory` supplies the freshness filter used when grounding a handoff from
`.memory-bank/`. The integration is fail-open: if the package is unavailable,
smart-trim keeps the raw memory lines and compaction continues.

## Wire (already wired — do not change)

`~/.claude/settings.json` → `"python3 ~/.claude/hooks/smart-trim.py"` on
`PreCompact`. Gemini reaches it via `~/.gemini/hooks/smart-trim.py` symlink;
Codex wires the same shim from `~/.codex/hooks.json`. When a runtime supplies
no transcript or live objective, the hook preserves the existing handoff
instead of overwriting it with an empty synthetic summary.

## Version

3.4.0 — adds the `doctor` health-check subcommand (native-Ubuntu LLM-tier
diagnostics) and closes coverage on the concurrency-critical file lock +
config input-validation helpers.

3.3.0 — vertical-slice split (was monolithic `smart-trim.py` v3.2).
