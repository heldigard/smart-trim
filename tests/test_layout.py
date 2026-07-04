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
