# Wave 0 Task 6: Integration Gate (Branch Protection + Merge Checklist)

## Objective
Verify that merge controls are in place before Wave 1 starts:
- Branch protections are enforced on integration branches.
- Pull requests follow a merge checklist.

## Verification Date
- 2026-03-17

## In-Repository Verification

### Present
- CI workflow exists at `.github/workflows/ci.yml`.
- CI defines three jobs suitable for required status checks:
  - `Lint`
  - `Tests`
  - `Migration Check`
- PR merge checklist template exists at `.github/pull_request_template.md`.

### Missing
- No CODEOWNERS file found (`.github/CODEOWNERS`).
- No repository-tracked branch protection policy file found.

## GitHub Settings Verification (Manual)
These checks must be confirmed in the repository settings UI (cannot be guaranteed from source files alone):

1. Protect `main`.
2. Require pull request before merge.
3. Require approvals (recommended: at least 1).
4. Require status checks to pass before merge:
   - `Lint`
   - `Tests`
   - `Migration Check`
5. Dismiss stale approvals on new commits.
6. Block force pushes.
7. Block branch deletion.
8. Restrict direct pushes to `main`.

## Merge Checklist Baseline (Required for Gate)
A PR must confirm:

- [ ] Scope matches task and excludes unrelated refactors.
- [ ] Tests added/updated for behavior changes.
- [ ] CI passes (`Lint`, `Tests`, `Migration Check`).
- [ ] DB migration included and validated when schema changes.
- [ ] Docs/ADR updated when architecture or standards change.
- [ ] Risk notes and rollback notes included.

## Gate Status
- Status: `PARTIAL PASS`
- Reason: PR checklist is now codified in-repo and CI checks are defined.
- Blocking item for full pass: branch protection rules must be confirmed/enforced in GitHub repository settings.
