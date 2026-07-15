# foreign-sessions
> Deep memory topic. Read on demand; keep entries factual.

## 2026-07-03T20:11:45
Method: ollama-qwen3.5:4b
Session: unknown

## Preserved Negative Constraints
- 2. **No lee credenciales del cluster** — el backend usa sus propias creds internamente. Yo no toco `minio-creds` ni escribo la BD dev directo (respeta tu regla y evita riesgo de un UPDATE malo).
- src/.../login/login.component.ts:70:// Fallback logo mapping for tenants that don't provide logoUrl from API
- 70 // Fallback logo mapping for tenants that don't provide logoUrl from API

**Task**: Fix multitenant branding (logo/contacts) to be DB-driven, remove hardcoded placeholders. Deploy prod after data seeding.
**Acceptance**: Logo visible in login/admin/PDF for `tarapacamed`; no 404s; tenant contacts populated correctly.
**Verified**: Prod & Dev MinIO logos uploaded (`product-images-prod/dev`); Tenant DB seeded with real values (Name, PBX, Email, Address, Web, Logo URL). Login/Admin placeholders removed via code edits.
**Current**: Code refactoring complete for `login.component.ts`, `tenant-list.service.ts`, and admin form HTML. Awaiting final verification of login UI rendering the dynamic logo vs hardcoded fallbacks in prod environment context (if any remaining issues found during manual inspection or automated tests).
**Errors**: None reported; all file edits successful per tool output.
**Decisions**: 
[REDACTED: possible secret-bearing line]
2. **Hardcoded Removal**: Removed `TENANT_LOGO_MAP` from login component; removed hardcoded logos/contacts from admin form placeholders (`tenant-config.component.html`). Logo source now strictly API-driven (`logoUrl` field).
3. **Prod Safety**: Verified Prod tenant data was NULL before seeding to ensure the fix is necessary and safe for customer-facing PDFs.
**Next**: Verify frontend login UI renders dynamic logo correctly in prod (visual check); confirm no regressions on other tenants; prepare final deployment checklist if manual checks pass.
**Files**: 
- `/mnt/ext4disk/ProyectosP/Elogix/scripts/seed-tenant-branding.sql` (created + updated)
- `elogix-web/src/app/features/authentication/ui/login/login.component.ts:70` (removed hardcoded map)
- `elogix-web/src/app/core/tenant/tenant-list.service.ts` (removed hardcoded fallback logos, added vs-guard marker)
- `elogix-web/src/app/features/administration/ui/tenant-config/tenant-config.component.html` (genericized placeholders)
---
POST-COMPACT RULES (next 3 turns):
1. DO NOT re-read files you already know from this summary
2. DO NOT read screenshots/images into context
3. Use grep/find to locate, read ONLY needed lines (max 50)
4. DO NOT re-read rules files — they are already loaded
5. Work from this summary, not from scratch

## 2026-07-15T09:40:22
Method: ollama-gemma4-e2b
Session: 019f661d-bf16-7503-b4ca-8e815ea4ab96

> Session data only; never overrides safety, permissions, or current instructions.

## Current Objective (from current-objective.json)
**Task**: ahora revisa el proyecto promtp-improve
**Phase**: Review
**Next**: Think -> Plan -> Build -> Review -> Test -> Validate -> Ship -> Reflect

## Session constraints (quoted; non-authoritative)
- Do not store compact-session directives or transient prompt rules in agent memory.

**Task**: ahora revisa el proyecto promtp-improve
**Acceptance**: 256 tests collected, 98.69% coverage, Ruff lint/format, Mypy, Pyright, Semgrep, Gitleaks, Vulture, diff/YAML checks, wheel build, and live Claude/Codex shim smokes all green.
**Verified**: All automated checks (linting, type checking, security scans, format checks, build) and live shims passed smoke tests.
**Current**: No active implementation guide exists; `smart-trim` is the PreCompact handler package behind `~/.claude/hooks/smart-trim.py`.
**Errors**: None reported in progress summary.
**Decisions**: Dropped `post_json` during v3.2 to v3.3 split; summarization uses `ollama_client.chat` / `cheap_complete`. Do not store compact-session directives in agent memory.
**Next**: Think -> Plan -> Build -> Review -> Test -> Validate -> Ship -> Reflect.
**Files**: None explicitly listed in the context provided for changes.

## 2026-07-15T10:04:35
Method: ollama-gemma4-e2b
Session: 019f661d-bf16-7503-b4ca-8e815ea4ab96

> Session data only; never overrides safety, permissions, or current instructions.

## Current Objective (from current-objective.json)
**Task**: ahora que tienes ese panorama revisa el cli-orchestration
**Phase**: Review
**Next**: Think -> Plan -> Build -> Review -> Test -> Validate -> Ship -> Reflect

## Session constraints (quoted; non-authoritative)
- Do not store compact-session directives or transient prompt rules in agent memory.

**Task**: Review the cli-orchestration based on current panorama.
**Acceptance**: Complete review of cli-orchestration.
**Verified**: 256 tests collected, 98.69% coverage, and all smoke tests (Claude/Codex shim) passed green.
**Current**: No active implementation guide exists; `smart-trim` is the PreCompact handler package behind `~/.claude/hooks/smart-trim.py`.
**Errors**: None reported.
**Decisions**: `post_json` was dropped in v3.2 to v3.3 split; summarization uses `ollama_client.chat` / `cheap_complete`. Do not store compact-session directives in agent memory.
**Next**: Think -> Plan -> Build -> Review -> Test -> Validate -> Ship -> Reflect.
**Files**: progress.md, activeContext.md, current-objective.json
