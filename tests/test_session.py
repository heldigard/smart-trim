"""Tests for features/session."""

from __future__ import annotations

import json

from smart_trim.features.session import command as session
from smart_trim.features.session import content

# --- get_session_id ----------------------------------------------------------


def test_get_session_id_from_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "abc-123")
    assert session.get_session_id() == "abc-123"


def test_get_session_id_from_input_data(monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    assert session.get_session_id({"sessionId": "xyz"}) == "xyz"


def test_get_session_id_unknown_default(monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    assert session.get_session_id() == "unknown"
    assert session.get_session_id({}) == "unknown"


# --- get_context_usage -------------------------------------------------------


def test_get_context_usage_from_env(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONTEXT_USED", "150000")
    monkeypatch.setenv("CLAUDE_CONTEXT_TOTAL", "200000")
    assert session.get_context_usage() == 75.0


def test_get_context_usage_no_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_CONTEXT_USED", raising=False)
    monkeypatch.delenv("CLAUDE_CONTEXT_TOTAL", raising=False)
    assert session.get_context_usage() == 0.0


def test_get_context_usage_zero_total(monkeypatch):
    monkeypatch.setenv("CLAUDE_CONTEXT_USED", "10")
    monkeypatch.setenv("CLAUDE_CONTEXT_TOTAL", "0")
    assert session.get_context_usage() == 0.0


# --- read_session ------------------------------------------------------------


def test_read_session_parses_jsonl(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}})
        + "\n"
        + json.dumps({"type": "assistant"})
        + "\n"
        + "\n"  # blank line skipped
        + "not-json\n",  # malformed skipped
        encoding="utf-8",
    )
    msgs = session.read_session(f)
    assert len(msgs) == 2


def test_read_session_missing_file_returns_empty(tmp_path):
    assert session.read_session(tmp_path / "nope.jsonl") == []


# --- _extract_text_from_content ---------------------------------------------


def test_extract_text_string_capped():
    out = content._extract_text_from_content("x" * 5000, "user")
    assert len(out) == 1200


def test_extract_text_assistant_smaller_cap():
    out = content._extract_text_from_content("x" * 5000, "assistant")
    assert len(out) == 1000


def test_extract_text_list_with_blocks():
    blocks = [
        {"type": "text", "text": "hello"},
        {"type": "thinking", "content": "internal"},  # skipped
        {"type": "tool_use", "name": "Read", "input": {"f": "a.py"}},
        {"type": "tool_result", "content": "ok"},
        {"type": "tool_result", "is_error": True, "content": "boom"},
    ]
    out = content._extract_text_from_content(blocks, "assistant")
    assert "hello" in out
    assert "[Tool: Read(" in out
    assert "[Result: ok]" in out
    assert "internal" not in out  # thinking skipped
    assert "boom" in out  # error result kept


def test_extract_text_dict_content():
    out = content._extract_text_from_content({"k": "v"}, "user")
    assert "k" in out and "v" in out


# --- extract_context_for_summary --------------------------------------------


def _msg(role, content, mtype="Conversation"):
    return {"type": mtype, "message": {"role": role, "content": content}}


def test_extract_context_newest_first_within_cap():
    msgs = [_msg("user", f"turn-{i}") for i in range(50)]
    ctx = session.extract_context_for_summary(msgs, max_length=200)
    # Newest messages kept; once cap exceeded, stopped.
    assert "turn-49" in ctx
    assert "[USER]" in ctx


def test_extract_context_skips_non_conversation_types():
    msgs = [
        {"type": "last-prompt", "message": {"role": "user", "content": "skip"}},
        {"type": "mode"},
        _msg("assistant", "keep"),
    ]
    ctx = session.extract_context_for_summary(msgs)
    assert "keep" in ctx
    assert "skip" not in ctx


def test_extract_context_filters_unknown_roles():
    msgs = [
        {"message": {"role": "system", "content": "sys"}},
        _msg("user", "u"),
    ]
    ctx = session.extract_context_for_summary(msgs)
    assert "u" in ctx
    assert "sys" not in ctx


def test_extract_context_empty_messages():
    assert session.extract_context_for_summary([]) == ""


# --- get_session_file (resolution order) ------------------------------------


def test_get_session_file_env_var_wins(monkeypatch, tmp_path):
    f = tmp_path / "env.jsonl"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_SESSION_FILE", str(f))
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert session.get_session_file({}) == f


def test_get_session_file_falls_back_to_latest(monkeypatch):
    # No env, no input -> find_latest_session_jsonl (which itself needs Claude env)
    monkeypatch.delenv("CLAUDE_SESSION_FILE", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert session.get_session_file(None) is None


def test_find_latest_returns_none_without_claude_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_FILE", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert session.find_latest_session_jsonl() is None
