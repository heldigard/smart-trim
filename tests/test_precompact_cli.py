"""precompact CLI surface (capabilities/help/version)."""

from __future__ import annotations

import json

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


def test_precompact_capabilities_json_has_side_effect_contract(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["smart-trim", "capabilities", "--json"])
    monkeypatch.setattr(sys, "stdin", None)

    precompact.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 1
    compact = next(item for item in payload["capabilities"] if item["name"] == "precompact")
    assert compact["read_only"] is False
    assert compact["writes"].startswith(".memory-bank/")
    assert payload["degradation"].endswith("deterministic summary")


def test_precompact_capabilities_table_output(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["smart-trim", "capabilities"])
    monkeypatch.setattr(sys, "stdin", None)

    precompact.main()

    output = capsys.readouterr().out
    assert "name          ro  open  cost          writes" in output
    assert "precompact" in output
    assert "capabilities" in output


def test_precompact_help_is_discoverable_without_reading_stdin(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys, "argv", ["smart-trim", "--help"])
    monkeypatch.setattr(sys, "stdin", None)

    precompact.main()

    output = capsys.readouterr().out
    assert "usage: smart-trim" in output
    assert "capabilities" in output
    assert "PreCompact" in output


def test_precompact_version_does_not_read_stdin(monkeypatch, capsys):
    import sys

    from smart_trim import __version__

    monkeypatch.setattr(sys, "argv", ["smart-trim", "--version"])
    monkeypatch.setattr(sys, "stdin", None)

    precompact.main()

    assert capsys.readouterr().out.strip() == f"smart-trim {__version__}"
