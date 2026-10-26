"""Background jobs, email and the operator admin."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app import jobs, mail
from app.config import get_settings
from app.db import SessionLocal
from app.models import Job
from tests.support import as_user, create_workspace

calls: list[dict] = []


@jobs.handler("test_record")
def _record(session, payload):
    calls.append(payload)


@jobs.handler("test_flaky")
def _flaky(session, payload):
    calls.append(payload)
    raise RuntimeError("temporary")


@jobs.handler("test_permanent")
def _permanent(session, payload):
    raise jobs.PermanentError("never going to work")


@pytest.fixture
def queued(monkeypatch):
    """Jobs wait in the queue, as in production, instead of running inside enqueue()."""
    monkeypatch.setattr(get_settings(), "jobs_inline", False)
    calls.clear()


def add(kind: str, **payload) -> Job:
    with SessionLocal() as session:
        job = jobs.enqueue(session, kind, payload, max_attempts=2)
        session.commit()
        return job


def load(job: Job) -> Job:
    with SessionLocal() as session:
        return session.get(Job, job.id)


def test_jobs_run_once_and_drop_their_payload(queued):
    job = add("test_record", secret="token")
    assert jobs.work_once() is True
    assert jobs.work_once() is False
    assert calls == [{"secret": "token"}]
    done = load(job)
    assert (done.status, done.attempts, done.payload) == ("done", 1, {})


def test_failures_retry_later_then_give_up(queued):
    job = add("test_flaky")
    jobs.work_once()
    retry = load(job)
    assert retry.status == "queued" and "temporary" in retry.last_error
    assert retry.run_after > datetime.now(UTC)
    assert jobs.work_once() is False  # not due yet

    with SessionLocal() as session:
        session.get(Job, job.id).run_after = datetime.now(UTC)
        session.commit()
    jobs.work_once()
    assert (load(job).status, load(job).attempts) == ("failed", 2)


def test_permanent_errors_are_not_retried(queued):
    job = add("test_permanent")
    jobs.work_once()
    assert (load(job).status, load(job).last_error) == ("failed", "never going to work")


def test_jobs_of_dead_workers_are_picked_up_again(queued):
    job = add("test_record")
    with SessionLocal() as session:
        row = session.get(Job, job.id)
        row.status, row.locked_at = "running", datetime.now(UTC) - timedelta(hours=1)
        session.commit()
    assert jobs.work_once() is True
    assert load(job).status == "done"


def test_two_workers_never_claim_the_same_job(queued):
    add("test_record")
    with SessionLocal() as first, SessionLocal() as second:
        first.begin()
        locked = first.scalar(
            jobs.select(Job).where(Job.status == "queued").with_for_update(skip_locked=True)
        )
        assert locked is not None
        assert jobs.claim(second) is None  # the only job is locked by the first worker
        first.rollback()


def test_unknown_job_kinds_are_refused():
    with SessionLocal() as session, pytest.raises(ValueError):
        jobs.enqueue(session, "no_such_kind", {})


def test_invites_are_emailed(client, caplog):
    workspace_id = create_workspace(client)
    with caplog.at_level("INFO", logger="app.mail"):
        client.post(
            f"/workspaces/{workspace_id}/invites",
            json={"email": "dana@example.com"},
            headers=as_user(),
        )
    message = caplog.text
    assert "Email to dana@example.com" in message
    assert "/invite/" in message and "expires in 7 days" in message


def test_resend_request(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "email_backend", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test")
    seen = {}

    def post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers)
        return httpx.Response(200, json={"id": "e1"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(mail.httpx, "post", post)
    mail._send(None, {"to": "a@example.com", "subject": "Hi", "text": "One <b>\n\nTwo"})
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert seen["json"]["to"] == ["a@example.com"]
    assert seen["json"]["html"] == "<p>One &lt;b&gt;</p><p>Two</p>"

    monkeypatch.setattr(
        mail.httpx,
        "post",
        lambda url, **kw: httpx.Response(422, request=httpx.Request("POST", url)),
    )
    with pytest.raises(jobs.PermanentError):
        mail._send(None, {"to": "bad", "subject": "Hi", "text": "x"})


def test_admin_is_invisible_to_everyone_else(client):
    create_workspace(client)
    assert client.get("/admin/workspaces", headers=as_user()).status_code == 404
    assert client.get("/admin/workspaces").status_code == 401


def test_operators_see_every_workspace(client):
    create_workspace(client, name="Acme")
    create_workspace(client, "user_bob", name="Beta")
    operator = as_user("user_operator")
    assert client.get("/me", headers=operator).json()["is_operator"] is True
    assert client.get("/me", headers=as_user()).json()["is_operator"] is False
    rows = client.get("/admin/workspaces", headers=operator).json()
    assert sorted((r["name"], r["members"]) for r in rows) == [("Acme", 1), ("Beta", 1)]


# [module:ai]
def test_operators_see_workspaces_and_set_budgets(client):
    workspace_id = create_workspace(client, name="Acme")
    operator = as_user("user_operator")
    rows = client.get("/admin/workspaces", headers=operator).json()
    assert [(r["name"], r["budget_usd"], r["spent_usd"]) for r in rows] == [("Acme", 5, 0)]

    path = f"/admin/workspaces/{workspace_id}"
    row = client.patch(path, json={"ai_monthly_budget_usd": 12.5}, headers=operator).json()
    assert (row["budget_usd"], row["budget_override_usd"]) == (12.5, 12.5)
    usage = client.get(f"/workspaces/{workspace_id}/usage", headers=as_user()).json()
    assert usage["budget_usd"] == 12.5

    row = client.patch(path, json={"ai_monthly_budget_usd": None}, headers=operator).json()
    assert (row["budget_usd"], row["budget_override_usd"]) == (5, None)
    assert client.patch(path, json={"ai_monthly_budget_usd": -1}, headers=operator).status_code == (
        422
    )
    missing = "/admin/workspaces/00000000-0000-0000-0000-000000000000"
    assert client.patch(missing, json={}, headers=operator).status_code == 404
    # Workspace owners can't raise their own cap.
    assert client.patch(
        path, json={"ai_monthly_budget_usd": 999}, headers=as_user()
    ).status_code == (404)


# [/module:ai]
