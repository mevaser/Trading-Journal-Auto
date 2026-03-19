## Full-System Delivery Plan: Trading Journal (Threaded Engineering Team)

### Summary
Build from current state (working FastAPI + fills/trades + Streamlit + IBKR skeleton) to a multi-tenant, production-ready system using **milestone waves** with **6 parallel Codex threads per wave**.  
Each thread is one small, independent task with strict deliverables, dependencies, and gate criteria.

### Locked Decisions
- Product milestone priority: **IBKR Import + Journal Core first**
- UI path: **Streamlit-first**
- Deployment target: **Multi-tenant cloud SaaS**
- Tenant architecture: **Shared DB + `tenant_id`**
- Async processing: **Celery + Redis**
- Execution cadence: **Milestone waves**
- Parallelism: **6 threads per wave**

### Public Interfaces/Type Changes (Planned)
- Add tenant-scoped auth and context:
  - JWT claims include `tenant_id`, `user_id`, `roles`
  - API dependency injects tenant context
- Extend DB schema:
  - `tenants`, `users`, `memberships`, `import_runs`, `broker_accounts`, `job_runs`
  - Add `tenant_id` to tenant-owned entities (`trades`, `trade_fills`, `market_data`, future analytics tables)
- Add API surface:
  - `/auth/*`, `/tenants/*`, `/broker/ibkr/import`, `/imports/*`, `/analytics/*`, `/reports/*`, `/health/*`
- IBKR adapter contract finalized:
  - `fetch_executions(start_time, end_time, account_ref) -> list[ExecutionDTO]`
  - Stable `external_fill_id` mapping and duplicate semantics
- Background job contracts:
  - Queue tasks for imports, market sync, report generation
  - Idempotency keys + run metadata persisted in `job_runs`/`import_runs`

### Wave Plan (6 Threads Per Wave)

#### Wave 0: Project Baseline and Standards
1. `W0-T1` Architecture baseline doc refresh and ADR set (tenanting, jobs, auth, imports).
2. `W0-T2` CI pipeline hardening (tests, lint, migration checks, API contract checks).
3. `W0-T3` Environment profiles (`dev/stage/prod`) with deterministic settings/secrets strategy.
4. `W0-T4` Observability baseline (structured logging, request IDs, error taxonomy).
5. `W0-T5` Local platform bootstrap (`docker-compose` for api/db/redis/worker/streamlit).
6. `W0-T6` Wave integration gate: verify branch protections and merge checklist.

#### Wave 1: Multi-Tenant Identity and Authorization
1. `W1-T1` DB migrations for `tenants/users/memberships` + `tenant_id` columns.
2. `W1-T2` Auth service (password hashing, login, token issue/refresh, role model).
3. `W1-T3` API auth middleware/dependencies and tenant scoping enforcement.
4. `W1-T4` Backfill strategy for existing data to default tenant and user mapping.
5. `W1-T5` Security tests (cross-tenant access denial, permission matrix).
6. `W1-T6` Integration gate: all existing trade/fill endpoints tenant-safe without regressions.

#### Wave 2: Core Domain Hardening (Trade/Fill Integrity)
1. `W2-T1` Enforce DB constraints/indexes for fill consistency and query performance.
2. `W2-T2` Service-level invariants for open/partial/closed transitions and edge cases.
3. `W2-T3` Pagination/filtering/sorting standards on trade/fill APIs.
4. `W2-T4` API error model unification (typed errors + stable response shape).
5. `W2-T5` Contract tests for backward-compatible API behavior.
6. `W2-T6` Integration gate: performance + correctness baseline signed off.

#### Wave 3: IBKR Import V1 (Manual Trigger, Safe Matching)
1. `W3-T1` Concrete IBKR adapter implementation (ib-insync) with normalization and UTC guarantees.
2. `W3-T2` Duplicate detection (`source + external_fill_id`) and unique constraints.
3. `W3-T3` Trade resolution policy implementation (safe attach vs create new trade).
4. `W3-T4` Import orchestration service + `/broker/ibkr/import` admin endpoint.
5. `W3-T5` Import summary/audit persistence (`import_runs` + per-record outcomes).
6. `W3-T6` Integration gate: replay/idempotency tests on realistic execution batches.

#### Wave 4: Async Jobs and Scheduled Operations
1. `W4-T1` Celery worker setup with Redis and retry/backoff policies.
2. `W4-T2` Move import execution into background jobs with job status APIs.
3. `W4-T3` Market data sync jobs (SPY/QQQ baseline) + storage/update policies.
4. `W4-T4` Scheduled run framework (manual + recurring) with tenant-safe task ownership.
5. `W4-T5` Failure handling/alerts and dead-letter strategy.
6. `W4-T6` Integration gate: load tests for queue throughput and failure recovery.

#### Wave 5: Analytics and Reporting Core
1. `W5-T1` Portfolio KPI service (returns, win rate, expectancy, drawdown).
2. `W5-T2` Benchmark comparison engine (portfolio vs SPY/QQQ over selectable windows).
3. `W5-T3` Strategy-level analytics slices and filters.
4. `W5-T4` Report generation service (daily/weekly summary payloads).
5. `W5-T5` `/analytics/*` and `/reports/*` API contracts with versioning.
6. `W5-T6` Integration gate: statistical correctness tests against fixture datasets.

#### Wave 6: Streamlit Productization (Primary UI)
1. `W6-T1` Authenticated Streamlit session flow with tenant context.
2. `W6-T2` Trade/fill management screens aligned to new APIs.
3. `W6-T3` Import control center (trigger, run history, failures, replay actions).
4. `W6-T4` Analytics dashboards (portfolio, benchmark, strategy views).
5. `W6-T5` UX polish + responsiveness + empty/error/loading state standards.
6. `W6-T6` Integration gate: end-to-end user workflows validated for primary personas.

#### Wave 7: Production Readiness and Launch
1. `W7-T1` Cloud deployment manifests/pipelines for api/worker/redis/db/streamlit.
2. `W7-T2` Secrets, IAM, and security hardening (OWASP-focused checks).
3. `W7-T3` Backup/restore, migration rollback, and disaster recovery playbooks.
4. `W7-T4` SLOs, dashboards, alerts, and incident runbooks.
5. `W7-T5` UAT and staged rollout plan (pilot tenants, feature flags, cutover criteria).
6. `W7-T6` Final launch gate: go-live checklist and post-launch monitoring protocol.

### Test Plan and Acceptance Criteria
- Unit tests:
  - Trade calculations, import mapping, duplicate detection, tenant auth guards
- Integration tests:
  - Full API flows with tenant isolation and background jobs
- Contract tests:
  - Stable schemas for trade/fill/auth/import/analytics endpoints
- End-to-end tests:
  - User login -> import IBKR -> verify fills -> analytics dashboard -> report
- Non-functional:
  - Performance baselines for list/import/analytics endpoints
  - Reliability checks for retries/idempotency
  - Security checks for cross-tenant isolation and auth failures

### Assumptions and Defaults
- Existing FastAPI + SQLAlchemy + Alembic stack remains primary backend.
- Streamlit remains customer-facing UI through first production launch.
- React archive remains out of scope until after Wave 7.
- IBKR V1 supports equities-focused execution import only.
- Every thread delivers via short-lived branch + PR + gate tests; no direct merges.
- A wave is complete only when `T6` integration gate passes and unresolved defects are closed.
