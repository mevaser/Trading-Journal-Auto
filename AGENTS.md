# AGENTS.md

This repository uses AI coding agents such as Codex.

## Working Style

- Always propose a short implementation plan before making changes.
- Break work into small, safe steps.
- After completing each step, stop and report results before moving to the next step.
- Prefer incremental implementation over large refactors.

## Git Workflow

- Always work on a branch named `codex/<task-name>`.
- Never commit or push directly to `main`.
- Agents may run:
  - `git add`
  - `git commit`
  - `git push`
    only for the current `codex/*` branch.
- Never merge branches.

## Shell Safety

Allowed commands:

- `python -m pytest`
- `uvicorn app.main:app --reload`
- `alembic upgrade head`
- `python scripts/*`

Forbidden commands:

- `git reset --hard`
- `git clean`
- deleting the database
- deleting project directories
- force-pushing
- modifying `.env` without explicit instruction

## Coding Rules

- Comments must be in English.
- Prefer small changes over large refactors.
- Keep business logic in services.
- Do not place business logic inside API routes.
- Preserve existing architecture unless the task explicitly requires changes.
- Keep backward compatibility when possible.
- Add or update tests when behavior changes.

## After Each Task

Report:

- files changed
- tests executed
- risks
- suggested commit message
