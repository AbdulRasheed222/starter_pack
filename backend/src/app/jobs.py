"""Background jobs in Postgres: no Redis, no extra service.

Enqueue with `enqueue(session, "kind", {...})` in the same transaction as the change that needs
it, so a job exists exactly when its data does. Workers claim jobs with
`SELECT ... FOR UPDATE SKIP LOCKED`, so any number of them can run side by side.

A failed job is retried with a growing delay, up to `max_attempts`; a job whose worker died is
picked up again once its lock goes stale. Handlers must therefore be safe to run twice.

Where workers run:
- By default the API process runs one in a background thread (`JOBS_WORKER_IN_API=true`), so a
  single container is enough.
- At scale, set that to false and run `uv run python -m app.worker` as its own service.
- Tests set `JOBS_INLINE=true`: jobs run inside `enqueue`, so results are there at once.
"""

import logging
import threading
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal
from app.models import Job

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict], None]
HANDLERS: dict[str, Handler] = {}

# A running job whose lock is older than this is assumed to belong to a dead worker.
STALE_AFTER = timedelta(minutes=15)


class PermanentError(Exception):
    """Raise from a handler for failures a retry can't fix, such as an unreadable file."""


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(function: Handler) -> Handler:
        HANDLERS[kind] = function
        return function

    return register


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(session: Session, kind: str, payload: dict, max_attempts: int = 5) -> Job:
    """Add a job to the session. It is queued when the session commits."""
    if kind not in HANDLERS:
        raise ValueError(f"No handler for job kind {kind!r}")
    job = Job(kind=kind, payload=payload, max_attempts=max_attempts)
    session.add(job)
    if get_settings().jobs_inline:
        session.flush()
        session.commit()
        run(job.id)
        session.refresh(job)
    return job


def claim(session: Session) -> Job | None:
    now = _now()
    job = session.scalar(
        select(Job)
        .where(
            or_(
                (Job.status == "queued") & (Job.run_after <= now),
                (Job.status == "running") & (Job.locked_at < now - STALE_AFTER),
            )
        )
        .order_by(Job.run_after)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = "running"
    job.locked_at = now
    job.attempts += 1
    session.commit()
    return job


def run(job_id: uuid.UUID) -> None:
    """Run one claimed or inline job and record how it went."""
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        if job.status == "queued":  # inline: nothing claimed it
            job.status, job.locked_at, job.attempts = "running", _now(), job.attempts + 1
            session.commit()
        kind, payload = job.kind, dict(job.payload)
    error: str | None = None
    permanent = False
    try:
        with SessionLocal() as session:
            HANDLERS[kind](session, payload)
            session.commit()
    except PermanentError as exc:
        error, permanent = str(exc), True
    except Exception:
        error = traceback.format_exc(limit=5)
        logger.exception("Job %s (%s) failed", job_id, kind)
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.locked_at = None
        if error is None:
            # Payloads can hold secrets, such as invite links in emails: keep none once done.
            job.status, job.finished_at, job.payload = "done", _now(), {}
        elif permanent or job.attempts >= job.max_attempts:
            job.status, job.finished_at, job.last_error = "failed", _now(), error
        else:
            job.status, job.last_error = "queued", error
            job.run_after = _now() + timedelta(seconds=10 * 2**job.attempts)
        session.commit()


def work_once() -> bool:
    """Claim and run one job. False when there was nothing to do."""
    with SessionLocal() as session:
        job = claim(session)
        job_id = job.id if job else None
    if job_id is None:
        return False
    run(job_id)
    return True


def work_forever(stop: threading.Event, idle_seconds: float = 2.0) -> None:
    import app.api  # noqa: F401  importing the app registers every handler

    while not stop.is_set():
        try:
            if not work_once():
                stop.wait(idle_seconds)
        except Exception:
            logger.exception("Worker loop error")
            stop.wait(idle_seconds)
