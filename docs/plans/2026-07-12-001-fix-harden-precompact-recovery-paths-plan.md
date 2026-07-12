---
title: "fix: Harden PreCompact recovery paths"
type: fix
status: completed
date: 2026-07-12
---

# fix: Harden PreCompact recovery paths

## Enhancement Summary

**Deepened on:** 2026-07-12
**Evidence used:** repository history, current tests, call-site tracing with
`codeq refs`, baseline quality sensors, and isolated local reproductions.

### Key Improvements

1. Separate strict session-ID validation for reads from lossy filename
   sanitization for archives; a malformed ID must never be mapped to a different
   live session file.
2. Preserve the hook's fail-open contract at each optional filesystem/helper
   boundary rather than relying solely on the top-level exception handler.
3. Make bounded and deterministic behavior directly testable: exact character
   caps, first-seen path order, and coexistence of rapid archives.

### Confirmed Reproductions

- `sessionId="../escaped"` writes an archive into `~/.claude/` instead of
  `~/.claude/summaries/`.
- Different `PYTHONHASHSEED` values produce four observed orders for the same
  three fallback paths.
- A requested context cap of 29 characters currently returns 31 because the
  `\n\n` separator is not budgeted.

## Overview

The package is healthy at baseline (164 tests, Ruff, formatting, Pyright,
Semgrep, Vulture, and Gitleaks all clean), but several best-effort paths can
still lose a handoff or behave nondeterministically when filesystem state or
hook payloads are unusual. This pass hardens those edges without changing the
normal Ollama/cloud/fallback cascade or the vertical-slice architecture.

## Problem Statement

The PreCompact hook must fail open while preserving as much recovery state as
possible. Current edge cases undermine that contract:

- Session discovery can raise while enumerating an unreadable Claude projects
  directory instead of returning no session and producing a minimal handoff.
- Loading the optional agent-memory freshness filter can raise during import or
  execution and must fall back to raw memory lines.
- Archive names interpolate the external session ID directly and have only
  second-level timestamps, allowing unsafe path components and same-second
  overwrites.
- Extracted LLM context counts message payloads but not separators, so the
  documented maximum can be exceeded.
- Rule-based fallback file order is derived from a set and is therefore not
  stable across processes.
- Archive rotation can abandon the entire cap pass when one entry cannot be
  stat'ed.

## Proposed Solution

Apply narrow, regression-tested changes at each owning slice:

1. Make session directory enumeration best-effort and validate session IDs
   before using them as filenames.
2. Treat optional helper import/initialization failures as helper absence.
3. Generate archive filenames from a filesystem-safe, bounded session label
   plus a microsecond timestamp.
4. Include inter-message separators in the context budget and define sensible
   behavior for non-positive budgets.
5. Preserve first-seen file order while deduplicating fallback paths.
6. Sort only archive entries whose metadata can be read.

### Implementation Decisions

- Session lookup accepts only bounded filename-safe identifiers matching the
  normal Claude UUID-like shape (`[A-Za-z0-9][A-Za-z0-9._-]*`). Invalid IDs
  skip direct and all-project lookup.
- Archive labels are sanitized independently because archives should still be
  produced for minimal handoffs with malformed or missing metadata. Labels are
  bounded and cannot contain separators; filenames include microseconds to
  avoid same-second replacement.
- Context accounting includes exactly two separator characters for every
  additional retained message. A non-positive cap yields empty context.
- Fallback paths use a list plus membership set, preserving first occurrence
  without quadratic deduplication.
- Hygiene keeps unreadable entries rather than deleting them blindly; readable
  entries remain eligible for cap enforcement.

## Technical Considerations

- Preserve module-level late binding in `features/precompact/command.py`.
- Keep every feature fail-open; no new external dependency or network access.
- Do not touch the user-owned `.gitignore` or `.memory-bank/control-plane/`
  changes.
- Stay below the 250-line module meta or split only where responsibility calls
  for it.
- Sanitization must retain enough of a normal UUID/session label for archive
  retrieval while preventing path traversal.

## System-Wide Impact

- **Interaction graph:** hook stdin -> `handle_precompact` -> session discovery
  and grounding -> local/cloud/fallback summary -> sanitized archive -> hygiene
  rotation -> memory-bank writer.
- **Error propagation:** optional/environmental filesystem failures resolve to
  empty data and continue to the minimal/fallback handoff; unexpected top-level
  failures remain caught by `main()`.
- **State lifecycle:** archive creation precedes rotation; memory topic creation
  precedes active-context replacement. Archive names must be unique so a newer
  compact cannot silently replace an older recovery point.
- **API parity:** public entry points and return schema remain unchanged.

## Acceptance Criteria

- [x] Unreadable/malformed session-store inputs do not raise from discovery.
- [x] Session IDs cannot escape the Claude projects directory or archive root.
- [x] Two archives for the same session created in rapid succession coexist.
- [x] Optional grounding helper import failures fall back to unfiltered lines.
- [x] Extracted context never exceeds the requested character cap.
- [x] Fallback file-path output is stable and preserves first occurrence.
- [x] One unreadable archive does not prevent rotation of readable entries.
- [x] Full pytest, Ruff check, Ruff format check, type/SAST/dead/secrets sensors,
  diff checks, and hook smoke tests pass.

## Regression Test Matrix

| Slice | Scenario | Expected result |
| --- | --- | --- |
| session | Projects root `iterdir()` raises | Discovery returns `None` |
| session | One project entry cannot be inspected | Other readable projects remain searchable |
| session | `sessionId` contains `../` | No out-of-root candidate is considered |
| grounding | Optional helper raises during import | Raw memory lines are still used |
| precompact | Archive session ID contains separators | File remains under summaries root |
| precompact | Same session archived twice rapidly | Two complete `.md` files exist |
| session content | Cap equals payload-only length | Separator is counted; result stays within cap |
| session content | Cap is zero or negative | Empty context |
| fallback | Duplicate paths across messages | First-seen unique order is stable |
| hygiene | One archive `stat()` fails | Readable excess archives are still rotated |

## Validation Sequence

1. Run only the modified slice tests while iterating.
2. Run `python3 -m pytest tests/ -q`.
3. Run `ruff check .` and `ruff format --check .`.
4. Run `codescan all --json --fail-on never` and require zero findings/errors
   (architecture may remain skipped because this Python project has no
   dependency-cruiser configuration).
5. Run `git diff --check`, inspect the complete diff, and run the canonical shim
   plus installed console entry in isolated smoke inputs.

## Post-Deploy Monitoring & Validation

- **Search:** stderr for `[smart-trim] precompact failed` and unexpected hygiene
  warnings.
- **Healthy signals:** each automatic compact leaves a complete
  `.memory-bank/activeContext.md`; new archives remain under
  `~/.claude/summaries/`; archive rotation stays at or below its configured cap
  aside from explicitly unreadable entries.
- **Failure signals:** missing active handoff after a valid session, archive files
  outside the summaries directory, or repeated top-level fail-open messages.
- **Mitigation:** restore the previous package revision; the tracked shim and
  memory-bank files require no schema rollback.
- **Window and owner:** observe the next five local compactions; repository owner.

## Risks and Mitigations

- **Over-sanitizing session IDs:** retain alphanumerics plus `._-`, bound length,
  and use a neutral fallback label.
- **Changed context boundary:** test exact budget behavior and preserve newest
  contiguous messages.
- **Behavior drift:** target only error cases and nondeterministic output; verify
  the normal cascade and writer tests unchanged.

## Internal References

- `src/smart_trim/features/precompact/command.py:41`
- `src/smart_trim/features/session/command.py:26`
- `src/smart_trim/features/session/content.py:20`
- `src/smart_trim/features/grounding/command.py:91`
- `src/smart_trim/features/fallback/command.py:44`
- `src/smart_trim/features/hygiene/command.py:62`
- `.memory-bank/MEMORY.md`
- `.memory-bank/CONTEXT.md`

## Implementation Phases

1. Add focused regression tests that demonstrate each failure mode.
2. Implement the smallest owning-slice fixes.
3. Review the combined diff for fail-open and path-containment guarantees.
4. Run targeted tests, then the complete quality and hook validation matrix.
5. Record only durable architecture/behavior decisions in agent memory.
