# Trading Journal Architecture Baseline (Wave 0 Task 1)

## Status
- Phase: Wave 0 Task 1 (documentation only)
- Scope: Decision baseline for Waves 1-4
- Runtime impact: None

## Decision References
- [ADR-001 Shared DB + tenant_id](./ADR/001-shared-db-tenant-id.md)
- [ADR-002 Backend tenant scoping enforcement](./ADR/002-tenant-scoping-enforcement.md)
- [ADR-003 JWT auth and role claims](./ADR/003-auth-jwt-claims.md)
- [ADR-004 Celery + Redis jobs](./ADR/004-celery-redis-jobs.md)
- [ADR-005 IBKR import idempotency and dedupe](./ADR/005-ibkr-import-idempotency.md)
- [Engineering standards baseline](./STANDARDS.md)

## System Context

Trading Journal is a Streamlit-first, backend-centric trading analytics system.
Phase 1 priority is IBKR execution import + journal core correctness, then async operations.

High-level topology:
- Streamlit UI (primary user interface in Phase 1)
- FastAPI API (auth, journal, import, analytics APIs)
- Domain services (trade/fill lifecycle, import resolution, analytics)
- PostgreSQL (shared DB with row-level tenant ownership and backend tenant enforcement)
- Redis + Celery (background jobs and scheduling)

## Bounded Domains
- Identity and Access:
  - user identity, login, token issuance, token lifecycle
- Tenant Membership and Authorization:
  - tenant entities, user membership, role assignment, access checks
- Trading Journal Core:
  - trades, fills, trade recalculation, lifecycle invariants
- Broker Import:
  - external execution fetch/normalize, staging, resolution, dedupe, ingest
- Jobs and Scheduling:
  - background execution, retry lifecycle, idempotency, run observability
- Analytics and Reporting:
  - read models and metrics derived from fills/trades; reporting as cached outputs

## Cross-cutting Invariants
- Tenant ownership is explicit and enforced server-side on every tenant-owned read and write.
- All API failures return one stable error envelope shape.
- Broker import is idempotent and deterministic under retries.
- Ambiguous broker matching never auto-attaches fills; unresolved outcomes are explicit.
- Derived metrics come from fills/trade services, not manual summary writes.
- Staged import records preserve auditability and cannot be silently rewritten.

## Source-of-Truth Policy
- External truth for broker data: broker execution records.
- Internal truth for journal accounting: `trade_fills`.
- Trade-level and portfolio-level metrics must be derived from fills and services.
- Reporting tables are cache/materialization artifacts only, never authoritative truth.

Market data policy for Phase 1:
- Benchmark market data is platform-managed shared reference data.
- Benchmark market data is not tenant-owned in Phase 1.

## Tenant Enforcement Rules and Invariants
- Every tenant-owned table has `tenant_id`.
- Every tenant-owned unique constraint is tenant-scoped when business meaning is tenant-local.
- Every service method handling tenant-owned entities receives tenant context.
- Every repository/query path filters by tenant context.
- Cross-tenant reads/writes are forbidden except explicit platform-admin operations.
- Foreign keys should preserve tenant consistency where practical:
  - either include tenant-compatible composite constraints
  - or enforce tenant equality in service invariants and DB checks.

Representative tenant-owned entities for Waves 1-4:
- `trades`, `trade_fills`
- `broker_accounts`, `import_runs`, `import_run_records`, `job_runs`

Platform-managed entities:
- `tenants`, `users`, `memberships`
- `memberships` is platform-managed but directly defines tenant authorization scope for user actions.
- benchmark `market_data` is platform-managed shared reference data in Phase 1.

## API Error Model Baseline
Error envelope must be stable before endpoint expansion:
- `error.code` (machine-readable stable identifier)
- `error.message` (human-readable summary)
- `error.details` (optional structured context)
- `error.request_id` (trace correlation)
- `error.retryable` (boolean for client behavior)

Auth, tenant, import, and async endpoints must conform to one shared error taxonomy.

## Auth Claims Model (Backend-Authoritative)
JWT claims baseline:
- `sub`: user id
- `tenant_id`: active tenant context
- `roles`: role list scoped to active tenant
- `session_id`: token/session lineage
- `iat`, `exp`, optional `nbf`
- optional `jti` for revocation tracking

Rules:
- Backend validates claims and tenant membership for every tenant-owned request.
- Streamlit must use backend-issued tokens and backend session semantics only.
- No UI-local authentication model is allowed.

## Job Lifecycle and Idempotency Model
Core entities:
- `import_runs`: business lifecycle of an import request
- `job_runs`: worker execution attempts
- `import_run_records`: per-execution staged outcome and audit detail

Relationship rules:
- One `import_run` may have multiple `job_runs`.
- `import_run` is the primary client-facing status source.
- `job_runs` provides operational execution detail and retry history.

Idempotency requirements:
- Import request accepts idempotency key.
- Replays/retries must return existing run state when the same key and scope are reused.
- Worker retries must not duplicate fills, import summaries, or audit records.

## import_run_records Baseline Status Model
Baseline statuses:
- `staged`: normalized execution persisted, not yet resolved
- `duplicate_skipped`: dedupe key matched existing imported fill
- `resolved_inserted`: accepted and inserted to `trade_fills`
- `resolved_unresolved`: matching ambiguous or policy-blocked, requires review
- `failed_validation`: payload invalid for import policy
- `failed_processing`: resolver/runtime failure

Status transition rules:
- Start at `staged`.
- Transition exactly once into one terminal status listed above.
- Terminal statuses are immutable.

## Staged Record Mutability and Audit Rules
- Raw broker payload snapshot and normalized identity fields are immutable after initial stage write.
- Resolver annotations (status, reason code, resolution metadata) are append-only from an audit perspective.
- Any correction uses explicit superseding metadata, not destructive overwrite.
- Every status mutation stores actor/system source and timestamp.
- Import summaries are derived from terminal staged statuses, not ad hoc counters.

## IBKR Import Flow (Phase 1)
Chosen approach: staging-first ingest (see ADR-005).

Flow:
1. User triggers manual import request.
2. API authenticates user and resolves tenant + broker account scope.
3. API creates/looks up `import_run` by idempotency key.
4. Celery job fetches broker executions via adapter.
5. Adapter normalizes executions to internal DTOs (UTC timestamps).
6. System writes normalized rows to `import_run_records` staging.
7. Resolver processes each staged record:
   - dedupe check with tenant/account/source/external id key
   - deterministic trade matching
   - ambiguous cases marked unresolved (no guessed attach)
   - accepted rows written to `trade_fills`
8. Trade recalculation runs through domain services.
9. `import_run` final status and counters are persisted.

## Request, Job, and Import Sequence Views

Request lifecycle:
1. Streamlit calls API with bearer token.
2. API validates JWT and tenant membership.
3. Service executes tenant-scoped operation.
4. Repository applies tenant-filtered query.
5. Response or standardized error envelope returned.

Job lifecycle:
1. API enqueues Celery task with tenant-scoped payload and idempotency key.
2. Worker claims task and creates `job_run` linked to `import_run`.
3. Worker executes logic with retry policy.
4. Worker writes attempt outcome to `job_run`.
5. `import_run` aggregates business status for client consumption.

Import lifecycle:
1. Import request accepted with idempotency key.
2. `import_run` created/reused.
3. External executions fetched and staged.
4. Per-record dedupe + deterministic resolution.
5. Fill insert + trade recalculation.
6. Summary persisted and surfaced to client from `import_run`.

## Phase 1 Explicit Out of Scope
- Options and multi-leg import logic
- Real-time streaming ingestion
- Automatic broker position reconciliation beyond execution import
- Multi-broker orchestration beyond IBKR
- Full React frontend replacement
- Custom UI-local auth/session model
- Portfolio cash ledger, dividends, and corporate actions
- Data warehouse/materialized OLAP redesign

## Wave Alignment Notes
- Wave 1:
  - identity/auth implementation
  - tenant membership/authorization implementation
  - stable API error model rollout
  - legacy data adoption/backfill as separate execution track
- Waves 2-4:
  - domain hardening, then IBKR import V1, then async job expansion
  - all changes must conform to ADR-001 through ADR-005







