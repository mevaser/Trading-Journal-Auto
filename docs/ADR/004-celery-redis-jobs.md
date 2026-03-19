# ADR-004: Celery + Redis Job Architecture

- Status: Accepted
- Date: 2026-03-15
- Deciders: Trading Journal architecture owners

## Context
Import and scheduled operations are long-running and retry-sensitive, and should not block API request threads.

## Decision
Use Celery workers with Redis broker/backend for async and scheduled workloads.

Job lifecycle model:
- API creates tenant-scoped task payloads and enqueues Celery jobs.
- Worker creates/updates `job_runs` records with status transitions.
- Retries follow explicit retry policy (bounded retry count + backoff).
- Final outcome and metrics are persisted to `job_runs`.

Import relationship model:
- `import_runs` tracks business lifecycle of import requests.
- `job_runs` tracks execution attempts.
- One `import_run` may map to multiple `job_runs`.
- Client-facing import status comes primarily from `import_runs`.

Idempotency model:
- High-value operations (imports) carry idempotency keys.
- Retry execution must not duplicate domain side effects.
- `job_runs` tracks attempts and terminal state deterministically.

## Consequences
Positive:
- Durable execution path for imports and recurring jobs.
- Better observability and failure handling.

Tradeoffs:
- Additional operational components and monitoring requirements.

## Rejected Alternatives
- In-process scheduler as production primary mechanism:
  - rejected due to weak durability and scaling limits.
- External workflow platform in Phase 1:
  - rejected to keep stack and delivery scope controlled.
- Fire-and-forget workers without persisted run metadata:
  - rejected due to poor auditability.

## Non-Goals
- Replacing Celery/Redis in Phase 1.

## Related
- ADR-005 import-specific idempotency semantics.
