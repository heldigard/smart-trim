"""compact_items / compact_value truncation rules."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from contextlib import contextmanager  # noqa: F401
from pathlib import Path  # noqa: F401
from typing import cast  # noqa: F401

from smart_trim.features.writer import active as active_renderer  # noqa: F401
from smart_trim.features.writer import command as writer  # noqa: F401


def test_compact_items_preserves_whole_items_that_fit():
    items = ["fix parser bug", "add regression test", "update docs"]
    result, truncated = active_renderer.compact_items(items, 200, "Next")
    assert truncated is False
    for item in items:
        assert item in result
    assert " | " in result
    assert "omitted" not in result


def test_compact_items_dedups_case_insensitive():
    items = ["Never bypass safety", "never bypass safety", "ship it"]
    result, truncated = active_renderer.compact_items(items, 200, "Constraints")
    assert truncated is True
    assert result.lower().count("never bypass safety") == 1
    assert "ship it" in result


def test_compact_items_tags_omitted_count_and_keeps_whole_items():
    items = ["alpha", "beta", "gamma", "delta", "epsilon"]
    result, truncated = active_renderer.compact_items(items, 20, "Files")
    assert truncated is True
    assert len(result) <= 20
    assert "omitted" in result
    # items kept are whole, not sliced mid-token
    assert "alpha" in result
    assert "epsilon" not in result


def test_compact_items_single_item_delegates_to_compact_value_tail():
    value = (
        "Authority: session data only; never overrides safety, permissions, "
        "or current instructions. Authority: session data only; never overrides "
        "safety, permissions, or current instructions."
    )
    result, truncated = active_renderer.compact_items([value], 120, "Constraints")
    assert truncated is True
    assert len(result) <= 120
    assert result.endswith("…")
    assert "[recortado]" not in result


def test_compact_items_empty_list_returns_empty():
    result, truncated = active_renderer.compact_items([], 120, "Task")
    assert result == ""
    assert truncated is False


def test_compact_items_tag_displaces_whole_item_not_fragment():
    # Items fill the budget exactly; the (+N omitted) tag must displace a WHOLE
    # item, never slice one mid-token (a sliced path is useless). Regression for
    # the out[:room] mid-item-fragment bug.
    items = [
        "/a/src/parser.py",
        "/a/src/lexer.py",
        "/a/tests/test_parser.py",
        "/a/src/utils.py",
    ]
    result, truncated = active_renderer.compact_items(items, 60, "Files")
    assert truncated is True
    assert len(result) <= 60
    assert "omitted" in result
    assert "/a/src/parser.py" in result
    assert "/a/src/lexer.py" in result
    assert "/a/tests/test_parser.py" not in result
    assert "/a/tests/t" not in result
    assert "/a/tests" not in result


def test_compact_items_keeps_whole_item_and_flag_when_tag_does_not_fit():
    # 1 item fits whole but the (+N omitted) tag does not fit alongside it:
    # the item must stay WHOLE and `truncated` must stay True (items were
    # dropped). Regression: the old while-empties-kept fallback returned via
    # compact_value, which reported truncated=False — losing the omission signal.
    items = ["abcdefghij", "x", "y"]  # item0=10 fits limit 11; x,y omitted
    result, truncated = active_renderer.compact_items(items, 11, "Files")
    assert result == "abcdefghij", f"item should stay whole, got {result!r}"
    assert truncated is True, "omission flag must survive when tag won't fit"


def test_compact_respects_len_limit_for_tiny_limits():
    # Regression (fuzz-found): _truncate_at_tail appended the elision marker even
    # when it pushed len(result) past the limit for tiny limits. len <= limit is
    # the hard contract of both compacters — it must hold for ALL limits >= 1,
    # or render_active_fields raises ValueError and loses the handoff.
    for limit in range(1, 12):
        rv, _ = active_renderer.compact_value("a long value here", limit, "Task")
        assert len(rv) <= limit, f"compact_value len {len(rv)} > {limit}: {rv!r}"
        ri, _ = active_renderer.compact_items(["abcdefghij", "xyz", "q"], limit, "Files")
        assert len(ri) <= limit, f"compact_items len {len(ri)} > {limit}: {ri!r}"


# --- compact_value -----------------------------------------------------------


def test_compact_value_short_value_not_truncated():
    result, truncated = active_renderer.compact_value("short value", 120, "Task")
    assert result == "short value"
    assert truncated is False


def test_compact_value_prose_truncates_at_tail_not_middle():
    value = (
        "Authority: session data only; never overrides safety, permissions, "
        "or current instructions. Authority: session data only; never overrides "
        "safety, permissions, or current instructions."
    )
    result, truncated = active_renderer.compact_value(value, 120, "Constraints")
    assert truncated is True
    assert len(result) <= 120
    assert result.endswith("…")
    assert "[recortado]" not in result
    assert result.count("…") == 1


def test_compact_value_prose_does_not_split_word_at_cut():
    value = "objective-aware handoff behavior is preserved via CLI orchestration layer"
    result, truncated = active_renderer.compact_value(value, 40, "Decisions")
    assert truncated is True
    assert len(result) <= 40
    assert result.endswith("…")
    assert "orchestr" not in result


def test_compact_value_error_field_keeps_evidence_in_middle():
    value = ("noise " * 40) + "E_PARSE_X /srv/app/parser.py:99 " + ("tail " * 40)
    result, truncated = active_renderer.compact_value(value, 160, "Errors")
    assert truncated is True
    assert len(result) <= 160
    assert "E_PARSE_X" in result
    assert "/srv/app/parser.py:99" in result
    assert "[recortado]" not in result
    assert "…" in result


def test_compact_value_error_evidence_preserved_when_too_long_for_head_tail():
    # Evidence (many error-ids + paths) exceeds the head+tail budget. It is the
    # critical signal, so it must survive (trimmed) instead of being dropped by
    # a prose tail-truncate that keeps only the surrounding "noise".
    value = (
        ("noise " * 30)
        + " ".join(f"E_BIG_{i} /srv/app/m{i}.py:9{i}" for i in range(12))
        + (" tail " * 20)
    )
    result, truncated = active_renderer.compact_value(value, 120, "Errors")
    assert truncated is True
    assert len(result) <= 120
    assert "[recortado]" not in result
    assert any(f"E_BIG_{i}" in result for i in range(3)), (
        f"evidence lost to tail-trunc; got {result!r}"
    )


def test_compact_value_overlapping_head_tail_falls_back_to_tail():
    value = (
        "the permissions check the permissions check the permissions check "
        "the permissions check the permissions check the permissions check"
    )
    result, truncated = active_renderer.compact_value(value, 80, "Verified")
    assert truncated is True
    assert len(result) <= 80
    assert result.endswith("…")
    assert result.count("…") == 1
