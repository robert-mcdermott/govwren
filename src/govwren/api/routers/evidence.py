"""Evidence: files, links, and notes that show a thing is so."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from govwren.access.policy import current
from govwren.api.common import clamp_limit, decode_cursor, encode_cursor, envelope, reading, writing
from govwren.core.errors import NotFound
from govwren.db.models import StoredFile
from govwren.evidence import files, service

router = APIRouter(prefix="/api/v1", tags=["evidence"])


class EvidenceBody(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    kind: str | None = None
    description: str | None = None
    url: str | None = None
    file_id: int | None = Field(default=None, description="From POST /evidence/files")
    file_name: str | None = Field(default=None, max_length=200)
    owner_id: int | None = None
    dated_on: str | None = None
    expires_on: str | None = None
    status: str | None = None
    supports: list[str] | None = Field(
        default=None,
        description="What it supports: record references such as UC-0012, or condition:7, "
        "review_task:3, agreement:5",
    )


@router.post("/evidence/files", status_code=201, summary="Send a file to attach as evidence")
async def send_file(
    request: Request, name: str = Query(max_length=300, description="The file's name")
) -> dict[str, Any]:
    """Send the file as the request body. PDF, images, office documents, plain text, CSV, and
    JSON, up to 25 MB. The answer carries a ``file_id`` to give to ``POST /evidence``. The
    same content sent twice is kept once."""
    data = await request.body()

    def keep() -> dict[str, Any]:
        principal = current(request)
        with writing(request, principal.actor) as session:
            stored = files.store(
                session, request.app.state.home.files, data, name, principal.account_id
            )
            return envelope(
                {
                    "file_id": stored.id,
                    "sha256": stored.sha256,
                    "size": stored.size,
                    "media_type": stored.media_type,
                    "name": files.clean_name(name),
                }
            )

    return await run_in_threadpool(keep)


@router.get("/evidence", summary="Find evidence")
def list_evidence(
    request: Request,
    q: str = Query("", max_length=200),
    kind: str | None = None,
    state: str | None = Query(None, description="current, expiring, expired, or withdrawn"),
    limit: int | None = Query(None, ge=1, le=200),
    cursor: str | None = None,
) -> dict[str, Any]:
    """Those who read everything see all evidence. Everyone else sees what they own or added;
    evidence on a record is shown on that record."""
    principal = current(request)
    size = clamp_limit(limit)
    offset = int((decode_cursor(cursor) or {}).get("offset", 0))
    with reading(request) as session:
        rows, total = service.search(
            session, principal, {"q": q, "kind": kind, "state": state}, limit=size, offset=offset
        )
        following = offset + len(rows)
        return envelope(
            [service.view(session, principal, row) for row in rows],
            total=total,
            offset=offset,
            next_cursor=encode_cursor({"offset": following}) if following < total else None,
            prev_cursor=encode_cursor({"offset": max(0, offset - size)}) if offset > 0 else None,
            limit=size,
        )


@router.post("/evidence", status_code=201, summary="Add evidence")
def add_evidence(request: Request, body: EvidenceBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        made = service.create(session, principal, body.model_dump(exclude_unset=True))
        return envelope(service.view(session, principal, made))


@router.get("/evidence/{ref}", summary="One piece of evidence")
def show_evidence(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(service.view(session, principal, service.find(session, principal, ref)))


@router.patch("/evidence/{ref}", summary="Change evidence, or withdraw it")
def change_evidence(request: Request, ref: str, body: EvidenceBody) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        found = service.find(session, principal, ref)
        service.update(session, principal, found, body.model_dump(exclude_unset=True))
        return envelope(service.view(session, principal, found))


@router.get("/evidence/{ref}/file", summary="Download the file", response_class=Response)
def download(request: Request, ref: str) -> Response:
    """Always a download, never shown in the page, with the type GovWren judged it to be."""
    principal = current(request)
    with reading(request) as session:
        found = service.find(session, principal, ref)
        stored = session.get(StoredFile, found.file_id) if found.file_id else None
        if stored is None:
            raise NotFound("This evidence has no file.")
        data = files.read(request.app.state.home.files, stored)
        name = files.clean_name(found.file_name or found.ref)
        media_type = stored.media_type
    plain = name.encode("ascii", "ignore").decode() or "file"
    return Response(
        data,
        media_type=media_type,
        headers={
            "content-disposition": f'attachment; filename="{plain}"; '
            f"filename*=UTF-8''{quote(name)}",
            "x-content-type-options": "nosniff",
            "content-security-policy": "default-src 'none'; sandbox",
            "cache-control": "private, no-store",
        },
    )
