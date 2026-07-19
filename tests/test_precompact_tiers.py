"""tier routing + shrinking-timeout budget."""

from __future__ import annotations

import time

from _helpers import (  # noqa: F401
    _COMPAT,
    _OLLAMA,
    _SESSION,
    _SUMMARIZE,
    _WRITER,
    _disable_external,
    _routed_precompact,
    _seed_session,
)

from smart_trim.features.precompact import command as precompact


def test_tier_timeout_clamps_to_remaining_share_and_ceiling():
    from smart_trim.shared.config import OLLAMA_TIMEOUT_SECONDS

    out = precompact._tier_timeout(time.monotonic() + 20.0, share=0.6)
    assert out is not None
    assert out <= 20.0 * 0.6 + 0.01  # 60% share of the remaining budget
    assert out <= OLLAMA_TIMEOUT_SECONDS


def test_tier_timeout_never_exceeds_per_call_ceiling():
    from smart_trim.shared.config import OLLAMA_TIMEOUT_SECONDS

    # A huge remaining budget still clamps to the per-call ceiling.
    out = precompact._tier_timeout(time.monotonic() + 10_000.0)
    assert out == OLLAMA_TIMEOUT_SECONDS


def test_tier_timeout_none_when_below_floor():
    # Under CASCADE_MIN_TIER_SECONDS the tier is skipped (None) rather than
    # starting a call that cannot finish.
    assert precompact._tier_timeout(time.monotonic() + 1.0) is None


def test_try_cloud_skips_when_budget_exhausted(monkeypatch):
    calls = {"cloud": 0}
    monkeypatch.setattr(
        precompact._summarize,
        "summarize_cloud_cascade",
        lambda *a, **k: calls.__setitem__("cloud", calls["cloud"] + 1) or None,
    )
    text, method, chain = precompact._try_cloud([], "g", "", deadline=time.monotonic() - 1.0)
    assert (text, method) == (None, None)
    assert calls == {"cloud": 0}


def test_try_local_passes_shrinking_timeout_to_primary(monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    captured: dict[str, float] = {}

    def fake_primary(context, grounding="", timeout=999.0, **_kw):
        captured["timeout"] = timeout
        return "primary ok"

    monkeypatch.setattr(precompact._summarize, "summarize_primary", fake_primary)
    # 30s remaining -> primary gets 60% (~18s), under the 45s ceiling.
    text, method, chain = precompact._try_local("ctx", "g", deadline=time.monotonic() + 30.0)
    assert text == "primary ok"
    assert captured["timeout"] <= 30.0 * 0.6 + 0.01
    assert captured["timeout"] > 0.0


def test_try_local_skips_both_tiers_when_budget_exhausted(monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    calls = {"primary": 0, "secondary": 0}
    monkeypatch.setattr(
        precompact._summarize,
        "summarize_primary",
        lambda *a, **k: calls.__setitem__("primary", calls["primary"] + 1) or None,
    )
    monkeypatch.setattr(
        precompact._summarize,
        "summarize_secondary",
        lambda *a, **k: calls.__setitem__("secondary", calls["secondary"] + 1) or None,
    )
    text, method, chain = precompact._try_local("ctx", "g", deadline=time.monotonic() - 1.0)
    assert (text, method) == (None, None)
    assert calls == {"primary": 0, "secondary": 0}


def test_cloud_tier_used_when_ollama_down(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "work")
    monkeypatch.setattr(f"{_COMPAT}.cg_reset", None)
    monkeypatch.setattr(f"{_OLLAMA}.is_ollama_alive", lambda: False)
    monkeypatch.setattr(
        f"{_SUMMARIZE}.summarize_cloud_cascade",
        lambda context, grounding="", **_kw: "cloud handoff" * 10,
    )
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr(
        f"{_WRITER}.update_agent_memory",
        lambda summary, method, session_id="unknown", project_root=None: seen.update(method=method),
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "s", "cwd": str(project)})
    assert seen["method"] == "deepseek-cloud"


def test_falls_back_to_rule_based_when_all_llm_fail(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".memory-bank").mkdir(parents=True)
    session_file = _seed_session(tmp_path, "edit /tmp/x.py error: boom failed")
    _disable_external(monkeypatch)
    monkeypatch.setattr(f"{_SESSION}.get_session_file", lambda input_data: session_file)
    monkeypatch.setattr(precompact, "_archive_summary", lambda *a, **k: None)
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.cleanup_old_summaries", lambda *a, **k: None
    )
    monkeypatch.setattr(
        "smart_trim.features.hygiene.command.check_memory_hygiene", lambda *a, **k: None
    )

    seen: dict[str, str] = {}
    monkeypatch.setattr(
        f"{_WRITER}.update_agent_memory",
        lambda summary, method, session_id="unknown", project_root=None: seen.update(method=method),
    )

    precompact.handle_precompact({"trigger": "auto", "sessionId": "s", "cwd": str(project)})
    assert seen["method"] == "fallback"


def test_precompact_secondary_ollama_success(tmp_path, monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        precompact._summarize, "summarize_primary", lambda context, grounding="", **_kw: None
    )
    monkeypatch.setattr(
        precompact._summarize,
        "summarize_secondary",
        lambda context, grounding="", **_kw: "secondary ok",
    )

    text, method, chain = precompact._try_local("context", "grounding")
    assert text == "secondary ok"
    # Label derived from active _SECONDARY_MODEL (env-aware).
    from smart_trim.features.summarize import command as summarize_cmd

    assert method == summarize_cmd.secondary_label()


def test_precompact_try_local_returns_none_none(monkeypatch):
    monkeypatch.setattr(precompact._ollama, "is_ollama_alive", lambda: True)
    monkeypatch.setattr(
        precompact._summarize, "summarize_primary", lambda context, grounding="", **_kw: None
    )
    monkeypatch.setattr(
        precompact._summarize, "summarize_secondary", lambda context, grounding="", **_kw: None
    )

    text, method, chain = precompact._try_local("context", "grounding")
    assert text is None
    assert method is None
