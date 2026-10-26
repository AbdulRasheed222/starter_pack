"""The operator's view across all workspaces: size, plan, AI spending, and a per-workspace AI
budget override.

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

# [module:ai]
from app.ai.usage import budget_usd, month_start

# [/module:ai]
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
    # [module:billing]
    plan: str
    subscription_status: str | None
    # [/module:billing]
    # [module:ai]
    documents: int
    spent_usd: float
    budget_usd: float
    budget_override_usd: float | None
    # [/module:ai]


def _grouped(session: Session, query) -> dict:
    return {key: value for key, value in session.execute(query).all()}


def _rows(session: Session, workspaces: list[Workspace]) -> list[AdminWorkspace]:
    """The admin view of each workspace, with a few grouped queries rather than one each."""
    members = _grouped(
        session,
        select(Membership.workspace_id, func.count(Membership.id)).group_by(
            Membership.workspace_id
        ),
    )
    # [module:ai]
    settings = get_settings()
    documents = _grouped(
        session,
        select(Document.workspace_id, func.count(Document.id)).group_by(Document.workspace_id),
    )
    spent = _grouped(
        session,
        select(UsageEvent.workspace_id, func.sum(UsageEvent.cost_usd))
        .where(UsageEvent.created_at >= month_start())
        .group_by(UsageEvent.workspace_id),
    )
    # [/module:ai]
    rows = []
    for workspace in workspaces:
        fields: dict = {
            "id": workspace.id,
            "name": workspace.name,
            "created_at": workspace.created_at,
            "members": members.get(workspace.id, 0),
        }
        # [module:billing]
        fields["plan"] = workspace.plan
        fields["subscription_status"] = workspace.subscription_status
        # [/module:billing]
        # [module:ai]
        fields["documents"] = documents.get(workspace.id, 0)
        fields["spent_usd"] = float(spent.get(workspace.id) or 0.0)
        fields["budget_usd"] = budget_usd(workspace, settings)
        fields["budget_override_usd"] = workspace.ai_monthly_budget_usd
        # [/module:ai]
        rows.append(AdminWorkspace(**fields))
    return rows


@router.get("/workspaces", response_model=list[AdminWorkspace])
def list_workspaces(session: SessionDep) -> list[AdminWorkspace]:
    """The newest 500 workspaces."""
    workspaces = list(
        session.scalars(select(Workspace).order_by(Workspace.created_at.desc()).limit(500))
    )
    return _rows(session, workspaces)


# [module:ai]
class BudgetIn(BaseModel):
    # None removes the override, so the plan's budget applies again.
    ai_monthly_budget_usd: float | None = Field(default=None, ge=0, le=100_000)


@router.patch("/workspaces/{target_id}", response_model=AdminWorkspace)
def set_budget(target_id: uuid.UUID, body: BudgetIn, session: SessionDep) -> AdminWorkspace:
    workspace = session.get(Workspace, target_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    workspace.ai_monthly_budget_usd = body.ai_monthly_budget_usd
    session.commit()
    return _rows(session, [workspace])[0]


# [/module:ai]
