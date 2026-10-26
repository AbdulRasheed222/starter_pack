"""Workspaces, their members and invites.

Roles: members use the workspace; admins also manage members and invites; owners also delete
the workspace and make other owners. A workspace always keeps at least one owner.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.config import get_settings
from app.db import get_session
from app.models import Invite, Membership, Role, User, Workspace
from app.tenancy import Admin, Member, Owner, owned

router = APIRouter(tags=["workspaces"])

SessionDep = Annotated[Session, Depends(get_session)]


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime) -> datetime:
    # SQLAlchemy returns aware datetimes from Postgres; this keeps comparisons safe elsewhere.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Workspaces


class WorkspaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class WorkspaceSummary(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class WorkspaceDetail(WorkspaceSummary):
    created_at: datetime
    members: int


class Me(BaseModel):
    id: uuid.UUID
    email: str | None
    workspaces: list[WorkspaceSummary]
    max_workspaces: int


def _detail(session: Session, workspace: Workspace, role: Role) -> WorkspaceDetail:
    members = session.scalar(
        select(func.count()).select_from(Membership).where(Membership.workspace_id == workspace.id)
    )
    return WorkspaceDetail(
        id=workspace.id,
        name=workspace.name,
        role=role,
        created_at=workspace.created_at,
        members=members or 0,
    )


@router.get("/me", response_model=Me)
def me(user: CurrentUser, session: SessionDep) -> Me:
    rows = session.execute(
        select(Workspace, Membership.role)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .where(Membership.user_id == user.id)
        .order_by(Workspace.created_at)
    ).all()
    return Me(
        id=user.id,
        email=user.email,
        workspaces=[WorkspaceSummary(id=w.id, name=w.name, role=role) for w, role in rows],
        max_workspaces=get_settings().max_workspaces_per_user,
    )


@router.post("/workspaces", response_model=WorkspaceDetail, status_code=201)
def create_workspace(body: WorkspaceIn, user: CurrentUser, session: SessionDep) -> WorkspaceDetail:
    owned_count = session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.user_id == user.id, Membership.role == Role.owner)
    )
    limit = get_settings().max_workspaces_per_user
    if (owned_count or 0) >= limit:
        raise HTTPException(status_code=409, detail=f"You can own at most {limit} workspaces.")
    workspace = Workspace(name=body.name.strip())
    session.add(workspace)
    session.flush()
    session.add(Membership(workspace_id=workspace.id, user_id=user.id, role=Role.owner))
    session.commit()
    return _detail(session, workspace, Role.owner)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(membership: Member, session: SessionDep) -> WorkspaceDetail:
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    return _detail(session, workspace, membership.role)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
def rename_workspace(body: WorkspaceIn, membership: Admin, session: SessionDep) -> WorkspaceDetail:
    workspace = session.get(Workspace, membership.workspace_id)
    assert workspace is not None
    workspace.name = body.name.strip()
    session.commit()
    return _detail(session, workspace, membership.role)


@router.delete("/workspaces/{workspace_id}", status_code=204)
def delete_workspace(membership: Owner, session: SessionDep) -> Response:
    """Deletes the workspace and, through the foreign keys, everything in it."""
    workspace = session.get(Workspace, membership.workspace_id)
    session.delete(workspace)
    session.commit()
    return Response(status_code=204)


# Members


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str | None
    role: Role
    joined_at: datetime


class RoleIn(BaseModel):
    role: Role


def _owners(session: Session, workspace_id: uuid.UUID) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.workspace_id == workspace_id, Membership.role == Role.owner)
        )
        or 0
    )


def _member_row(session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID) -> Membership:
    target = session.scalar(
        select(Membership).where(
            Membership.workspace_id == workspace_id, Membership.user_id == user_id
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Member not found.")
    return target


def _member_out(session: Session, membership: Membership) -> MemberOut:
    user = session.get(User, membership.user_id)
    return MemberOut(
        user_id=membership.user_id,
        email=user.email if user else None,
        role=membership.role,
        joined_at=membership.created_at,
    )


@router.get("/workspaces/{workspace_id}/members", response_model=list[MemberOut])
def list_members(membership: Member, session: SessionDep) -> list[MemberOut]:
    rows = session.execute(
        select(Membership, User.email)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == membership.workspace_id)
        .order_by(Membership.created_at)
    ).all()
    return [
        MemberOut(user_id=m.user_id, email=email, role=m.role, joined_at=m.created_at)
        for m, email in rows
    ]


@router.patch("/workspaces/{workspace_id}/members/{user_id}", response_model=MemberOut)
def change_role(
    user_id: uuid.UUID, body: RoleIn, membership: Admin, session: SessionDep
) -> MemberOut:
    target = _member_row(session, membership.workspace_id, user_id)
    if Role.owner in (target.role, body.role) and membership.role != Role.owner:
        raise HTTPException(status_code=403, detail="Only owners can change who is an owner.")
    if (
        target.role == Role.owner
        and body.role != Role.owner
        and _owners(session, membership.workspace_id) == 1
    ):
        raise HTTPException(status_code=409, detail="A workspace needs at least one owner.")
    target.role = body.role
    session.commit()
    return _member_out(session, target)


@router.delete("/workspaces/{workspace_id}/members/{user_id}", status_code=204)
def remove_member(
    user_id: uuid.UUID, membership: Member, user: CurrentUser, session: SessionDep
) -> Response:
    """Admins remove others; anyone can remove themselves, which is leaving."""
    target = _member_row(session, membership.workspace_id, user_id)
    leaving = user_id == user.id
    if not leaving:
        if not membership.role.at_least(Role.admin):
            raise HTTPException(status_code=403, detail="This needs the admin role.")
        if target.role == Role.owner and membership.role != Role.owner:
            raise HTTPException(status_code=403, detail="Only owners can remove an owner.")
    if target.role == Role.owner and _owners(session, membership.workspace_id) == 1:
        raise HTTPException(
            status_code=409,
            detail="A workspace needs at least one owner. Make someone else owner first.",
        )
    session.delete(target)
    session.commit()
    return Response(status_code=204)


# Invites


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = Role.member


class InviteOut(BaseModel):
    id: uuid.UUID
    email: str
    role: Role
    created_at: datetime
    expires_at: datetime


class CreatedInvite(InviteOut):
    # Shown once: only a hash of the token is stored. PR 3 emails it; until then the inviter
    # copies the link.
    link: str


class TokenIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class InvitePreview(BaseModel):
    workspace_name: str
    email: str
    role: Role
    expired: bool
    accepted: bool


def _invite_out(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=invite.role,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
    )


def _pending(session: Session, workspace_id: uuid.UUID):
    return select(Invite).where(
        Invite.workspace_id == workspace_id,
        Invite.accepted_at.is_(None),
        Invite.expires_at > _now(),
    )


@router.post("/workspaces/{workspace_id}/invites", response_model=CreatedInvite, status_code=201)
def create_invite(body: InviteIn, membership: Admin, user: CurrentUser, session: SessionDep):
    if body.role == Role.owner and membership.role != Role.owner:
        raise HTTPException(status_code=403, detail="Only owners can invite an owner.")
    email = body.email.strip().lower()
    already = session.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.workspace_id == membership.workspace_id, User.email == email)
    )
    if already is not None:
        raise HTTPException(status_code=409, detail="That person is already a member.")
    # A new invite to the same address replaces the old one, so only the newest link works.
    for old in session.scalars(
        _pending(session, membership.workspace_id).where(Invite.email == email)
    ):
        session.delete(old)

    settings = get_settings()
    token = secrets.token_urlsafe(32)
    invite = Invite(
        workspace_id=membership.workspace_id,
        email=email,
        role=body.role,
        token_hash=hash_token(token),
        invited_by=user.id,
        expires_at=_now() + timedelta(days=settings.invite_days),
    )
    session.add(invite)
    session.commit()
    link = f"{settings.site_url.rstrip('/')}/invite/{token}"
    return CreatedInvite(**_invite_out(invite).model_dump(), link=link)


@router.get("/workspaces/{workspace_id}/invites", response_model=list[InviteOut])
def list_invites(membership: Admin, session: SessionDep) -> list[InviteOut]:
    invites = session.scalars(
        _pending(session, membership.workspace_id).order_by(Invite.created_at.desc())
    )
    return [_invite_out(i) for i in invites]


@router.delete("/workspaces/{workspace_id}/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: uuid.UUID, membership: Admin, session: SessionDep) -> Response:
    session.delete(owned(session, Invite, invite_id, membership))
    session.commit()
    return Response(status_code=204)


def _by_token(session: Session, token: str) -> Invite:
    invite = session.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))
    if invite is None:
        raise HTTPException(status_code=404, detail="This invite link is not valid.")
    return invite


# The token travels in the body, not the URL, so it stays out of access logs.
@router.post("/invites/preview", response_model=InvitePreview)
def preview_invite(body: TokenIn, user: CurrentUser, session: SessionDep) -> InvitePreview:
    invite = _by_token(session, body.token)
    workspace = session.get(Workspace, invite.workspace_id)
    assert workspace is not None
    return InvitePreview(
        workspace_name=workspace.name,
        email=invite.email,
        role=invite.role,
        expired=_aware(invite.expires_at) <= _now(),
        accepted=invite.accepted_at is not None,
    )


@router.post("/invites/accept", response_model=WorkspaceSummary)
def accept_invite(body: TokenIn, user: CurrentUser, session: SessionDep) -> WorkspaceSummary:
    invite = _by_token(session, body.token)
    if invite.accepted_at is not None:
        raise HTTPException(status_code=410, detail="This invite has already been used.")
    if _aware(invite.expires_at) <= _now():
        raise HTTPException(status_code=410, detail="This invite has expired. Ask for a new one.")
    if get_settings().invite_requires_email_match:
        if user.email is None:
            raise HTTPException(
                status_code=400,
                detail="Your sign-in has no email address, so the invite can't be checked. "
                "The workspace admin needs to add the email claim (docs/clerk.md).",
            )
        if user.email != invite.email:
            raise HTTPException(
                status_code=403,
                detail=f"This invite is for {invite.email}. Sign in with that address.",
            )
    workspace = session.get(Workspace, invite.workspace_id)
    assert workspace is not None
    membership = session.scalar(
        select(Membership).where(
            Membership.workspace_id == invite.workspace_id, Membership.user_id == user.id
        )
    )
    if membership is None:
        membership = Membership(workspace_id=workspace.id, user_id=user.id, role=invite.role)
        session.add(membership)
    invite.accepted_at = _now()
    session.commit()
    return WorkspaceSummary(id=workspace.id, name=workspace.name, role=membership.role)
