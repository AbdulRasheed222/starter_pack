# starter_pack

<!-- [module:setup] -->
A starter for AI SaaS products on **FastAPI** and **Next.js**: sign-in, team workspaces with roles and invites, tenant isolation that is tested on every endpoint, answers from your customers' documents with checked citations, AI spending caps, Stripe subscriptions, background jobs, email, an operator admin page, and English, Turkish and Arabic with right-to-left layout.

It is built from code that runs in [Answervera](https://www.answervera.com), with the product taken out.

## Start a project

```sh
git clone https://github.com/AbdulRasheed222/starter_pack my-product
cd my-product && rm -rf .git && git init
python3 setup_project.py        # asks for a name and which modules to keep
```

The setup script deletes the modules you don't want, along with their tables, pages, settings, tests and translations, then deletes itself. CI runs it with every combination of modules and checks that each result passes its tests and builds.

| Module | What it adds | Without it |
| --- | --- | --- |
| `ai` | Documents, cited answers, model providers, usage ledger and spending caps | No pgvector, no model download, no AI keys |
| `billing` | Stripe plans, checkout, customer portal, webhook | Every workspace is on one free plan |
| `notes` | The example feature | The workspace home goes to the first page that exists |
<!-- [/module:setup] -->

## What you get

| | |
| --- | --- |
| **Sign-in** | [Clerk](https://clerk.com). The API checks each session token's signature, expiry, issuer and origin. Clerk says who someone is; workspaces and roles live in your own database. |
| **Workspaces** | Every customer record belongs to a workspace. Roles: owner, admin, member. A workspace always keeps an owner. |
| **Invites** | One-time links, emailed to the invitee, that expire after 7 days and only work for the invited email. Only a hash of the token is stored. |
| **Tenant isolation** | [`test_tenant_isolation.py`](backend/tests/test_tenant_isolation.py) reads every route from the app and calls it from the wrong workspace, expecting a 404. New endpoints are covered automatically, and unscoped ones must be listed with a reason. |
| **Background jobs** | A queue in Postgres, so there is nothing else to run. Retries with backoff, picks up jobs from crashed workers, and runs inside the API or as separate workers. See [docs/operations.md](docs/operations.md). |
| **Email** | Through [Resend](https://resend.com), sent by a job so a slow email service never slows a request. Logged to the console in development. |
| **Operator admin** | `/admin` lists every workspace and what it uses, for the user ids you list. Everyone else gets a 404. |
| **Languages** | English, Turkish and Arabic, chosen from the browser or a switcher. Arabic mirrors the layout. CI fails if a translation is missing. |
| **Ask your documents** | Upload PDF, Word, Markdown or text; a background job reads and indexes it. Members ask questions and get streamed answers, each sentence linked to the passage it comes from. Citations are checked before they are shown. See [docs/ai.md](docs/ai.md). | <!-- [only:ai] -->
| **Any model** | Claude by default, or any OpenAI-compatible server (OpenAI, Ollama, vLLM). A fake provider runs the app and the tests without a key. | <!-- [only:ai] -->
| **Spending caps** | Every model call is costed in a usage ledger. A workspace that reaches its monthly budget gets a 429 until the month turns. Members see a usage page; operators can raise one workspace's cap. | <!-- [only:ai] -->
| **Search quality in CI** | An eval with the real embedding model checks that the right passage is found, in English, Turkish and Arabic, and fails the build if recall drops. | <!-- [only:ai] -->
| **Billing** | Stripe Checkout for upgrades and the Stripe customer portal for cards, invoices and cancelling. The webhook checks Stripe's signature, handles each event once, and reads the subscription's current state from Stripe, so events arriving out of order can't leave a workspace on the wrong plan. See [docs/billing.md](docs/billing.md). | <!-- [only:billing] -->
| **Example feature** | Notes, a small CRUD feature that shows the pattern to copy. Delete it when you add yours. | <!-- [only:notes] -->
| **CI** | Lint, tests on Postgres, migrations checked against the models and rolled back, web build, Docker image boot. |

## What is tested and what isn't

- **Tested in CI:** every API rule above on Postgres 16, including that one workspace never sees another's data, the job queue's retries and locking, and that every language has every message. Migrations are checked against the models and rolled back, the web app builds, and the Docker image boots.
- **AI:** the Claude and OpenAI-compatible request and stream formats are tested against recorded responses, and search recall is measured with the real embedding model. No test calls a live model; try one question with your key before you ship. <!-- [only:ai] -->
- **Billing:** tested against a fake Stripe client, with webhook signatures checked by Stripe's own library. No test calls Stripe; run one checkout in [test mode](docs/billing.md#try-it) before you ship. <!-- [only:billing] -->
- **Not tested against live services:** Resend and Clerk. Send yourself an invite before you ship.
- **Not yet checked in a browser:** the signed-in pages, which need a Clerk development instance. The Turkish and Arabic text is a first draft; have a native speaker review it before production.

## Run it locally

You need Docker, [uv](https://docs.astral.sh/uv/) and Node 22.

```sh
docker compose up -d                      # Postgres, "app" and "app_test" databases

cd backend
cp .env.example .env                      # set CLERK_ISSUER (docs/clerk.md) and any other keys
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

1. Add a table with a `workspace_id` column (see `Membership` in [`models.py`](backend/src/app/models.py)), then `uv run alembic revision --autogenerate -m "…"`.
2. Put its routes under `/workspaces/{workspace_id}/…` and depend on `Member`, `Admin` or `Owner` from [`tenancy.py`](backend/src/app/tenancy.py). Load single rows with `owned(...)`.
3. If a route has a new path parameter, teach `ids_for` in the isolation test how to fill it. The test fails until you do.
4. Slow or unreliable work (emails, calls to other services, file processing) goes in a job: write a function with `@handler("kind")` and call `enqueue(...)` from the route.
5. Add its strings to `web/messages/en.json` and the other languages.

## Layout

```
backend/   FastAPI app (src/app), Alembic migrations, tests
web/       Next.js app, messages/ for translations
docs/      Clerk, deployment, operations, and one page per module
eval/      documents and questions for the search eval
```

## License

MIT
