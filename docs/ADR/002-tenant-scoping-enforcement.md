# ADR-002: Backend Tenant Scoping Enforcement

- Status: Accepted
- Date: 2026-03-15
- Deciders: Trading Journal architecture owners

## Context
Shared DB row-level tenant ownership is safe only with strict server-side enforcement.

## Decision
Enforce tenant boundaries in backend services and data access, never in UI only.

Enforcement contract:
- Every tenant-owned service method receives tenant context.
- Every repository/query path filters by `tenant_id`.
- Cross-tenant access returns authorization error through standard error envelope.
- Write paths verify parent-child tenant consistency.

Data invariants:
- Tenant-owned FK relationships preserve tenant consistency where practical.
- Composite uniqueness and indexes include `tenant_id` when business meaning is tenant-local.

Verification:
- Negative tests for cross-tenant reads and writes.
- Policy tests that no tenant-owned endpoint bypasses tenant-filter dependencies.

## Consequences
Positive:
- Predictable security boundary.
- Lower accidental data leakage risk.

Tradeoffs:
- More service/repository boilerplate.
- Stronger review discipline required.

## Rejected Alternatives
- Client-side tenant filtering only:
  - rejected due to trivial bypass risk.
- Endpoint-by-endpoint optional tenant filtering:
  - rejected due to inconsistency and drift risk.
- DB-only enforcement with minimal service-level checks:
  - rejected for reduced domain-layer safety and clarity.

## Non-Goals
- Endpoint exemptions without explicit ADR-level approval.

## Related
- ADR-001 storage model.
- ADR-003 claim model supplying tenant context.
