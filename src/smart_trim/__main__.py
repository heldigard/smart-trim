"""Allow ``python -m smart_trim`` (same surface as the ``smart-trim`` console script)."""

from __future__ import annotations

from smart_trim.features.precompact.command import main

if __name__ == "__main__":
    main()
