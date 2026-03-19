# ADR-001: Shared Database with Tenant ID Ownership

- Status: Accepted
- Date: 2026-03-15
- Deciders: Trading Journal architecture owners

## Context
Phase 1 targets multi-tenant cloud SaaS while maintaining delivery speed and operational simplicity.

## Decision
Use a shared PostgreSQL database with row-level tenant ownership via `tenant_id`, enforced by backend authorization and query policy.

Rules:
- Every tenant-owned row includes `tenant_id`.
- Tenant-local uniqueness uses composite keys beginning with `tenant_id`.
- Indexes for tenant-owned tables begin with `tenant_id` for query selectivity.

## Consequences
Positive:
- Fastest path to multi-tenant SaaS.
- Lower operational complexity than physically isolating tenant schemas or databases in Phase 1.

Tradeoffs:
- Requires strict backend guardrails for tenant scoping and authorization.
- Security depends on consistent enforcement and test coverage.

## Rejected Alternatives
- Schema-per-tenant isolation in Phase 1:
  - rejected due to migration and operational overhead for current scope.
- Database-per-tenant isolation in Phase 1:
  - rejected due to provisioning, cost, and orchestration complexity.
- No tenant ownership column with implicit tenant context:
  - rejected because it weakens enforceability and audit clarity.

## Non-Goals
- Physical tenant isolation model changes in Phase 1.
- Cross-tenant analytics except explicit platform-admin operations.

## Related
- ADR-002 tenant enforcement policy.
- ADR-005 import dedupe keys are tenant-scoped.
