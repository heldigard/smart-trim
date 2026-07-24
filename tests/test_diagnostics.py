"""Tests for the ``doctor`` health-check command.

The doctor probes a live Ollama endpoint and the filesystem, so the network +
writability helpers are isolated into module-level functions and monkeypatched.
``agent-memory`` availability is also monkeypatched so tests do not depend on
whether the optional package is installed in the runner.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from smart_trim.features.capabilities import command as caps
from smart_trim.features.diagnostics import command as doc
from smart_trim.features.summarize import command as summarize

# --- _ollama_installed_models -------------------------------------------------


def test_ollama_installed_models_parses_tags():
    fake_payload = json.dumps(
        {"models": [{"name": "batiai/gemma4-e2b:q4"}, {"name": "other:latest"}]}
    ).encode("utf-8")

    class _Resp:
        def __init__(self, data):
            self._data = data

        def read(self):
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(req, timeout):
        assert "/api/tags" in req.full_url
        return _Resp(fake_payload)

    orig = doc.urlopen
    doc.urlopen = fake_urlopen  # type: ignore[method-assign]
    try:
        assert doc._ollama_installed_models() == {"batiai/gemma4-e2b:q4", "other:latest"}
    finally:
        doc.urlopen = orig  # type: ignore[method-assign]


def test_ollama_installed_models_returns_none_on_urlerror():
    from urllib.error import URLError

    def boom(req, timeout):
        raise URLError("connection refused")

    orig = doc.urlopen
    doc.urlopen = boom  # type: ignore[method-assign]
    try:
        assert doc._ollama_installed_models() is None
    finally:
        doc.urlopen = orig  # type: ignore[method-assign]


def test_ollama_installed_models_returns_none_on_bad_json():
    class _Resp:
        def read(self):
            return b"not-json"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    orig = doc.urlopen
    doc.urlopen = lambda req, timeout: _Resp()
    try:
        assert doc._ollama_installed_models() is None
    finally:
        doc.urlopen = orig  # type: ignore[method-assign]


# --- run_doctor end-to-end (helpers monkeypatched) ---------------------------


def _wire_mocks(
    monkeypatch,
    *,
    models,
    agent_memory=True,
    archive_dir: Path,
    helpers: dict[str, bool] | None = None,
    shim_ok: bool = True,
):
    monkeypatch.setattr(doc, "_ollama_installed_models", lambda: models)
    monkeypatch.setattr(doc, "_agent_memory_available", lambda: agent_memory)
    monkeypatch.setattr(
        doc,
        "_cascade_helpers",
        lambda: helpers or {"ollama_client": True, "cheap_complete": True, "cg_reset": True},
    )
    monkeypatch.setattr(doc, "_shim_present", lambda: shim_ok)
    monkeypatch.setattr(doc._paths, "default_summaries_dir", lambda: archive_dir)


def test_run_doctor_all_green_exits_zero(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(
        monkeypatch,
        models={summarize.primary_model(), summarize.secondary_model()},
        archive_dir=archive,
    )
    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf)
    out = buf.getvalue()
    assert code == 0
    assert "[FAIL]" not in out
    assert "ollama: reachable" in out
    assert "primary model:" in out
    assert "memory bank:" in out
    assert "python:" in out
    assert "Result: 0 failure" in out


def test_run_doctor_ollama_unreachable_is_warn_not_fail(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(monkeypatch, models=None, archive_dir=archive)
    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf)
    out = buf.getvalue()
    assert code == 0  # degraded, not broken
    assert "unreachable" in out
    assert "[FAIL]" not in out


def test_run_doctor_missing_model_is_warn(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(monkeypatch, models=set(), archive_dir=archive)
    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf)
    out = buf.getvalue()
    assert code == 0
    assert "primary model:" in out
    # A missing model shows as WARN (cascade still falls through), not FAIL.
    assert "[WARN] primary model:" in out


def test_run_doctor_unwritable_memory_bank_is_fail(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(
        monkeypatch,
        models={summarize.primary_model()},
        archive_dir=archive,
    )
    # Point memory-bank at a path whose parent is a file -> mkdir fails -> not writable.
    blocker = tmp_path / "blocker"
    blocker.write_text("I am a file, not a dir", encoding="utf-8")
    buf = io.StringIO()
    code = doc.run_doctor(project_root=blocker, stream=buf)
    out = buf.getvalue()
    assert code == 1
    assert "[FAIL] memory bank:" in out


def test_run_doctor_self_defeating_budget_is_fail(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(monkeypatch, models=set(), archive_dir=archive)
    monkeypatch.setattr(doc, "CASCADE_BUDGET_SECONDS", 2.0)
    monkeypatch.setattr(doc, "CASCADE_MIN_TIER_SECONDS", 3.0)
    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf)
    out = buf.getvalue()
    assert code == 1
    assert "cascade budget" in out and "[FAIL]" in out


def test_run_doctor_resolves_project_root_when_none(monkeypatch, tmp_path):
    """``project_root=None`` defers to ``paths.get_project_root`` (the hook's resolver)."""
    archive = tmp_path / "archive"
    _wire_mocks(monkeypatch, models=None, archive_dir=archive)
    monkeypatch.setattr(doc._paths, "get_project_root", lambda: tmp_path)
    buf = io.StringIO()
    code = doc.run_doctor(stream=buf)
    assert code == 0
    assert str(tmp_path) in buf.getvalue()


def test_run_doctor_warns_on_missing_helpers_and_shim(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(
        monkeypatch,
        models={summarize.primary_model()},
        archive_dir=archive,
        helpers={"ollama_client": False, "cheap_complete": False, "cg_reset": False},
        shim_ok=False,
        agent_memory=False,
    )
    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf)
    out = buf.getvalue()
    assert code == 0
    assert "[WARN] helper ollama client:" in out
    assert "[WARN] precompact shim:" in out
    assert "[WARN] agent memory:" in out


def test_collect_checks_and_json_mode(tmp_path, monkeypatch):
    archive = tmp_path / "archive"
    _wire_mocks(
        monkeypatch,
        models={summarize.primary_model(), summarize.secondary_model()},
        archive_dir=archive,
    )
    report = doc.collect_checks(project_root=tmp_path)
    assert report["ok"] is True
    assert report["schema_version"] == 1
    assert report["python"]
    names = {c["name"] for c in report["checks"]}
    assert "ollama" in names
    assert "agent_memory" in names
    assert "helper_ollama_client" in names
    assert "precompact_shim" in names

    buf = io.StringIO()
    code = doc.run_doctor(project_root=tmp_path, stream=buf, as_json=True)
    assert code == 0
    parsed = json.loads(buf.getvalue())
    assert parsed["command"] == "doctor"
    assert parsed["ok"] is True


def test_agent_memory_available_handles_import_error(monkeypatch):
    import importlib

    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ModuleNotFoundError(name)),
    )
    assert doc._agent_memory_available() is False


def test_cascade_helpers_reports_compat_bindings():
    helpers = doc._cascade_helpers()
    assert set(helpers) == {"ollama_client", "cheap_complete", "cg_reset"}
    assert all(isinstance(v, bool) for v in helpers.values())


def test_shim_present_false_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(doc, "_shim_path", lambda: tmp_path / "missing-shim.py")
    assert doc._shim_present() is False


def test_shim_present_true_for_file(tmp_path, monkeypatch):
    shim = tmp_path / "smart-trim.py"
    shim.write_text("# ok\n", encoding="utf-8")
    monkeypatch.setattr(doc, "_shim_path", lambda: shim)
    assert doc._shim_present() is True


def test_shim_present_false_on_oserror(tmp_path, monkeypatch):
    class _Boom(type(tmp_path)):
        def is_file(self):
            raise OSError("permission denied")

    bad = _Boom(tmp_path / "x")
    monkeypatch.setattr(doc, "_shim_path", lambda: bad)
    assert doc._shim_present() is False


# --- capabilities wiring ------------------------------------------------------


def test_help_text_mentions_doctor():
    assert "doctor" in caps.help_text()
    assert "python -m smart_trim" in caps.help_text()


def test_capabilities_payload_lists_doctor():
    names = {c["name"] for c in caps.capabilities_payload()["capabilities"]}
    assert "doctor" in names


def test_handle_cli_doctor_dispatches_to_run_doctor(monkeypatch):
    """``handle_cli(['doctor'])`` exits with run_doctor's code (doctor not re-run here)."""
    captured = {"called": False, "as_json": None}

    def fake_run_doctor(project_root=None, *, stream=None, as_json=False):
        captured["called"] = True
        captured["as_json"] = as_json
        return 0

    monkeypatch.setattr("smart_trim.features.diagnostics.command.run_doctor", fake_run_doctor)
    try:
        caps.handle_cli(["doctor"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("SystemExit not raised")
    assert captured["called"] is True
    assert captured["as_json"] is False


def test_handle_cli_doctor_json_flag(monkeypatch):
    captured = {"as_json": None}

    def fake_run_doctor(project_root=None, *, stream=None, as_json=False):
        captured["as_json"] = as_json
        return 0

    monkeypatch.setattr("smart_trim.features.diagnostics.command.run_doctor", fake_run_doctor)
    try:
        caps.handle_cli(["doctor", "--json"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("SystemExit not raised")
    assert captured["as_json"] is True
