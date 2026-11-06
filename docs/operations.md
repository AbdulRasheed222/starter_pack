# Operations

Background jobs, email and the operator admin page. These are part of every project; the setup script doesn't remove them.

## Background jobs

Work that is slow or can fail (sending email, calling another service, processing an upload) runs as a job instead of inside the request. The queue is a table in the same Postgres database, so there is nothing else to host. The code is in [`jobs.py`](../backend/src/app/jobs.py).

```python
from app.jobs import enqueue, handler

@handler("send_welcome")
def send_welcome(session, payload):
    ...  # raise PermanentError for failures a retry can't fix

# in a route, before session.commit():
enqueue(session, "send_welcome", {"user_id": str(user.id)})
```

The job is saved in the same transaction as the route's own changes, so it exists only if they do.

- **Retries.** A failed job runs again after 20 seconds, then 40, 80 and so on, up to `max_attempts` (5 by default). `PermanentError` stops the retries at once.
- **Crashed workers.** A job left running for 15 minutes is picked up again, so handlers should be safe to run twice.
- **Many workers.** Workers claim jobs with `FOR UPDATE SKIP LOCKED`, so two never run the same job.
- **Payloads.** A finished job's payload is cleared, so tokens and email bodies don't stay in the database.

By default a worker thread runs inside the API (`JOBS_WORKER_IN_API=true`), which is enough to start. When jobs get heavy, run workers as their own service with `uv run python -m app.worker` (the same Docker image, with that command) and set `JOBS_WORKER_IN_API=false` on the API.

Failed jobs stay in the `jobs` table with their last error:

```sql
select kind, attempts, last_error, updated_at from jobs where status = 'failed' order by updated_at desc limit 20;
```

## Email

`send_email(session, to, subject, text)` in [`mail.py`](../backend/src/app/mail.py) queues the email as a job. Invites use it.

| Variable | Value |
| --- | --- |
| `EMAIL_BACKEND` | `console` (default) logs emails; `resend` sends them |
| `RESEND_API_KEY` | from [Resend](https://resend.com) |
| `EMAIL_FROM` | for example `Acme <hello@mail.acme.com>`, on a domain verified in Resend |

Resend rejecting an email (bad address, unverified domain) fails the job without retrying; network errors and Resend outages are retried.

## Operator admin

`/admin` lists the newest 500 workspaces. For each it shows:

- the number of members
- the plan and subscription status <!-- [only:billing] -->
- the number of documents and the AI spending this month <!-- [only:ai] -->
- the AI budget, which an operator can override for that workspace <!-- [only:ai] -->

Operators are the Clerk user ids in `ADMIN_USER_IDS`, comma separated (find yours in the Clerk dashboard, under Users). Everyone else gets a 404 from the admin routes, so they don't reveal that the page exists.
