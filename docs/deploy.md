# Deploying

Any host that runs a container and any host that runs Next.js will do. These steps use Railway for the API and Vercel for the web app, because they need no server management.

## Database

Create a Postgres 16 database with the pgvector extension available (Neon, Railway, Supabase and the `pgvector/pgvector` image all have it). The first migration runs `CREATE EXTENSION vector`, which needs the database owner's role. Use its connection string with the `postgresql+psycopg://` prefix.

## API

Build from the repository root with the `Dockerfile`. Migrations run on every start.

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | your connection string |
| `CLERK_ISSUER` | your Clerk production instance's Frontend API URL |
| `CORS_ORIGINS` | the web app's URL, e.g. `https://app.example.com` |
| `SITE_URL` | the same URL, used in invite links |
| `ANTHROPIC_API_KEY` | from the Claude Console, or see `ai.md` for other providers |
| `AI_MONTHLY_BUDGET_USD` | the spending cap per workspace per month |

Check it with `curl https://your-api/healthz`.

The embedding model (about 1 GB) downloads to `/app/models` on the first upload or question. Mount a volume there, or every restart downloads it again. Give the API more than 1 GB of memory, since the model is loaded into it.

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
- Have a native speaker review `web/messages/tr.json` and `ar.json`.
