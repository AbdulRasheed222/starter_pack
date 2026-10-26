# Deploying

Any host that runs a container and any host that runs Next.js will do. These steps use Railway for the API and Vercel for the web app, because they need no server management.

## Database

Create a Postgres 16 database. Use its connection string with the `postgresql+psycopg://` prefix.

<!-- [module:ai] -->
The AI module needs the pgvector extension (Neon, Supabase and the `pgvector/pgvector` image have it; check your host). Its migration runs `CREATE EXTENSION vector`, which needs the database owner's role.
<!-- [/module:ai] -->

## API

Build from the repository root with the `Dockerfile`. Migrations run on every start.

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | your connection string |
| `CLERK_ISSUER` | your Clerk production instance's Frontend API URL |
| `CORS_ORIGINS` | the web app's URL, e.g. `https://app.example.com` |
| `SITE_URL` | the same URL, used in invite links |
| `EMAIL_BACKEND`, `RESEND_API_KEY`, `EMAIL_FROM` | see `operations.md`; without them invites are only logged |
| `ADMIN_USER_IDS` | your Clerk user id, to open `/admin` |
| `ANTHROPIC_API_KEY` | from the Claude Console, or see `ai.md` for other providers | <!-- [only:ai] -->
| `AI_MONTHLY_BUDGET_USD` | the spending cap per workspace per month | <!-- [only:ai] -->
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PRO` | see `billing.md` | <!-- [only:billing] -->

Check it with `curl https://your-api/healthz`.

Background jobs run in a thread of the API. To run them separately, add a second service from the same image with the start command `uv run python -m app.worker`, and set `JOBS_WORKER_IN_API=false` on the API (see `operations.md`).

<!-- [module:ai] -->
The embedding model (about 1 GB) downloads to `/app/models` on the first upload or question. Mount a volume there, or every restart downloads it again. Give the API more than 1 GB of memory, since the model is loaded into it.
<!-- [/module:ai] -->

## Web

Deploy the `web/` folder to Vercel (set it as the root directory).

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | the API's URL |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | from Clerk's production instance |
| `CLERK_SECRET_KEY` | from Clerk's production instance |

`NEXT_PUBLIC_` values are built into the browser bundle, so redeploy after changing them.

## Before going live

- Use a Clerk **production** instance with your own domain, and add the email claim (see `clerk.md`).
- Send yourself an invite to check that email arrives.
- Switch Stripe to live mode and add the production webhook (see `billing.md`). <!-- [only:billing] -->
- Have a native speaker review `web/messages/tr.json` and `ar.json`.
