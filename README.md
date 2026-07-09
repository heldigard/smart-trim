# smart-trim

LLM-powered **PreCompact** context-compression hook for Claude Code. Compresses
the active session into a compact handoff (`Task / Acceptance / Verified /
Current / Errors / Decisions / Next / Files`) grounded in the project memory
bank, so compaction preserves the real objective instead of drifting.

**Privacy-first**: primary + secondary summarization run on **local Ollama**
(no data leaves the machine). Cloud (`cheap_llm` cascade, secret-scrubbed) is
tier-3, reached only when both local models are down. Rule-based extraction is
the always-succeeds fallback.

## Fallback chain (quality-optimized)

1. Ollama `hf.co/HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced:Q4_K_M` (local) — PRIMARY (`SMART_TRIM_PRIMARY_MODEL`, smart_trim #1, 2026-07-08 PM)
2. Ollama `hf.co/SC117/gemma-4-12B-it-heretic-QAT-GGUF:UD-Q4_K_XL` (local) — SECONDARY (`SMART_TRIM_SECONDARY_MODEL`)
3. `cheap_llm` cascade → DeepSeek (cloud, secret-scrubbed) — TERTIARY
4. Rule-based extraction (deterministic, ~0s) — FALLBACK

## Architecture

Vertical-slice package (`src/smart_trim/{shared,features}/}`), graduated from a
1114-line monolith. See `CLAUDE.md`. Entry point is the thin shim
`~/.claude/hooks/smart-trim.py`.

## Install (dev)

```bash
pip install -e ~/smart-trim
python3 -m pytest ~/smart-trim/tests/ -q
```

## Wire (already wired — do not change)

`~/.claude/settings.json` → `"python3 ~/.claude/hooks/smart-trim.py"` on
`PreCompact`. Gemini reaches it via `~/.gemini/hooks/smart-trim.py` symlink.

## Version

3.3.0 — vertical-slice split (was monolithic `smart-trim.py` v3.2).
