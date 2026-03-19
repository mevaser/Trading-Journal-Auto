# ADR-003: JWT Auth and Tenant Role Claims

- Status: Accepted
- Date: 2026-03-15
- Deciders: Trading Journal architecture owners

## Context
Phase 1 requires backend-authoritative authentication/authorization usable by API, jobs, and Streamlit.

## Decision
Use JWT-based auth with tenant-scoped claims and backend validation.

Required claims:
- `sub`: user id
- `tenant_id`: active tenant context
- `roles`: active tenant role list
- `session_id`: token lineage/session tracking
- `iat`, `exp`, optional `nbf`
- optional `jti` for revocation tracking

Authorization model:
- Identity/auth is separated from membership/authorization concerns.
- Membership records determine whether user can act in requested tenant.
- Roles are interpreted server-side per tenant.

Phase 1 token/session baseline:
- Access tokens are short-lived (target 15 minutes).
- Refresh token flow is supported as the standard renewal direction.
- Refresh tokens are bound to `session_id` and revocable.
- Session invalidation revokes the session lineage and blocks subsequent refresh/access issuance.
- Password reset or explicit admin lock invalidates active sessions for affected user.

Session rule:
- Streamlit consumes backend-issued tokens only.
- No UI-local session auth fork is allowed.

## Consequences
Positive:
- One auth model across API and UI.
- Clear boundary between identity and tenant membership.
- Predictable session invalidation behavior.

Tradeoffs:
- Requires refresh-token persistence/revocation strategy.
- Requires clear operational playbooks for token/session incidents.

## Rejected Alternatives
- Long-lived access tokens without refresh flow:
  - rejected due to elevated compromise window.
- UI-only session model independent of backend tokens:
  - rejected due to authorization drift risk.
- Stateless-only revocation with no session lineage:
  - rejected due to weak invalidation guarantees.

## Non-Goals
- Social login and SSO in Phase 1.
- Device-level trust management in Phase 1.

## Related
- ADR-002 tenant scoping enforcement.
- Architecture baseline error envelope and cross-cutting invariants.
