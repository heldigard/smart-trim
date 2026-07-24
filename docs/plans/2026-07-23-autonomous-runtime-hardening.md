# Autonomous runtime hardening

Date: 2026-07-23  
Status: implemented and validated

## Objective

Make `smart-trim doctor` verify the operational wiring that actually decides
whether compaction runs, instead of reporting a healthy runtime solely because
the shim path exists. Preserve fail-open hook behavior and avoid the writer,
file-lock, tier-policy, and test files currently owned by the parallel Claude
session.

## Findings

1. The live Claude, Codex, and Gemini shim paths currently resolve to the
   tracked `harness-shim/smart-trim.py`.
2. Claude and Codex both configure `PreCompact` with a 90-second timeout; the
   LLM cascade budget is 40 seconds.
3. `doctor` checks that `~/.claude/hooks/smart-trim.py` is a file but not that
   it delegates to `smart_trim.features.precompact.command`.
4. `doctor` does not inspect the Claude or Codex `PreCompact` configuration, so
   an absent command, wrong shim path, malformed configuration, or timeout
   shorter than the cascade budget can still produce an all-green report.
5. The diagnostics module is already near the project's 250-line module meta;
   wiring inspection should live in a cohesive sibling module.

## Planned changes

1. Add a diagnostics wiring module that:
   - inspects a shim without executing it;
   - parses only the `hooks.PreCompact` subtree from a JSON settings file;
   - detects a command targeting the expected shim;
   - reports the configured timeout without returning unrelated configuration.
2. Extend `collect_checks()` with:
   - shim integrity;
   - required Claude wiring;
   - optional Codex wiring when its hook configuration exists;
   - timeout headroom against the cascade budget.
3. Omit optional Codex checks when its configuration is absent; report broken
   Codex wiring as a warning when present, while broken Claude wiring or a
   non-delegating Claude shim is a failure.
4. Add focused unit tests for valid, missing, malformed, stale, and
   under-budget configurations.
5. Update operational documentation and capability wording.

## Detailed design

### Wiring result

Use a small immutable result type with `configured`, `timeout_seconds`, and
`detail` fields. The public report keeps only the status, timeout, and a
sanitized path; it must never echo arbitrary commands or unrelated settings.
JSON parsing accepts only dictionaries/lists in the expected hook subtree and
ignores malformed entries rather than raising.

### Command matching

A hook is considered wired when a command-type entry references the normalized
suffix `.claude/hooks/smart-trim.py` for Claude or
`.codex/hooks/smart-trim.py` for Codex. Matching does not execute a shell,
expand environment variables, or trust the command as a filesystem path.
This deliberately supports `~`, `$HOME`, and absolute-home spellings while
remaining narrow enough not to accept another `smart-trim.py`.

### Severity policy

| Condition | Level | Reason |
|---|---|---|
| Claude shim delegates to package entry | OK | Authoritative runtime entry is usable |
| Claude shim missing/unreadable/stale | FAIL | The configured event cannot reach the package |
| Claude hook configured with enough timeout | OK | Cascade can finish before host termination |
| Claude hook absent/malformed/wrong command | FAIL | PreCompact will not invoke smart-trim |
| Claude timeout missing | WARN | Host default is unknown |
| Claude timeout not greater than cascade budget | FAIL | Host can kill before fallback persistence |
| Codex config absent | no check | Codex integration is optional on other hosts |
| Existing Codex config not wired correctly | WARN | Claude remains the authoritative entry |

Timeout comparison uses a strict `timeout > CASCADE_BUDGET_SECONDS`; equality
has no allowance for session loading, redaction, archive rotation, or memory
writes.

### Boundaries

- No changes to hook execution, summarization, persistence, or global config.
- No writes outside the repository.
- No reads of credentials, environment files, or unrelated settings subtrees.
- No edits to files claimed by the active Claude session.
- Diagnostics stay zero-dependency and fail closed only in the explicit
  `doctor` command; the PreCompact runtime remains fail-open.

## Test matrix

| Case | Expected |
|---|---|
| Delegating shim | integrity OK |
| Existing non-delegating shim | integrity FAIL |
| Missing/unreadable shim | integrity FAIL |
| Valid Claude hook, timeout above budget | wiring OK |
| Valid hook with missing timeout | wiring WARN |
| Timeout equal to/below budget | wiring FAIL |
| Malformed JSON or wrong subtree type | wiring FAIL without exception |
| Multiple entries with one valid smart-trim command | valid entry selected |
| Existing Codex config with wrong path | warning only |
| Report JSON | contains sanitized metadata, never raw command text |

## Rollback

The implementation is isolated to diagnostics, tests, and docs. Reverting the
new wiring module plus the `collect_checks()` integration restores the previous
doctor behavior without touching persisted handoffs or hook configuration.

## Validation

- 48 focused diagnostics, capabilities, and layout tests passed.
- Full suite passed: 327 tests, 97.4% coverage.
- `ruff check .`, `ruff format --check .`, `mypy src`, pyright, vulture,
  gitleaks, and offline architecture sensors passed.
- Live `doctor --json`: zero failures/warnings; Claude and Codex both report
  90-second timeouts against the 40-second cascade budget.
- Live smoke passed, and Claude/Codex shims are byte-identical to the tracked
  canonical shim through their symlinks.
- Final review found no raw command exposure or unrelated settings in reports.
