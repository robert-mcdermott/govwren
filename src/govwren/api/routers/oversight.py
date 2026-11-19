"""Keeping watch: attestation campaigns."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.core.errors import NotFound
from govwren.inventory import access, records
from govwren.inventory.registry import USE_CASE, find, find_any
from govwren.oversight import campaigns, changes, findings, retirement

router = APIRouter(prefix="/api/v1", tags=["oversight"])


class NewCampaign(BaseModel):
    kind: str
    title: str
    due_on: date | None = None
    scope_unit_id: int | None = None
    record_types: list[str] = Field(default_factory=lambda: ["use_case"])
    note: str = ""


class Change(BaseModel):
    summary: str = ""


class Retirement(BaseModel):
    reason: str = ""


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


@router.post(
    "/use-cases/{ref}/change", status_code=201, summary="Declare a change to an approved use"
)
def declare_change(request: Request, ref: str, body: Change) -> dict[str, Any]:
    """Opens a change review that waits on the owner. The answers given last time become a
    draft to correct through the intake routes; submitting them lets the rules judge whether
    the change is material. Until then, withdrawing the review drops the change."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        use_case = find(session, USE_CASE, ref)
        if access.sight(session, principal, USE_CASE, use_case) is None:
            raise NotFound(f"There is no use case {ref}.")
        review = changes.declare(session, principal, use_case, body.summary)  # type: ignore[arg-type]
        return envelope({"ref": use_case.ref, "review": review.ref})


@router.post("/records/{ref}/retire", summary="Retire a record")
def retire(request: Request, ref: str, body: Retirement) -> dict[str, Any]:
    """The record stays in the inventory with its history, marked as no longer in use. The
    owners of the records that rely on it are told."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        record_type, record = find_any(session, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no record {ref}.")
        _, told = retirement.retire(session, principal, record_type, record, body.reason)
        return envelope(records.detail(session, principal, record_type, record), dependents=told)


@router.get("/records/{ref}/findings", summary="What to know before relying on a record")
def record_findings(request: Request, ref: str) -> dict[str, Any]:
    """The record's own findings, and those inherited from everything it relies on, each
    with the record it comes from. Records you may not see contribute nothing."""
    principal = current(request)
    with reading(request) as session:
        record_type, record = find_any(session, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no record {ref}.")
        found = findings.for_record(session, principal, record_type, record)
        found["dependents"] = len(retirement.dependents(session, record_type, record))
        return envelope(found)
