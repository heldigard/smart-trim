"""Tests for features/fallback."""

from __future__ import annotations

from smart_trim.features.fallback import command as fallback


def _envelope(role, content):
    return {"message": {"role": role, "content": content}}


def test_fallback_includes_user_request_count():
    msgs = [_envelope("user", "do thing"), _envelope("assistant", "ok")]
    out = fallback.generate_fallback_summary(msgs, session_id="s1")
    assert "1 user requests" in out
    assert "s1" in out


def test_fallback_extracts_file_paths():
    msgs = [_envelope("user", "edit /home/eldi/smart-trim/src/app.py please")]
    out = fallback.generate_fallback_summary(msgs)
    assert "/home/eldi/smart-trim/src/app.py" in out


def test_fallback_file_paths_preserve_first_seen_order_and_deduplicate():
    msgs = [
        _envelope("user", "edit /tmp/b.py then /tmp/a.py"),
        _envelope("assistant", "verified /tmp/b.py and /tmp/c.py"),
    ]

    out = fallback.generate_fallback_summary(msgs)

    assert "**Files**: /tmp/b.py, /tmp/a.py, /tmp/c.py" in out


def test_fallback_extracts_error_lines():
    msgs = [_envelope("assistant", "Traceback:\nValueError: bad thing failed")]
    out = fallback.generate_fallback_summary(msgs)
    assert "bad thing failed" in out or "ValueError" in out


def test_fallback_extracts_decisions():
    msgs = [_envelope("user", "we decided to use ollama for this")]
    out = fallback.generate_fallback_summary(msgs)
    assert "decided" in out.lower() or "ollama" in out.lower()


def test_fallback_no_errors_shows_none_detected():
    msgs = [_envelope("user", "all good here")]
    out = fallback.generate_fallback_summary(msgs)
    assert "None detected" in out


def test_fallback_caps_at_three_errors():
    content = "\n".join(f"error number {i} failed" for i in range(10))
    msgs = [_envelope("assistant", content)]
    out = fallback.generate_fallback_summary(msgs)
    # At most 3 error lines extracted.
    assert out.count("- ") <= 4  # 3 errors + possible decisions header line


def test_fallback_unwraps_message_envelope():
    # Raw form without envelope should also work.
    msgs = [{"role": "user", "content": "naked message"}]
    out = fallback.generate_fallback_summary(msgs)
    assert "1 user requests" in out


def test_fallback_caps_at_three_decisions():
    msgs = [
        _envelope("user", "we decided to do A"),
        _envelope("user", "we agreed on B"),
        _envelope("user", "we chose C"),
        _envelope("user", "decision: do D"),
    ]
    out = fallback.generate_fallback_summary(msgs)
    # We should have at most 3 decisions listed under Decisions
    # Since we extract from each message, and we break when len(decisions) >= 3, we should only see A, B, C.
    assert "decided to do A" in out
    assert "agreed on B" in out
    assert "chose C" in out
    assert "do D" not in out
