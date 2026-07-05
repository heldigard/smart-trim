"""LLM summarization cascade (quality-ordered, privacy-first).

Chain:
  1. Ollama SetneufPT/Qwopus3.5-4B-Coder-MTP (LOCAL, ~3s) — PRIMARY (smart_trim combined #1, re-bench 2026-07-04)
  2. Ollama qwen3.5:4b (LOCAL, ~5s, universal anchor) — SECONDARY
  3. cheap_llm cascade -> DeepSeek (CLOUD, secret-scrubbed) — TERTIARY

Each tier returns ``None`` on failure so the caller falls through. Cloud tier
only runs when both local tiers are down — keeps most summaries on-machine.
"""

import os

from smart_trim.shared import compat
from smart_trim.shared.config import OLLAMA_BASE, OLLAMA_TIMEOUT_SECONDS

_SYSTEM_PROMPT = (
    "You are a context compression expert. Max 280 words. "
    "Preserve file paths, errors, decisions verbatim. "
    "Use the provided TASK/PROGRESS grounding to keep focus. Discard filler."
)

# Re-bench 2026-07-04 (Ollama 0.31.1): SetneufPT/Qwopus3.5-4B-Coder-MTP is
# smart_trim combined #1 (deep 7.00 + tie-break 10.50 — perfect; 174 tok/s,
# 2.8GB VRAM, no think-leak). qwen3.5:4b (was PRIMARY) is the universal anchor
# — always installed, clean output — so it stays as the always-available fallback.
_PRIMARY_MODEL = os.environ.get(
    "SMART_TRIM_PRIMARY_MODEL", "SetneufPT/Qwopus3.5-4B-Coder-MTP_Q4_64k_8GB-GPU"
)
_SECONDARY_MODEL = os.environ.get("SMART_TRIM_SECONDARY_MODEL", "qwen3.5:4b")


def get_summary_prompt(context: str, grounding: str = "") -> str:
    """Generate the prompt for LLM summarization."""
    grounding_block = f"\n{grounding}\n\n" if grounding.strip() else ""
    return f"""Compress this conversation into a compact handoff. MAX 280 words. Preserve ONLY:

1. Exact FILE PATHS (absolute, with :line if available)
2. ERROR MESSAGES (verbatim)
3. Architectural DECISIONS + rationale
4. Code CHANGES made (file:line format)
5. Acceptance criteria / verified state
6. What's PENDING next

DISCARD: pleasantries, explanations, repeated info, verbose tool output details.
{grounding_block}CONVERSATION:
{context}

Format:
**Task**: [one sentence]
**Acceptance**: [criteria or definition of done]
**Verified**: [what has been tested/confirmed]
**Current**: [in-progress work]
**Errors**: [verbatim if any]
**Decisions**: [key choices]
**Next**: [immediate next steps]
**Files**: [list of all files touched]"""


def summarize_ollama(context: str, model: str, grounding: str = "") -> str | None:
    """Summarize using an Ollama local model (via shared ollama_client.chat)."""
    if compat.ollama_client is None:
        return None
    prompt = get_summary_prompt(context, grounding=grounding)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        # cache=False: PreCompact payloads are large and rarely identical; avoid
        # storing multi-KB summaries in the shared generation cache.
        # num_ctx=32768: a compacting session can exceed the model's default 8K
        # window; without this, smaller-ctx models return empty (done_reason=length).
        return compat.ollama_client.chat(
            messages,
            model=model,
            temperature=0.2,
            num_predict=600,
            think=False,
            base_url=OLLAMA_BASE,
            cache=False,
            num_ctx=32768,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    except compat.ollama_client.OllamaUnavailable:
        return None


def summarize_primary(context: str, grounding: str = "") -> str | None:
    """PRIMARY: Ollama SetneufPT/Qwopus3.5-4B-Coder-MTP (smart_trim combined #1,
    re-bench 2026-07-04: deep 7.00 + tie-break 10.50 — perfect; longctx/reason
    winner 2026-06-28: 9/10 facts, 174 tok/s, 2.8GB VRAM, no think-leak).

    carstenuhlig/omnicoder-9b demoted 2026-06-27: reasoning model that burns its
    token budget on a 'Thinking Process:' preamble (think=False) or returns EMPTY
    (think=True). qwen3.5:4b (the prior PRIMARY) is now the universal-anchor
    SECONDARY — slightly lower smart_trim rank, but always installed + clean.
    """
    return summarize_ollama(context, _PRIMARY_MODEL, grounding=grounding)


def summarize_secondary(context: str, grounding: str = "") -> str | None:
    """SECONDARY: Ollama qwen3.5:4b (universal clean anchor, ~5s, 3.4GB VRAM) —
    always-installed fallback when the SetneufPT tag is missing or fails."""
    return summarize_ollama(context, _SECONDARY_MODEL, grounding=grounding)


def primary_label() -> str:
    """Stable, env-aware label for the PRIMARY tier (drives the `method` field).

    Derived from ``_PRIMARY_MODEL`` so an env override changes the label
    alongside the model, keeping ``.memory-bank/activeContext.md`` truthful.
    Quantization suffixes (``_Q4_..._8GB-GPU`` etc.) are stripped — they
    encode VRAM hints, not identity.
    """
    return f"ollama-{_normalize_model_for_label(_PRIMARY_MODEL)}"


def secondary_label() -> str:
    """Stable, env-aware label for the SECONDARY tier (drives the `method` field)."""
    return f"ollama-{_normalize_model_for_label(_SECONDARY_MODEL)}"


# Quantization / VRAM-hint suffixes that vary per-host and must NOT appear in
# the persisted method label (they identify the *host*, not the *model*).
_QUANT_SUFFIXES = (
    "_Q4_64k_8GB-GPU",
    "_Q4_K_M",
    "_Q4_K_S",
    "_Q5_K_M",
    "_Q8_0",
    "_Q4_0",
)


def _normalize_model_for_label(model: str) -> str:
    """Strip a trailing quantization suffix; return the bare model tag."""
    for suffix in _QUANT_SUFFIXES:
        if model.endswith(suffix):
            return model[: -len(suffix)]
    return model


def summarize_cloud_cascade(context: str, grounding: str = "") -> str | None:
    """TERTIARY: cheap_llm cloud cascade (secret-scrubbed, cross-provider failover).

    Only called when BOTH local Ollama models are unavailable. Context is scrubbed
    of secrets before leaving the machine. Returns None if all cloud tiers fail
    (caller falls to rule-based).
    """
    if compat.cheap_complete is None:
        return None
    prompt = get_summary_prompt(context, grounding=grounding)
    try:
        result = compat.cheap_complete(
            system=_SYSTEM_PROMPT,
            prompt=prompt,
            schema_hint=None,
            timeout_total=45.0,  # DeepSeek 1M ctx on a large context needs headroom
            prefer_local=False,  # local primary+secondary already tried upstream
            require_json=False,  # summary is free text, not JSON
            cloud_model="deepseek/deepseek-v4-flash",  # judgment tier
        )
        text = result.get("text", "").strip()
        if text and len(text) > 50:
            return text
    except Exception:
        pass
    return None


__all__ = [
    "get_summary_prompt",
    "summarize_ollama",
    "summarize_primary",
    "summarize_secondary",
    "summarize_cloud_cascade",
    "primary_label",
    "secondary_label",
]
