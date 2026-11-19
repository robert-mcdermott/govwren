"""Keeping watch: attestation campaigns."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.oversight import campaigns

router = APIRouter(prefix="/api/v1", tags=["oversight"])


class NewCampaign(BaseModel):
    kind: str
    title: str
    due_on: date | None = None
    scope_unit_id: int | None = None
    record_types: list[str] = Field(default_factory=lambda: ["use_case"])
    note: str = ""


class Answer(BaseModel):
    id: int
    response: str
    note: str = ""


class Answers(BaseModel):
    items: list[Answer]


@router.get("/campaigns", summary="Attestation campaigns")
def list_campaigns(request: Request) -> dict[str, Any]:
    """Governance, auditors, and administrators see every campaign. Anyone else sees the
    campaigns that ask something of them."""
    principal = current(request)
    with reading(request) as session:
        return envelope(campaigns.listing(session, principal))


@router.post("/campaigns", status_code=201, summary="Start a campaign")
def open_campaign(request: Request, body: NewCampaign) -> dict[str, Any]:
    """An owner confirmation asks the owners of each record in scope whether it is still
    true. A unit completeness campaign asks each unit's steward whether its list is whole."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        campaign = campaigns.open_campaign(
            session, principal, kind=body.kind, title=body.title, due_on=body.due_on,
            scope_unit_id=body.scope_unit_id, record_types=body.record_types, note=body.note,
        )  # fmt: skip
        return envelope(campaigns.view(session, principal, campaign))


@router.get("/campaigns/{ref}", summary="One campaign: coverage, and what is yours to answer")
def show_campaign(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(campaigns.view(session, principal, campaigns.find(session, ref)))


@router.post("/campaigns/{ref}/answers", summary="Answer some of a campaign's questions")
def answer(request: Request, ref: str, body: Answers) -> dict[str, Any]:
    """For a record: ``confirmed``, ``changed``, or ``retired``; the last two need a note.
    For a unit: ``attested``. Several can be answered at once; all are recorded, or none."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        campaign = campaigns.find(session, ref)
        campaigns.answer(session, principal, campaign, [item.model_dump() for item in body.items])
        return envelope(campaigns.view(session, principal, campaign))


@router.post("/campaigns/{ref}/close", summary="Close a campaign")
def close(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        campaign = campaigns.close(session, principal, campaigns.find(session, ref))
        return envelope(campaigns.view(session, principal, campaign))
