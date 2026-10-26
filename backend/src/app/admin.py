"""The operator's view across all workspaces: who is on which plan, what they spend, and a
per-workspace AI budget override.

Operators are listed by Clerk user id in ADMIN_USER_IDS. Everyone else gets a 404, so the
routes don't reveal they exist.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.usage import budget_usd, month_start
from app.auth import current_user
from app.config import get_settings
from app.db import get_session
from app.models import Document, Membership, UsageEvent, User, Workspace

SessionDep = Annotated[Session, Depends(get_session)]


def operator(user: Annotated[User, Depends(current_user)]) -> User:
    if user.clerk_user_id not in get_settings().admin_user_id_set:
        raise HTTPException(status_code=404, detail="Not found.")
    return user


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(operator)])


class AdminWorkspace(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    members: int
    documents: int
    plan: str
    subscription_status: str | None
    spent_usd: float
    budget_usd: float
    budget_override_usd: float | None


class BudgetIn(BaseModel):
    # None removes the override, so the plan's budget applies again.
    ai_monthly_budget_usd: float | None = Field(default=None, ge=0, le=100_000)


def _counts(session: Session, column, group) -> dict[uuid.UUID, float]:
    return dict(session.execute(select(group, column).group_by(group)).all())


def _row(workspace: Workspace, members, documents, spent) -> AdminWorkspace:
    settings = get_settings()
    return AdminWorkspace(
        id=workspace.id,
        name=workspace.name,
        created_at=workspace.created_at,
        members=int(members.get(workspace.id, 0)),
        documents=int(documents.get(workspace.id, 0)),
        plan=workspace.plan,
        subscription_status=workspace.subscription_status,
        spent_usd=float(spent.get(workspace.id, 0.0)),
        budget_usd=budget_usd(workspace, settings),
        budget_override_usd=workspace.ai_monthly_budget_usd,
    )


def _spent(session: Session) -> dict[uuid.UUID, float]:
    return dict(
        session.execute(
            select(UsageEvent.workspace_id, func.sum(UsageEvent.cost_usd))
            .where(UsageEvent.created_at >= month_start())
            .group_by(UsageEvent.workspace_id)
        ).all()
    )


@router.get("/workspaces", response_model=list[AdminWorkspace])
def list_workspaces(session: SessionDep) -> list[AdminWorkspace]:
    """Every workspace, highest AI spend this month first. Capped at 500 rows."""
    members = _counts(session, func.count(Membership.id), Membership.workspace_id)
    documents = _counts(session, func.count(Document.id), Document.workspace_id)
    spent = _spent(session)
    rows = [
        _row(w, members, documents, spent)
        for w in session.scalars(select(Workspace).order_by(Workspace.created_at.desc()).limit(500))
    ]
    return sorted(rows, key=lambda r: r.spent_usd, reverse=True)


@router.patch("/workspaces/{target_id}", response_model=AdminWorkspace)
def set_budget(target_id: uuid.UUID, body: BudgetIn, session: SessionDep) -> AdminWorkspace:
    workspace = session.get(Workspace, target_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    workspace.ai_monthly_budget_usd = body.ai_monthly_budget_usd
    session.commit()
    members = _counts(session, func.count(Membership.id), Membership.workspace_id)
    documents = _counts(session, func.count(Document.id), Document.workspace_id)
    return _row(workspace, members, documents, _spent(session))
