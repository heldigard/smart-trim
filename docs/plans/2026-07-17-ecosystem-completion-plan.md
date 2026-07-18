# Ecosystem Completion Plan

**Date:** 2026-07-17

**Scope:** `smart-trim`, `prompt-improve`, `cli-orchestration`,
`fusion-local`, `cheap-llm`, and shared multi-CLI configuration.

## Objective

Complete a second autonomous pass after the broad ecosystem hardening audit.
Close remaining high-value quality, configuration, resilience, and maintenance
gaps without erasing or obscuring pre-existing worktree changes.

## Known residual opportunities

1. Increase headroom in always-loaded instructions; the current aggregate is
   11,920/12,000 tokens. Target at most 10,800 tokens (90%) by removing
   duplication and stale narrative, not by weakening authority boundaries or
   increasing the budget.
2. Close repository-wide formatter debt in `cheap-llm` now that the user has
   explicitly authorized the broader completion pass.
3. Revisit executable trust boundaries in shared MCP configuration and replace
   PATH lookup with stable absolute paths where that will not make version
   management brittle.
4. Align loopback URL handling across local-model consumers, including IPv6
   and the full IP loopback range, while continuing to reject credentials,
   queries, fragments, non-HTTP schemes, and remote hosts.
5. Resolve memory-bank warnings only through the supported memory helper and
   only when it can preserve useful history.
6. Re-run cross-project contracts, quality sensors, hook/config doctors, and
   full offline suites after implementation.

## Constraints

- Preserve every starting worktree modification and all unpushed commits.
- Do not inspect secrets, credential JSON, `.env*`, or `.ssh/*`.
- Do not add dependencies or architecture machinery without a concrete defect
  that existing lightweight checks cannot cover.
- Do not perform provider calls, deployments, outbound communication, commits,
  or pushes.
- Prefer bounded changes with focused regression coverage.

## Evidence and decisions

### Always-loaded rules

- `browser-automation.md` duplicates the full outbound-send prohibition already
  owned by `outbound-communication.md`; retain one short cross-reference in the
  browser rule and keep the authoritative safety contract intact.
- `context-protection.md` incorrectly says every CLI has an LSP. Replace that
  conflict with native LSP when available and `codeq` for Codex/non-LSP
  controllers.
- Compact historical origin stories and implementation detail from
  `skill-router.md` and `doc-fetch-discipline.md`; preserve active commands,
  thresholds, precedence rules, and security requirements.

### MCP execution

- `uv` and `uvx` resolve to stable binaries under `/home/eldi/.local/bin`; use
  those absolute paths in active Codex configuration.
- `npx` lives under a versioned NVM directory, so hard-coding that path would
  break on the next Node upgrade. Keep the NVM-managed executable lookup but
  pin every previously floating npm MCP package to its registry version.
- Preserve the already pinned Context7 version unless an upgrade is separately
  compatibility-tested. Pin Python tool packages when a registry version and
  existing command syntax can both be verified.

### Loopback endpoint boundary

- The three projects accept only literal `localhost`, `127.0.0.1`, and `::1`.
  Use `ipaddress.ip_address(host).is_loopback` so valid `127.0.0.0/8` and IPv6
  loopback literals work while arbitrary hostnames remain rejected.
- Preserve exact reconstruction with brackets for IPv6 and reject credentials,
  paths, params, queries, fragments, invalid/zero ports, HTTPS, and remote IPs.
- Add focused IPv4 and IPv6 tests in every affected project.

### Memory maintenance

- `smart-trim/progress.md` is at 85%; the supported compact helper currently
  compacts only at the hard budget. `cli-orchestration`'s 90% topic is an
  auto-generated active session registry.
- Run supported maintenance/compaction checks, but do not manually truncate or
  archive an active registry merely to silence a warning. A warning is
  intentional if the helper proves there is no history-preserving mutation.

## Bounded implementation slices

1. Compact and correct shared always-on rules; verify token and home-config
   audits immediately.
2. Pin floating MCP packages and anchor stable Python executables; run model,
   hook, shim, and home-config regression suites.
3. Generalize loopback validation in `smart-trim`, `prompt-improve`, and
   `cheap-llm`, each with local tests and security scans.
4. Run Ruff formatting over the full `cheap-llm` Python surface and review that
   the resulting changes are mechanical.
5. Run supported memory maintenance and record any intentionally retained
   warning.
6. Re-review all diffs, then execute full repository and cross-CLI validation.

## Risk controls

- Configuration pinning can break startup: resolve versions from primary
  registries, preserve CLI arguments, and exercise every shim/config doctor.
- URL normalization is security-sensitive: reject by default and test both
  allowed and denied boundaries before integration tests.
- Rule compaction can erase safety nuance: measure tokens after every slice and
  leave `outbound-communication.md` authoritative.
- Formatting can obscure logic: isolate formatter output from behavioral edits
  in review and run the complete behavioral suite afterward.

## Validation matrix

| Surface | Required gate |
|---|---|
| Rules/config | token budget, `audit-home-config --warnings-as-errors`, active-model config, hooks, shims, RTK |
| `smart-trim` | focused URL tests, full Pytest, Ruff check/format, Pyright, `codescan all` |
| `prompt-improve` | focused config tests, full Pytest, Ruff check/format, Pyright, `codescan all` |
| `cheap-llm` | 198-case offline runner, Pytest, Ruff check/format, Pyright, `codescan all` |
| Other repos | regression suites and aggregate sensors to prove shared configuration did not drift |
| Memory | `agent-memory compact --topics`, doctor, bounded read |

## Execution

1. Establish exact residual evidence and deepen this plan.
2. Implement independent bounded slices in the smallest affected repository or
   configuration surface.
3. Review diffs for behavior drift, duplication, and compatibility.
4. Run local suites and aggregate sensors.
5. Validate shared hooks, shims, model configuration, token budgets, and
   memory-bank health.
6. Record durable outcomes and remaining intentional non-actions.

## Exit criteria

- Always-loaded rules have useful growth headroom without weakening safety.
- All applicable repository formatter, lint, type, secret, SAST, and dead-code
  checks are clean.
- Local endpoint validation is consistent and regression-tested.
- Shared executable configuration is hardened wherever a stable path exists.
- Memory changes preserve history and leave no avoidable budget warning.
- All project and cross-CLI tests pass with clean diffs.

## Intentional non-goals

- Do not add Dependency Cruiser to Python-only repositories; the skipped
  JavaScript architecture sensor is not evidence of a missing Python gate.
- Do not create semantic indexes solely to remove informational doctor output.
- Do not replace an NVM-managed executable with a brittle version-specific
  absolute path.
- Browser testing and feature video are not applicable because this pass has
  no user interface or visual artifact.

## Completion snapshot

- Always-loaded rules were reduced from 11,920 to 10,797 tokens (89.98% of the
  budget). Outbound authorization remains canonical and complete; duplicated
  browser prose and stale LSP assumptions were removed.
- Active npm/Python MCP packages are version-pinned in the registry, source
  catalog, and Codex runtime block. Stable `uv`/`uvx` executables use absolute
  paths; NVM-managed `npx` remains portable.
- `smart-trim`, `prompt-improve`, and `cheap_bench` now accept the complete
  literal IP loopback range while rejecting remote or malformed endpoints.
- The full `cheap-llm` Python surface is Ruff-formatted. Its offline harness
  now removes and exactly restores optional provider credentials around live
  tests, preventing environment-dependent route assertions or accidental use
  of inherited credentials.
- Antigravity non-workspace access is disabled. Cross-CLI authority, hook,
  shim, model, MCP, RTK, and home-config gates pass.
- All five repositories pass their full offline suites and aggregate sensors
  with zero secrets, SAST findings, dead items, lint findings, or type
  diagnostics.
- Supported memory compaction found no safe/necessary archive operation.
  Preventive 85%/90% warnings remain intentionally because manual truncation
  would discard useful progress or an active auto-generated session registry.
