# Harness shim — wired hook entry point

`smart-trim.py` here is the canonical source for the wired hook file at
`~/.claude/hooks/smart-trim.py` (and the Gemini symlink at
`~/.gemini/hooks/smart-trim.py`).

## Why a tracked template

The hook entry path is fixed:

- `~/.claude/settings.json` references it as
  `python3 ~/.claude/hooks/smart-trim.py` on `PreCompact`.
- Gemini reaches it via a symlink at `~/.gemini/hooks/smart-trim.py`.
- `pip install -e ~/smart-trim` only registers the `smart_trim` import; it does
  not touch the wired hook path.

Without a tracked source-of-truth, the wired shim drifts silently (no test,
no review) whenever someone tweaks it in place.

## Sync (set up once per host)

```bash
mkdir -p ~/.claude/hooks ~/.gemini/hooks
ln -sfn ~/smart-trim/harness-shim/smart-trim.py ~/.claude/hooks/smart-trim.py
ln -sfn ~/smart-trim/harness-shim/smart-trim.py ~/.gemini/hooks/smart-trim.py
```

After symlink, the wired path is byte-identical to this template. The drift
detector (`tests/test_layout.py::test_shim_matches_canonical`) compares
content; a symlink reads through to the canonical source so drift is
structurally impossible.

## Drift detector

`pytest tests/test_layout.py -q` includes a contract check that the live shim
contains the canonical import line. The check is `skipif` the wired path
doesn't exist (CI environments without the harness live shim), so it never
fails when run on a fresh checkout.

## Editing rules

1. Edit this file (the canonical), never `~/.claude/hooks/smart-trim.py` in
   place.
2. After edit, re-sync via the symlink (above) so the wired path picks up
   the change.
3. Tests must still pass (`pytest tests/ -q`).
