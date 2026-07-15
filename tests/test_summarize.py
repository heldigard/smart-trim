"""Tests for features/summarize."""

from __future__ import annotations

from smart_trim.features.summarize import command as summarize
from smart_trim.shared import compat

# --- get_summary_prompt ------------------------------------------------------


def test_prompt_includes_grounding_when_present():
    p = summarize.get_summary_prompt("ctx", grounding="## Current Task\nfix bug")
    assert "## Current Task" in p
    assert "CONVERSATION:" in p
    assert "ctx" in p


def test_prompt_omits_grounding_block_when_empty():
    p = summarize.get_summary_prompt("ctx", grounding="")
    assert "ctx" in p
    # No stray leading grounding block
    assert "Format:" in p


def test_prompt_has_required_handoff_sections():
    p = summarize.get_summary_prompt("ctx")
    for section in ("**Task**:", "**Acceptance**:", "**Next**:", "**Files**:"):
        assert section in p


# --- summarize_ollama --------------------------------------------------------


class _FakeOllamaUnavailable(Exception):
    pass


class _FakeOllamaClient:
    OllamaUnavailable = _FakeOllamaUnavailable

    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        if self.exc:
            raise self.exc
        return self.result


def test_summarize_ollama_none_when_client_missing(monkeypatch):
    monkeypatch.setattr(compat, "ollama_client", None)
    assert summarize.summarize_ollama("ctx", "model") is None


def test_summarize_ollama_returns_client_output(monkeypatch):
    fake = _FakeOllamaClient(result="compressed handoff")
    monkeypatch.setattr(compat, "ollama_client", fake)
    out = summarize.summarize_ollama("ctx", "qwen3.5:4b", grounding="g")
    assert out == "compressed handoff"
    call = fake.calls[0]
    assert call["model"] == "qwen3.5:4b"
    assert call["think"] is False
    assert call["cache"] is False
    assert call["num_ctx"] == 65536
    assert call["num_predict"] == summarize.SUMMARY_NUM_PREDICT == 384


def test_summarize_ollama_num_ctx_env_override(monkeypatch):
    """SMART_TRIM_NUM_CTX overrides the context window (RTX 5080 headroom)."""
    fake = _FakeOllamaClient(result="ok")
    monkeypatch.setattr(compat, "ollama_client", fake)
    monkeypatch.setattr(summarize, "_NUM_CTX", 98304)
    summarize.summarize_ollama("ctx", "qwen3.5:4b")
    assert fake.calls[0]["num_ctx"] == 98304


def test_num_ctx_invalid_env_falls_back_to_default(monkeypatch):
    """A bad SMART_TRIM_NUM_CTX must not crash the hook on import (fail-open)."""
    import importlib

    monkeypatch.setenv("SMART_TRIM_NUM_CTX", "not-a-number")
    try:
        importlib.reload(summarize)
        assert summarize._NUM_CTX == 65536
    finally:
        monkeypatch.delenv("SMART_TRIM_NUM_CTX", raising=False)
        importlib.reload(summarize)


def test_summarize_ollama_swallows_unavailable(monkeypatch):
    fake = _FakeOllamaClient(exc=_FakeOllamaUnavailable("down"))
    monkeypatch.setattr(compat, "ollama_client", fake)
    assert summarize.summarize_ollama("ctx", "m") is None


def test_summarize_ollama_swallows_unexpected_client_error(monkeypatch):
    fake = _FakeOllamaClient(exc=RuntimeError("malformed local response"))
    monkeypatch.setattr(compat, "ollama_client", fake)

    assert summarize.summarize_ollama("ctx", "m") is None


# --- summarize_primary / secondary ------------------------------------------


def test_summarize_primary_uses_batiai_e2b_model(monkeypatch):
    """Round-15 cross-validation: batiai-e2b (11.67) beats SC117 (10.79) on score."""
    fake = _FakeOllamaClient(result="ok")
    monkeypatch.setattr(compat, "ollama_client", fake)
    summarize.summarize_primary("ctx")
    assert fake.calls[0]["model"] == "batiai/gemma4-e2b:q4"


def test_summarize_secondary_uses_cryptidbleh_model(monkeypatch):
    """Round-15 cross-validation runner-up: cryptidbleh (11.63) as fidelity fallback."""
    fake = _FakeOllamaClient(result="ok")
    monkeypatch.setattr(compat, "ollama_client", fake)
    summarize.summarize_secondary("ctx")
    assert fake.calls[0]["model"] == "cryptidbleh/gemma4-claude-opus-4.6:latest"


# --- summarize_cloud_cascade ------------------------------------------------


def test_cloud_cascade_none_when_cheap_complete_missing(monkeypatch):
    monkeypatch.setattr(compat, "cheap_complete", None)
    assert summarize.summarize_cloud_cascade("ctx") is None


def test_cloud_cascade_returns_text(monkeypatch):
    def fake_complete(**kwargs):
        return {"text": "a" * 100}

    monkeypatch.setattr(compat, "cheap_complete", fake_complete)
    out = summarize.summarize_cloud_cascade("ctx")
    assert out is not None and len(out) >= 50


def test_cloud_cascade_rejects_short_text(monkeypatch):
    def fake_complete(**kwargs):
        return {"text": "too short"}  # < 50 chars

    monkeypatch.setattr(compat, "cheap_complete", fake_complete)
    assert summarize.summarize_cloud_cascade("ctx") is None


def test_cloud_cascade_rejects_empty(monkeypatch):
    def fake_complete(**kwargs):
        return {"text": ""}

    monkeypatch.setattr(compat, "cheap_complete", fake_complete)
    assert summarize.summarize_cloud_cascade("ctx") is None


def test_cloud_cascade_swallows_exception(monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(compat, "cheap_complete", boom)
    assert summarize.summarize_cloud_cascade("ctx") is None


def test_cloud_cascade_passes_deepseek_model(monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return {"text": "x" * 60}

    monkeypatch.setattr(compat, "cheap_complete", fake_complete)
    summarize.summarize_cloud_cascade("ctx")
    assert captured["cloud_model"] == "deepseek/deepseek-v4-flash"
    assert captured["prefer_local"] is False
    assert captured["require_json"] is False


def test_summarize_model_env_overrides(monkeypatch):
    import importlib

    from smart_trim.features.summarize import command as sum_cmd

    # Override models
    monkeypatch.setenv("SMART_TRIM_PRIMARY_MODEL", "my-primary-model")
    monkeypatch.setenv("SMART_TRIM_SECONDARY_MODEL", "my-secondary-model")
    importlib.reload(sum_cmd)

    assert sum_cmd._PRIMARY_MODEL == "my-primary-model"
    assert sum_cmd._SECONDARY_MODEL == "my-secondary-model"

    # Clean up
    monkeypatch.delenv("SMART_TRIM_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("SMART_TRIM_SECONDARY_MODEL", raising=False)
    importlib.reload(sum_cmd)


# --- label derivation (tracks env override; strips quant suffix) ------------


def test_primary_label_strips_quantization_suffix():
    """Round-15: primary label strips quant + vendor prefix from
    batiai/gemma4-e2b:q4, producing a stable 'ollama-<bare-name>' hook label."""
    from smart_trim.features.summarize import command as sum_cmd

    label = sum_cmd.primary_label()
    assert label.startswith("ollama-")
    # batiai/ prefix + :q4 quant stripped → bare "gemma4-e2b".
    assert "gemma4-e2b" in label
    # Quant suffix + vendor prefix must be stripped.
    assert ":q4" not in label
    assert "batiai/" not in label


def test_secondary_label_uses_bare_tag():
    from smart_trim.features.summarize import command as sum_cmd

    label = sum_cmd.secondary_label()
    # cryptidbleh/ prefix + :latest stripped → bare "gemma4-claude-opus-4.6".
    assert "gemma4-claude-opus-4.6" in label
    assert "cryptidbleh/" not in label
    assert ":latest" not in label


def test_labels_track_env_override(monkeypatch):
    """The whole point of label derivation: env override MUST change the label."""
    import importlib

    from smart_trim.features.summarize import command as sum_cmd

    monkeypatch.setenv("SMART_TRIM_PRIMARY_MODEL", "custom/cool-model-9b_Q4_K_M")
    importlib.reload(sum_cmd)
    try:
        # _Q4_K_M is a known quant suffix -> stripped, vendor prefix preserved.
        assert sum_cmd.primary_label() == "ollama-custom/cool-model-9b"
    finally:
        monkeypatch.delenv("SMART_TRIM_PRIMARY_MODEL", raising=False)
        importlib.reload(sum_cmd)


def test_labels_fall_back_when_no_quant_suffix(monkeypatch):
    """Plain tags (no quant suffix) pass through verbatim (lower-cased)."""
    import importlib

    from smart_trim.features.summarize import command as sum_cmd

    monkeypatch.setenv("SMART_TRIM_SECONDARY_MODEL", "org/model-v1")
    importlib.reload(sum_cmd)
    try:
        assert sum_cmd.secondary_label() == "ollama-org/model-v1"
    finally:
        monkeypatch.delenv("SMART_TRIM_SECONDARY_MODEL", raising=False)
        importlib.reload(sum_cmd)


# --- cloud tier: env-aware model + label -------------------------------------


def test_cloud_label_default_is_deepseek_cloud():
    assert summarize.cloud_label() == "deepseek-cloud"


def test_cloud_model_env_override_changes_model_and_label(monkeypatch):
    import importlib

    from smart_trim.features.summarize import command as sum_cmd

    monkeypatch.setenv("SMART_TRIM_CLOUD_MODEL", "deepseek/deepseek-v4-pro")
    importlib.reload(sum_cmd)
    try:
        captured = {}

        def fake_complete(**kwargs):
            captured.update(kwargs)
            return {"text": "x" * 60}

        monkeypatch.setattr(compat, "cheap_complete", fake_complete)
        sum_cmd.summarize_cloud_cascade("ctx")
        assert captured["cloud_model"] == "deepseek/deepseek-v4-pro"
        assert sum_cmd.cloud_label() == "cloud-deepseek-v4-pro"
    finally:
        monkeypatch.delenv("SMART_TRIM_CLOUD_MODEL", raising=False)
        importlib.reload(sum_cmd)
