# ADR-005: IBKR Import Idempotency, Staging, and Dedupe

- Status: Accepted
- Date: 2026-03-15
- Deciders: Trading Journal architecture owners

## Context
IBKR import must support replay, retries, and auditability without creating duplicate fills or incorrect trade matches.

## Decision
Use staging-first import with explicit run and record audit tables.

Chosen write path:
1. Fetch and normalize executions from adapter.
2. Stage normalized rows in `import_run_records`.
3. Resolve each record deterministically.
4. Write accepted records to `trade_fills`.
5. Mark unresolved/failed outcomes explicitly.

Dedupe key policy:
- Dedupe and uniqueness are tenant/account/source scoped.
- Canonical uniqueness target for broker fills:
  - (`tenant_id`, `broker_account_id`, `source`, `external_fill_id`)

Matching policy:
- Deterministic and conservative.
- If matching is ambiguous, do not guess.
- Mark record as unresolved for review.

`import_run_records` baseline status model:
- `staged`
- `duplicate_skipped`
- `resolved_inserted`
- `resolved_unresolved`
- `failed_validation`
- `failed_processing`

Mutability and audit rules:
- Raw broker payload snapshot and normalized identity fields are immutable after staging.
- Resolver updates are status-driven and audit-attributed.
- Terminal status records are immutable.
- Corrections are modeled as explicit superseding actions, not destructive overwrite.

Idempotency policy:
- Import request includes idempotency key.
- Same key + same scope returns same import run lineage.
- Retries are side-effect safe (no duplicate fills, no duplicate summary inflation).

Source-of-truth policy:
- Broker executions are external truth.
- `trade_fills` are internal accounting truth.
- Trade and analytics metrics are derived from fills.

## Consequences
Positive:
- Strong auditability and replay safety.
- Deterministic behavior under retries and partial failures.

Tradeoffs:
- Additional tables and processing stage before final write.

## Rejected Alternatives
- Direct write into `trade_fills` without staging:
  - rejected due to weaker audit/replay semantics.
- Dedupe key without tenant/account scope:
  - rejected due to cross-tenant collision risk.
- Aggressive auto-matching on ambiguous records:
  - rejected due to data integrity risk.

## Non-Goals
- Real-time stream ingest in Phase 1.
- Options/multi-leg reconciliation in Phase 1.
- Full broker position reconciliation in Phase 1.

## Related
- ADR-001 tenant storage model.
- ADR-004 async job lifecycle.
