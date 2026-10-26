"""Documents the AI answers from: upload, list, delete, and search.

An upload is stored and answered at once; a background job (jobs.py) then parses it, splits
it into passages and embeds them. The document's status goes from processing to ready, or to
failed with a reason the user can read.

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
from app.ai.parsing import ParseError, kind_for_filename, parse_file
from app.auth import CurrentUser
from app.config import Settings, get_settings
from app.db import get_session
from app.jobs import enqueue, handler
from app.models import Chunk, Document
from app.tenancy import Admin, Member, owned

router = APIRouter(prefix="/workspaces/{workspace_id}/documents", tags=["ai"])

SessionDep = Annotated[Session, Depends(get_session)]


class DocumentOut(BaseModel):
    id: uuid.UUID
    title: str
    filename: str
    kind: str
    status: str
    error: str | None
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
        status=document.status,
        error=document.error,
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
        kind = kind_for_filename(filename)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = Document(
        workspace_id=membership.workspace_id,
        title=filename.rsplit(".", 1)[0][:300],
        filename=filename,
        kind=kind,
        size_bytes=len(data),
        content=data,
        created_by=user.id,
    )
    session.add(document)
    session.flush()
    enqueue(session, "ingest_document", {"document_id": str(document.id)}, max_attempts=3)
    session.commit()
    session.refresh(document)
    chunks = session.scalar(select(func.count(Chunk.id)).where(Chunk.document_id == document.id))
    return _out(document, chunks or 0)


@handler("ingest_document")
def ingest_document(session: Session, payload: dict) -> None:
    """Parse, split and embed one upload. Safe to run twice: it replaces earlier passages."""
    settings = get_settings()
    document = session.get(Document, uuid.UUID(payload["document_id"]))
    if document is None or document.content is None:
        return  # deleted while queued
    try:
        parsed = parse_file(document.filename, document.content)
        passages = chunk_sections(
            parsed.sections, settings.chunk_words, settings.chunk_overlap_words
        )
        if not passages:
            raise ParseError("No text was found in this file.")
    except ParseError as exc:
        document.status, document.error = "failed", str(exc)[:500]
        return

    vectors = get_embedder(settings).embed_documents([p.embedding_text() for p in passages])
    session.query(Chunk).filter(Chunk.document_id == document.id).delete()
    session.add_all(
        Chunk(
            workspace_id=document.workspace_id,
            document_id=document.id,
            position=n,
            page=p.page,
            heading=(p.heading or None) and p.heading[:300],
            text=p.text,
            embedding=vector,
        )
        for n, (p, vector) in enumerate(zip(passages, vectors, strict=True))
    )
    document.title = parsed.title[:300]
    document.pages = parsed.pages
    document.status, document.error = "ready", None


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
