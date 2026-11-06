"""Notes: a small example of a workspace's own data, to copy for your real features.

The pattern is the whole point: depend on `Member` (or `Admin`) for the workspace, filter lists
by `membership.workspace_id`, and load single rows with `owned`.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser
from app.db import get_session
from app.models import Note
from app.tenancy import Member, owned

router = APIRouter(prefix="/workspaces/{workspace_id}/notes", tags=["notes"])

SessionDep = Annotated[Session, Depends(get_session)]


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=20_000)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    body: str | None = Field(default=None, max_length=20_000)


class NoteOut(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


@router.get("", response_model=list[NoteOut])
def list_notes(membership: Member, session: SessionDep) -> list[Note]:
    return list(
        session.scalars(
            select(Note)
            .where(Note.workspace_id == membership.workspace_id)
            .order_by(Note.updated_at.desc())
        )
    )


@router.post("", response_model=NoteOut, status_code=201)
def create_note(body: NoteIn, membership: Member, user: CurrentUser, session: SessionDep) -> Note:
    note = Note(
        workspace_id=membership.workspace_id, title=body.title, body=body.body, created_by=user.id
    )
    session.add(note)
    session.commit()
    return note


@router.get("/{note_id}", response_model=NoteOut)
def get_note(note_id: uuid.UUID, membership: Member, session: SessionDep) -> Note:
    return owned(session, Note, note_id, membership)


@router.patch("/{note_id}", response_model=NoteOut)
def update_note(
    note_id: uuid.UUID, body: NotePatch, membership: Member, session: SessionDep
) -> Note:
    note = owned(session, Note, note_id, membership)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(note, field, value)
    session.commit()
    return note


@router.delete("/{note_id}", status_code=204)
def delete_note(note_id: uuid.UUID, membership: Member, session: SessionDep) -> Response:
    session.delete(owned(session, Note, note_id, membership))
    session.commit()
    return Response(status_code=204)
