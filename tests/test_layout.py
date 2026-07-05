"""Layout gate: each module respects the 250L meta (cohesion-first budget).

Mirrors codeq's test_codeq_modular_layout. A module may exceed the meta only
when it is genuinely cohesive (one responsibility, a single pipeline); such
exceptions are listed in ALLOWLIST with the reason and re-reviewed on change.
"""

from __future__ import annotations

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "smart_trim"
META = 250

# Modules allowed to exceed the 250L meta (cohesive, one responsibility).
# Each entry: relative path -> human reason. Keep this SHORT and re-review.
ALLOWLIST: dict[str, str] = {}


def _python_modules() -> list[tuple[str, int]]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        out.append((rel, sum(1 for _ in path.open(encoding="utf-8"))))
    return out


def test_every_module_present():
    mods = _python_modules()
    assert mods, "no modules found under src/smart_trim/"
    # Sanity: the seven features + shared must exist.
    names = {rel for rel, _ in mods}
    for required in (
        "shared/config.py",
        "shared/compat.py",
        "features/session/command.py",
        "features/summarize/command.py",
        "features/fallback/command.py",
        "features/grounding/command.py",
        "features/writer/command.py",
        "features/hygiene/command.py",
        "features/precompact/command.py",
    ):
        assert required in names, f"missing required module: {required}"


def test_modules_under_meta():
    over = [(rel, n) for rel, n in _python_modules() if n > META and rel not in ALLOWLIST]
    assert not over, (
        f"modules over the {META}L meta (split or add to ALLOWLIST with a reason): {over}"
    )


def test_allowlist_modules_are_actually_over():
    """An ALLOWLIST entry that no longer exceeds the meta is stale — remove it."""
    for rel in ALLOWLIST:
        path = SRC / rel
        n = sum(1 for _ in path.open(encoding="utf-8"))
        assert n > META, f"{rel} is in ALLOWLIST but only {n}L <= {META}; drop the exception"


# --- Harness shim contract ---------------------------------------------------


_REPO_ROOT = Path(__file__).resolve().parent.parent
_CANONICAL_SHIM = _REPO_ROOT / "harness-shim" / "smart-trim.py"
_LIVE_SHIM = Path.home() / ".claude" / "hooks" / "smart-trim.py"
_REQUIRED_IMPORT = "from smart_trim.features.precompact.command import main"


def test_canonical_shim_is_tracked():
    """The wired hook entry point must live in the repo as source-of-truth."""
    assert _CANONICAL_SHIM.is_file(), (
        f"missing tracked shim template: {_CANONICAL_SHIM}. "
        "Create it (see harness-shim/README.md) and wire it via symlink."
    )
    content = _CANONICAL_SHIM.read_text(encoding="utf-8")
    assert _REQUIRED_IMPORT in content, (
        f"canonical shim must import {_REQUIRED_IMPORT!r}; got:\n{content}"
    )


def test_live_shim_matches_canonical():
    """Live wired shim must be byte-equal to the tracked canonical (or a symlink).

    A symlinked live path resolves to the canonical at read time, so drift is
    structurally impossible. If this test fires, someone hand-edited the wired
    copy or the symlink was replaced.
    """
    if not _LIVE_SHIM.exists():
        import pytest

        pytest.skip(
            f"live shim not present at {_LIVE_SHIM} "
            "(CI/dev without the wired hook). See harness-shim/README.md to sync."
        )
    canonical = _CANONICAL_SHIM.read_text(encoding="utf-8")
    live = _LIVE_SHIM.read_text(encoding="utf-8")
    assert canonical == live, (
        f"live shim drifted from canonical. Re-sync:\n"
        f"  ln -sfn {_CANONICAL_SHIM} {_LIVE_SHIM}"
    )
