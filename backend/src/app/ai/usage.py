"""The usage ledger: every model call is recorded with its cost, and a workspace that has spent
its monthly budget gets no more calls until the month turns (UTC).

The check runs before a call and the cost is recorded after it, so concurrent calls can
overshoot the budget by the cost of the calls in flight. For hard limits, reserve an estimate
before the call and settle it after.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.pricing import Usage, cost_usd
from app.billing import plan_budget
from app.config import Settings, get_settings
from app.db import get_session
from app.models import UsageEvent, Workspace
from app.tenancy import Member

router = APIRouter(prefix="/workspaces/{workspace_id}/usage", tags=["ai"])

DAYS = 30


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def budget_usd(workspace: Workspace, settings: Settings) -> float:
    if workspace.ai_monthly_budget_usd is not None:
        return workspace.ai_monthly_budget_usd
    return plan_budget(workspace, settings)


def spent_this_month(session: Session, workspace_id: uuid.UUID) -> float:
    total = session.scalar(
        select(func.coalesce(func.sum(UsageEvent.cost_usd), 0.0)).where(
            UsageEvent.workspace_id == workspace_id, UsageEvent.created_at >= month_start()
        )
    )
    return float(total or 0.0)


def check_budget(session: Session, workspace_id: uuid.UUID, settings: Settings) -> None:
    workspace = session.get(Workspace, workspace_id)
    assert workspace is not None
    if spent_this_month(session, workspace_id) >= budget_usd(workspace, settings):
        raise HTTPException(
            status_code=429,
            detail="This workspace has used its AI budget for this month.",
        )


def record(
    session: Session,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID | None,
    kind: str,
    model: str,
    usage: Usage,
    settings: Settings,
) -> UsageEvent:
    event = UsageEvent(
        workspace_id=workspace_id,
        user_id=user_id,
        kind=kind,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cost_usd=cost_usd(model, usage, settings),
    )
    session.add(event)
    session.commit()
    return event


class Day(BaseModel):
    date: date
    calls: int
    cost_usd: float


class UsageOut(BaseModel):
    month_start: date
    spent_usd: float
    budget_usd: float
    calls: int
    input_tokens: int
    output_tokens: int
    by_model: dict[str, float]
    days: list[Day]


@router.get("", response_model=UsageOut)
def usage(membership: Member, session: Annotated[Session, Depends(get_session)]) -> UsageOut:
    settings = get_settings()
    start = month_start()
    today = datetime.now(UTC).date()
    since = min(start, datetime.combine(today - timedelta(days=DAYS - 1), datetime.min.time(), UTC))
    events = session.scalars(
        select(UsageEvent).where(
            UsageEvent.workspace_id == membership.workspace_id, UsageEvent.created_at >= since
        )
    ).all()
    per_day: dict[date, Day] = {}
    by_model: dict[str, float] = {}
    this_month = [e for e in events if e.created_at >= start]
    for event in events:
        day = per_day.setdefault(
            event.created_at.date(), Day(date=event.created_at.date(), calls=0, cost_usd=0.0)
        )
        day.calls += 1
        day.cost_usd += event.cost_usd
    for event in this_month:
        by_model[event.model] = by_model.get(event.model, 0.0) + event.cost_usd
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    return UsageOut(
        month_start=start.date(),
        spent_usd=sum(e.cost_usd for e in this_month),
        budget_usd=budget_usd(workspace, settings),
        calls=len(this_month),
        input_tokens=sum(e.input_tokens for e in this_month),
        output_tokens=sum(e.output_tokens for e in this_month),
        by_model=by_model,
        days=[
            per_day.get(d, Day(date=d, calls=0, cost_usd=0.0))
            for d in (today - timedelta(days=n) for n in range(DAYS - 1, -1, -1))
        ],
    )
