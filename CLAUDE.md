# CLAUDE.md

Guidance for AI coding agents working in this repository.

## Commits

- Commits are authored by the repository owner only. Never add `Co-Authored-By` or any other AI trailer, and no AI footer in PR descriptions.
- Conventional Commits, lowercase subject of 72 characters or fewer: `feat(api): …`, `fix(web): …`.

## Commands

| Task | Command |
| --- | --- |
| Local Postgres | `docker compose up -d` (repository root) |
| Backend install | `cd backend && uv sync` |
| Backend tests | `cd backend && uv run pytest` |
| Lint and format | `cd backend && uv run ruff check . && uv run ruff format .` |
| New migration | `cd backend && uv run alembic revision --autogenerate -m "…"` |
| Web | `cd web && npm run typecheck && npm run check:messages && npm run build` |

Tests run on Postgres (`TEST_DATABASE_URL`, default `app_test` on localhost), never SQLite.

## Rules

- **Tenant isolation.** Every customer table has a `workspace_id`. Every route that touches one lives under `/workspaces/{workspace_id}/…`, depends on `Member`, `Admin` or `Owner` from `tenancy.py`, and loads single rows with `owned`. Non-members get 404, not 403. Never weaken `tests/test_tenant_isolation.py`; extend `ids_for` or `UNSCOPED` (with a reason) instead.
- **Languages.** Every user-facing string in the web app goes through `t()` with a key in all files under `web/messages/`. Use logical CSS properties (`margin-inline-start`, not `margin-left`) so right-to-left works.
- **Secrets.** `.env` files are never committed. Configuration comes from environment variables (`config.py`).
