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
    assert call["num_ctx"] == 32768


def test_summarize_ollama_swallows_unavailable(monkeypatch):
    fake = _FakeOllamaClient(exc=_FakeOllamaUnavailable("down"))
    monkeypatch.setattr(compat, "ollama_client", fake)
    assert summarize.summarize_ollama("ctx", "m") is None


# --- summarize_primary / secondary ------------------------------------------


def test_summarize_primary_uses_qwen_model(monkeypatch):
    fake = _FakeOllamaClient(result="ok")
    monkeypatch.setattr(compat, "ollama_client", fake)
    summarize.summarize_primary("ctx")
    assert fake.calls[0]["model"] == "qwen3.5:4b"


def test_summarize_secondary_uses_qwopus_model(monkeypatch):
    fake = _FakeOllamaClient(result="ok")
    monkeypatch.setattr(compat, "ollama_client", fake)
    summarize.summarize_secondary("ctx")
    assert "Qwopus" in fake.calls[0]["model"]


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
