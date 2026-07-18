# Ecosystem Audit and Hardening Plan

**Date:** 2026-07-17

**Scope:** `smart-trim`, `cli-orchestration`, `prompt-improve`, `fusion-local`,
`cheap-llm`, and their shared hook/router/CLI configuration.

**Mode:** autonomous, safe defaults; preserve all pre-existing worktree changes.

## Objective

Review the five cooperating projects as one execution pipeline, identify
correctness, security, resilience, performance, routing, documentation, and
operability gaps, implement the highest-value reversible improvements, and
validate both each repository and the cross-project contracts.

## Baseline and constraints

- Every repository begins with local modifications; `cli-orchestration` and
  `cheap-llm` also have unpushed commits. Existing changes are treated as user
  work and must not be reverted or reformatted wholesale.
- No secrets, credential files, `.env*`, `.ssh/*`, or credential JSON may be
  read. Configuration review is limited to schemas, commands, paths, routing,
  permissions, symlinks, and redacted/local diagnostics.
- No live provider calls, paid inference, production deploys, outbound
  communication, or destructive cleanup are required for this audit.
- Hook and router paths are compatibility surfaces. Package code should remain
  authoritative and harness files should stay thin shims.
- Security/auth, architecture, and integration decisions remain with the
  controller. Independent agents may inspect bounded repositories read-only;
  the controller reviews every claim and owns all edits.

## Current worktree themes to preserve and verify

1. **smart-trim:** bounded/validated numeric configuration, loopback-only
   Ollama URL, and locked/durable topic writes.
2. **cli-orchestration:** safer reflection, bounded subprocess capture,
   transactional memory updates, Grok worker routing, and model-score refresh.
3. **prompt-improve:** bounded stdin/HTTP responses, durable cache/metrics
   writes, corrupt-cache eviction, and deterministic model selection.
4. **fusion-local:** worker process-tree cleanup, Grok subscription seat, Kimi
   K3 aliases, and related panel contract updates.
5. **cheap-llm:** refreshed provider/model cascade and fallback ordering.

## Deepened review model

### A. Contract and dependency graph

- Trace each public entry point, shim, executable, environment knob, and
  import/bootstrap edge.
- Compare producer/consumer assumptions for:
  `cheap-llm → fusion-local`, `cli-orchestration → workers`,
  `prompt-improve → cheap-llm/Ollama`, and `smart-trim → cheap-llm/Ollama`.
- Check version gates, result shapes, timeout budgets, output bounds, error
  semantics, model aliases, and provider/billing boundaries.
- Prefer a single source of truth when duplicated routing/configuration can
  drift, but avoid coupling independent packages merely to remove repetition.

### B. Correctness and failure boundaries

- Review all local diffs before editing.
- Exercise malformed input, oversized input/output, corrupt state, timeouts,
  subprocess descendants, concurrent writers, partial writes, missing tools,
  invalid environment values, and unavailable local/cloud tiers.
- Ensure hooks fail open where user interaction must continue and brokers or
  external dispatch fail closed where unsafe execution or conflicting writes
  would otherwise occur.
- Verify validation evidence is never fabricated and advisory LLM output is
  always treated as untrusted data.

### C. Security and privacy

- Verify local-model URLs are loopback-only where intended.
- Inspect hook command construction for shell interpolation, `eval`,
  auto-grants, unsafe PATH lookup, and unbounded output retention.
- Verify worker prompts are scrubbed before any external path and returned
  model/tool content cannot become executable instructions.
- Inspect non-secret CLI/Codex/Claude/Gemini/OpenCode configuration for
  absolute trusted paths, read-only worker modes, symlink integrity, approval
  decisions, and stale/duplicate MCP or hook registrations.
- Run repository-local secret and SAST sensors without printing secret values.

### D. Performance and operability

- Look for redundant model probes, repeated imports/config parsing, avoidable
  subprocesses, excessive fsync/locking, cache churn, sequential fallbacks that
  violate total budgets, and large in-memory reads.
- Keep hot hooks bounded and deterministic. Any durability cost added to a hot
  path must protect genuinely durable state and remain fail-safe.
- Check capability/doctor surfaces accurately describe installed behavior and
  recovery semantics.

### E. Documentation and durable context

- Reconcile README/CLAUDE/model-routing claims with implementation.
- Update only durable decisions and current state in `.memory-bank`; do not
  store logs, transcripts, raw diffs, or ephemeral test output.
- Record deferred findings with severity, evidence, and a concrete next action.

## Execution phases

1. **Think / baseline**
   - Capture branch/status/diff summaries, package metadata, executable
     availability, and current quality-sensor capabilities.
   - Run narrow baseline tests and lint to distinguish existing failures from
     regressions.
2. **Plan / deepen**
   - Obtain an independent five-field Fusion analysis of the ecosystem risks.
   - Split read-only audits by independent repository groups; consolidate
     findings into one prioritized backlog.
3. **Build**
   - Fix confirmed P0/P1 correctness or security defects first.
   - Add focused regression tests before or with each behavior change.
   - Apply P2 optimizations only when evidence shows useful impact and the
     change does not destabilize compatibility.
4. **Review**
   - Re-read every diff in context, run `git diff --check`, and verify changes
     do not overwrite the starting work.
   - Resolve actionable review findings; document intentional deferrals.
5. **Test / validate**
   - Run repository-specific offline suites, Ruff checks, and format checks.
   - Run the narrowest useful `codescan` sensors, plus hook/shim doctors and
     smoke tests that perform no paid or outbound work.
   - Validate cross-project entry points, version contracts, routes, and
     capability JSON from a neutral working directory.
6. **Ship / reflect**
   - Update affected memory banks with durable facts only.
   - Leave commits/pushes untouched unless explicitly warranted by the task;
     report exact repository status and any remaining risks.

## Validation matrix

| Project | Required offline validation |
|---|---|
| smart-trim | `pytest`, Ruff check/format, layout gate, hook smoke |
| cli-orchestration | `pytest`, compileall, Ruff check/format, mypy if available, doctor/config tests |
| prompt-improve | `pytest`, Ruff check/format, CLI capabilities/detect smoke |
| fusion-local | offline panel/delegate tests, Ruff check/format, capability smoke |
| cheap-llm | offline behavioral suite, contract/shim pytest, Ruff check/format, route-plan/probe without inference |
| shared config | hook/shim verification, safe symlink check, redacted routing/config audit |

## Exit criteria

- Confirmed high-impact defects in scope are fixed with regression coverage.
- All applicable offline tests and lint gates pass, or remaining failures are
  clearly identified as pre-existing/external with evidence.
- Cross-project contracts agree on model IDs, timeouts, provider boundaries,
  output schemas, and fail-open/fail-closed behavior.
- Final diffs are scoped, reviewable, free of whitespace errors, and preserve
  all unrelated starting changes.
- Durable project memory reflects the implemented state and outstanding risks.

## Completion snapshot

- Added bounded, contention-safe file locking to the two hot-hook writers and
  protected cache eviction from concurrent replacement.
- Bounded control-plane subprocess output at the producer, made paired memory
  publication rollback-safe, hardened project/sensitive-path resolution, and
  completed Grok routing metadata.
- Removed unconditional DeepInfra fallback attempts, validated benchmark
  endpoints, and aligned cascade tests, metadata, and documentation.
- Completed Fusion process-tree cleanup and five-seat subscription routing;
  restored its catalog facade and aligned first-party DeepSeek contracts.
- Synchronized Codex model/effort defaults, repaired the benchmark shim,
  removed one exact broken skill symlink, and brought always-loaded rules back
  under budget without raising the limit.
- All five repositories finish with zero findings from the aggregate secrets,
  SAST, dead-code, lint, and type sensors. Offline suites, hook/shim/config
  checks, RTK checks, and whitespace validation pass.
- One advisory Fusion deliberation was run during review: three subscription
  panel responses succeeded, two timed out, and the low-cost judge completed
  for approximately USD 0.000869. No deployment or outbound communication was
  performed.
