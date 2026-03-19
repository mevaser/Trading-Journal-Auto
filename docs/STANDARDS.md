# Trading Journal Engineering Standards Baseline (Wave 0 Task 1)

## Status
- Phase: Wave 0 Task 1 (documentation only)
- Scope: Enforceable standards baseline for Waves 1-4 delivery
- Runtime impact: None

## Related Decisions
- [ADR-001 Shared DB + tenant_id](./ADR/001-shared-db-tenant-id.md)
- [ADR-002 Backend tenant scoping enforcement](./ADR/002-tenant-scoping-enforcement.md)
- [ADR-003 JWT auth and role claims](./ADR/003-auth-jwt-claims.md)
- [ADR-004 Celery + Redis jobs](./ADR/004-celery-redis-jobs.md)
- [ADR-005 IBKR import idempotency and dedupe](./ADR/005-ibkr-import-idempotency.md)

## Core Enforcement Rules
- Tenant boundaries are enforced in backend services and repositories only, never UI-only.
- Tenant-owned tables must include `tenant_id`.
- Tenant-local uniqueness must be tenant-scoped.
- Cross-tenant read/write behavior is forbidden except explicit platform-admin paths.
- Fill/trade derived metrics must be service-calculated, never manually persisted from API clients.

## API Standards
- API routes validate input, delegate business behavior to services, and return standardized envelopes.
- Business logic must not be placed in route handlers.
- Error responses must use the shared envelope:
  - `error.code`
  - `error.message`
  - `error.details` (optional)
  - `error.request_id`
  - `error.retryable`
- Endpoint behavior must be deterministic under retries for idempotent operations.

## Auth and Authorization Standards
- API accepts backend-issued JWT only.
- Required authorization context:
  - identity (`sub`)
  - active tenant (`tenant_id`)
  - active tenant roles (`roles`)
- Every tenant-owned endpoint enforces membership and role checks server-side.
- Session invalidation and refresh behavior follow ADR-003 lineage model.

## Import and Async Standards
- Import flow is staging-first; no direct write path to final accounting tables for broker payloads.
- Dedupe keys for broker-imported fills are tenant/account/source scoped.
- Ambiguous matching outcomes must be explicit unresolved statuses (no guessed attach).
- Async jobs must persist execution attempts (`job_runs`) and business run state (`import_runs`).

## Database and Migration Standards
- All schema changes require Alembic migrations.
- Migrations must be forward-only and reproducible.
- Tenant-owned foreign-key paths must preserve tenant consistency by constraint or service invariant.
- Backfills must be explicit and idempotent; no silent destructive rewrites of staged import data.

## Testing Standards
- Any behavior change must include or update tests.
- Minimum required coverage areas for new tenant-owned features:
  - tenant-scope positive tests
  - cross-tenant negative tests
  - error-envelope contract tests
- Minimum required coverage areas for import/async features:
  - idempotent retry behavior
  - dedupe behavior
  - unresolved/failed status behavior

## Observability and Operations Standards
- Mutating operations should emit request correlation identifiers.
- Import/job lifecycle state transitions must be auditable.
- Retry policies must be bounded and explicit for worker jobs.

## Delivery and Review Standards
- Small, incremental changes over large refactors.
- Preserve existing architecture boundaries unless explicit task scope says otherwise.
- PR/review acceptance for Waves 1-4 requires:
  - conformity with ADR-001..005
  - conformity with this standards baseline
  - tests passing for changed behavior

## Change Control
- Any exception to these standards requires explicit ADR or architecture note update before implementation.
