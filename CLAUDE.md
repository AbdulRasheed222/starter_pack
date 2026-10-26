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

<!-- [module:setup] -->
## Modules

`setup_project.py` lets people remove the `ai`, `billing` and `notes` modules. Keep it working when you change code:

- Code that belongs to a module goes between `[module:NAME]` and `[/module:NAME]` comment lines (`# …` in Python, YAML and env files, `// …` in TypeScript, `/* … */` in CSS, `<!-- … -->` in Markdown). Marker lines are always deleted, so never put anything else on them.
- In a Markdown table or list, end a single line with `<!-- [only:NAME] -->` instead; a marker line would break the table.
- A file that belongs entirely to a module goes in `MODULE_FILES`; its translation keys go in `MODULE_MESSAGES`.
- Each module has its own migration. Changing a module's tables means changing its migration, not adding one that other modules depend on.
- CI's `setup` job runs the script with several module combinations. Locally: copy the repository, run `python3 setup_project.py --yes --without ai`, then the backend tests and web build.
<!-- [/module:setup] -->
