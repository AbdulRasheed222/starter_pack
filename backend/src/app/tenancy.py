"""The one gate to a workspace's data.

Every route under /workspaces/{workspace_id} depends on `member_of` (or one of the role
shortcuts below). Callers who are not members get a 404, never a 403, so they cannot learn
which workspace ids exist. Rows inside a workspace are then always loaded with `owned`, which
checks the row's workspace_id against the path's, so an id from another workspace is a 404 too.
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_session
from app.models import Membership, Role, User

NOT_FOUND = "Workspace not found."


def _membership(workspace_id: uuid.UUID, user: User, session: Session) -> Membership:
    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return membership


def member_of(minimum: Role = Role.member):
    """A dependency that returns the caller's membership of the path's workspace, if their
    role is at least `minimum`. Members with too low a role get a 403: they can already see the
    workspace, so it hides nothing."""

    def dependency(
        workspace_id: uuid.UUID,
        user: Annotated[User, Depends(current_user)],
        session: Annotated[Session, Depends(get_session)],
    ) -> Membership:
        membership = _membership(workspace_id, user, session)
        if not membership.role.at_least(minimum):
            raise HTTPException(status_code=403, detail=f"This needs the {minimum} role.")
        return membership

    return dependency


Member = Annotated[Membership, Depends(member_of(Role.member))]
Admin = Annotated[Membership, Depends(member_of(Role.admin))]
Owner = Annotated[Membership, Depends(member_of(Role.owner))]


def owned[T](session: Session, model: type[T], row_id: uuid.UUID, membership: Membership) -> T:
    """A row of `model` by id, only if it belongs to the membership's workspace."""
    row = session.get(model, row_id)
    if row is None or row.workspace_id != membership.workspace_id:  # type: ignore[attr-defined]
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found.")
    return row
