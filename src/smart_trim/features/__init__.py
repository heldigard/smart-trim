"""Features layer — one responsibility per folder.

Each feature module depends only on ``smart_trim.shared`` (and, for the
precompact orchestrator, on the other feature modules). No feature imports
another feature except via the orchestrator.
"""
