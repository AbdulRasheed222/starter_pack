# starter_pack

A starter for AI SaaS products on **FastAPI** and **Next.js**: sign-in, team workspaces with roles and invites, tenant isolation that is tested on every endpoint, and English, Turkish and Arabic with right-to-left layout.

It is built from code that runs in [Answervera](https://www.answervera.com), with the product taken out.

> **Status:** part 1 of 3. This is the foundation. Part 2 adds the AI module (model providers, streaming, usage and spending caps, evals in CI). Part 3 adds Stripe billing, background jobs, email, an admin page and a setup command that removes the modules you don't need.

## What you get

| | |
| --- | --- |
| **Sign-in** | [Clerk](https://clerk.com). The API checks each session token's signature, expiry, issuer and origin. Clerk says who someone is; workspaces and roles live in your own database. |
| **Workspaces** | Every customer record belongs to a workspace. Roles: owner, admin, member. A workspace always keeps an owner. |
| **Invites** | One-time links that expire after 7 days and only work for the invited email. Only a hash of the token is stored. |
| **Tenant isolation** | [`test_tenant_isolation.py`](backend/tests/test_tenant_isolation.py) reads every route from the app and calls it from the wrong workspace, expecting a 404. New endpoints are covered automatically, and unscoped ones must be listed with a reason. |
| **Languages** | English, Turkish and Arabic, chosen from the browser or a switcher. Arabic mirrors the layout. CI fails if a translation is missing. |
| **Example feature** | Notes, a small CRUD feature that shows the pattern to copy. Delete it when you add yours. |
| **CI** | Lint, tests on Postgres, migrations checked against the models and rolled back, web build, Docker image boot. |

## What is tested and what isn't

- **Tested in CI:** every API rule above (41 tests on Postgres 16), migrations up and down, the web build, that every language has every message, and that the Docker image boots.
- **Checked by hand:** the landing page in all three languages at desktop and phone width, including right-to-left.
- **Not yet checked in a browser:** the signed-in pages, which need a Clerk development instance. The Turkish and Arabic text is a first draft; have a native speaker review it before production.

## Run it locally

You need Docker, [uv](https://docs.astral.sh/uv/) and Node 22.

```sh
docker compose up -d                      # Postgres, with "app" and "app_test" databases

cd backend
cp .env.example .env                      # set CLERK_ISSUER, see docs/clerk.md
uv sync
uv run alembic upgrade head
uv run uvicorn app.api:app --reload       # http://localhost:8000/docs

cd ../web
cp .env.example .env.local                # set the two Clerk keys
npm install
npm run dev                               # http://localhost:3000
```

Tests: `cd backend && uv run pytest`.

## Adding a feature

1. Add a table with a `workspace_id` column (see `Note` in [`models.py`](backend/src/app/models.py)), then `uv run alembic revision --autogenerate -m "…"`.
2. Put its routes under `/workspaces/{workspace_id}/…` and depend on `Member`, `Admin` or `Owner` from [`tenancy.py`](backend/src/app/tenancy.py). Load single rows with `owned(...)`.
3. If a route has a new path parameter, teach `ids_for` in the isolation test how to fill it. The test fails until you do.
4. Add its strings to `web/messages/en.json` and the other languages.

## Layout

```
backend/   FastAPI app (src/app), Alembic migrations, tests
web/       Next.js app, messages/ for translations
docs/      Clerk setup and deployment
```

## License

MIT
