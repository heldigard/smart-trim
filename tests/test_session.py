"""Tests for features/session."""

from __future__ import annotations

import json
import os
from pathlib import Path

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


# --- read_session ------------------------------------------------------------


def test_read_session_tail_bounded_keeps_newest_messages(tmp_path, monkeypatch):
    # A session larger than the tail budget is read from the end: newest
    # messages survive, the partial line at the seek boundary is dropped.
    monkeypatch.setenv("SMART_TRIM_SESSION_TAIL_BYTES", "4096")
    jsonl = tmp_path / "big.jsonl"
    lines = [json.dumps({"seq": i, "pad": "x" * 100}) for i in range(200)]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")

    messages = session.read_session(jsonl)

    assert messages, "tail read must yield messages"
    assert len(messages) < 200, "older messages beyond the tail budget are skipped"
    assert messages[-1]["seq"] == 199, "the newest message must survive"
    seqs = [m["seq"] for m in messages]
    assert seqs == sorted(seqs), "message order preserved"


def test_read_session_tail_zero_forces_full_read(tmp_path, monkeypatch):
    monkeypatch.setenv("SMART_TRIM_SESSION_TAIL_BYTES", "0")
    jsonl = tmp_path / "full.jsonl"
    lines = [json.dumps({"seq": i}) for i in range(50)]
    jsonl.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert len(session.read_session(jsonl)) == 50


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


def test_find_latest_session_jsonl_resolves_newest(monkeypatch, tmp_path):
    # Set up simulated Claude projects directory under tmp_path
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-1")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    projects_dir = tmp_path / ".claude" / "projects"

    # 1. projects_dir not a directory
    assert session.find_latest_session_jsonl() is None

    projects_dir.mkdir(parents=True)
    # 2. projects_dir exists but empty
    assert session.find_latest_session_jsonl() is None

    # 3. Create two project subdirs and some jsonl files
    p1 = projects_dir / "proj1"
    p2 = projects_dir / "proj2"
    p1.mkdir()
    p2.mkdir()

    import time

    f1 = p1 / "sessionA.jsonl"
    f2 = p2 / "sessionB.jsonl"
    f1.write_text("{}", encoding="utf-8")
    f2.write_text("{}", encoding="utf-8")

    # Set mtimes
    os.utime(f1, (time.time() - 100, time.time() - 100))
    os.utime(f2, (time.time(), time.time()))

    # newest should be B
    assert session.find_latest_session_jsonl() == f2

    # mtime check OSError
    original_stat = Path.stat

    def fake_stat(*args, **kwargs):
        if len(args) > 0 and str(args[0]).endswith(".jsonl"):
            raise OSError("Permission denied")
        return original_stat(*args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)
    assert session.find_latest_session_jsonl() is None


def test_get_session_file_resolves_from_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    projects_dir = tmp_path / ".claude" / "projects"
    p1 = projects_dir / "-home-eldi-app"
    p1.mkdir(parents=True)

    f1 = p1 / "sess-123.jsonl"
    f1.write_text("{}", encoding="utf-8")

    # Create a dummy file directly in projects directory to test is_dir check
    dummy_file = projects_dir / "not-a-dir.txt"
    dummy_file.write_text("dummy", encoding="utf-8")

    # Resolve using candidate from cwd
    input_data = {"sessionId": "sess-123", "cwd": "/home/eldi/app"}
    res = session.get_session_file(input_data)
    assert res == f1

    # Resolve via search all projects
    input_data_other_cwd = {"sessionId": "sess-123", "cwd": "/other/path"}
    res = session.get_session_file(input_data_other_cwd)
    assert res == f1

    # Resolve with empty stdin data (returns None)
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    monkeypatch.delenv("CLAUDE_SESSION_FILE", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert session._resolve_from_stdin({}) is None

    # Search all projects when session does not exist
    input_data_not_found = {"sessionId": "sess-999", "cwd": "/other/path"}
    assert session.get_session_file(input_data_not_found) is None


def test_content_extraction_edge_cases():
    # 1. non-dict in message
    msgs = [{"type": "Conversation", "message": "not-a-dict"}]
    assert content.extract_context_for_summary(msgs) == ""

    # 2. user message has no text/empty text
    msgs = [{"type": "Conversation", "message": {"role": "user", "content": ""}}]
    assert content.extract_context_for_summary(msgs) == ""

    # 3. non-string non-dict non-list content (e.g. integer/bool)
    out = content._extract_text_from_content(12345, "user")
    assert out == "12345"

    # 4. list of blocks has non-dict block
    blocks = [12345, {"type": "text", "text": "hello"}]
    out = content._extract_text_from_content(blocks, "user")
    assert "hello" in out

    # 5. tool result contains a list of text result blocks
    tool_res_list = [
        {"type": "tool_result", "content": [{"type": "text", "text": "result-block-content"}]}
    ]
    out = content._extract_text_from_content(tool_res_list, "assistant")
    assert "result-block-content" in out

    # 6. tool result contains non-list non-string content (e.g. dict or integer)
    tool_res_other = [{"type": "tool_result", "content": 12345}]
    out = content._extract_text_from_content(tool_res_other, "assistant")
    # should skip or return empty for this block
    assert "12345" not in out

    # 7. tool result contains dict content
    tool_res_dict = [{"type": "tool_result", "content": {"status": "ok"}}]
    out = content._extract_text_from_content(tool_res_dict, "assistant")
    assert '{"status": "ok"}' in out
