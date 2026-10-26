"""Documents the AI answers from: upload, list, delete, and search.

Uploads are parsed, split into passages and embedded inside the request. That is fine for
files of a few dozen pages; move it to a background job when your users upload books.

Search is an exact nearest-neighbour scan of one workspace's chunks, filtered on workspace_id
in SQL. It stays fast to roughly 100,000 chunks per workspace. Past that, add an HNSW index
and turn on pgvector's iterative scans, so the workspace filter can't starve the results.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.chunking import chunk_sections
from app.ai.embeddings import get_embedder
from app.ai.parsing import ParseError, parse_file
from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Chunk, Document
from app.tenancy import Admin, Member, owned

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["ai"])

SessionDep = Annotated[Session, Depends(get_session)]


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    kind: str
    pages: int
    size_bytes: int
    chunks: int
    created_at: datetime


def _out(document: Document, chunks: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        filename=document.filename,
        kind=document.kind,
        pages=document.pages,
        size_bytes=document.size_bytes,
        chunks=chunks,
        created_at=document.created_at,
    )


@router.get("", response_model=list[DocumentOut])
def list_documents(membership: Member, session: SessionDep) -> list[DocumentOut]:
    rows = session.execute(
        select(Document, func.count(Chunk.id))
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .where(Document.workspace_id == membership.workspace_id)
        .group_by(Document.id)
        .order_by(Document.created_at.desc())
    ).all()
    return [_out(document, chunks) for document, chunks in rows]


@router.post("", response_model=DocumentOut, status_code=201)
def upload_document(
    file: UploadFile, membership: Admin, user: CurrentUser, session: SessionDep
) -> DocumentOut:
    settings = get_settings()
    count = session.scalar(
        select(func.count(Document.id)).where(Document.workspace_id == membership.workspace_id)
    )
    if (count or 0) >= settings.max_documents_per_workspace:
        raise HTTPException(status_code=409, detail="This workspace has too many documents.")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail=f"Files can be up to {settings.max_upload_mb} MB."
        )
    filename = (file.filename or "upload.txt")[-300:]
    try:
        parsed = parse_file(filename, data)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    passages = chunk_sections(parsed.sections, settings.chunk_words, settings.chunk_overlap_words)
    if not passages:
        raise HTTPException(status_code=422, detail="No text was found in this file.")

    vectors = get_embedder(settings).embed_documents([p.embedding_text() for p in passages])
    document = Document(
        workspace_id=membership.workspace_id,
        title=parsed.title[:300],
        filename=filename,
        kind=parsed.kind,
        pages=parsed.pages,
        size_bytes=len(data),
        created_by=user.id,
    )
    session.add(document)
    session.flush()
    session.add_all(
        Chunk(
            workspace_id=membership.workspace_id,
            document_id=document.id,
            position=n,
            page=p.page,
            heading=(p.heading or None) and p.heading[:300],
            text=p.text,
            embedding=vector,
        )
        for n, (p, vector) in enumerate(zip(passages, vectors, strict=True))
    )
    session.commit()
    return _out(document, len(passages))


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, membership: Admin, session: SessionDep) -> Response:
    session.delete(owned(session, Document, document_id, membership))
    session.commit()
    return Response(status_code=204)


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    page: int | None
    heading: str | None
    text: str
    distance: float


def search(
    session: Session, workspace_id: uuid.UUID, query: str, limit: int, settings: Settings
) -> list[Hit]:
    """The workspace's passages closest in meaning to the query. Only ever one workspace."""
    vector = get_embedder(settings).embed_query(query)
    distance = Chunk.embedding.cosine_distance(vector)
    rows = session.execute(
        select(Chunk, Document.title, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.workspace_id == workspace_id, Document.workspace_id == workspace_id)
        .order_by(distance)
        .limit(limit)
    ).all()
    return [
        Hit(chunk.id, chunk.document_id, title, chunk.page, chunk.heading, chunk.text, d)
        for chunk, title, d in rows
    ]
