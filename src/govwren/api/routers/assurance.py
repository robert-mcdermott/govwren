"""Assurance: the risk library and the risk register."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.assurance import library, risks
from govwren.core.errors import NotFound, PermissionDenied
from govwren.inventory import access
from govwren.inventory.registry import USE_CASE, find_any
from govwren.review import service as review

router = APIRouter(prefix="/api/v1", tags=["assurance"])


class NewRisk(BaseModel):
    record: str | None = None
    review: str | None = None
    library_key: str | None = None
    title: str | None = None
    description: str | None = None
    category: str | None = None
    inherent_likelihood: int | None = None
    inherent_impact: int | None = None
    owner_id: int | None = None
    review_on: str | None = None


class RiskChange(BaseModel):
    title: str | None = None
    description: str | None = None
    category: str | None = None
    inherent_likelihood: int | None = None
    inherent_impact: int | None = None
    treatment: str | None = None
    treatment_note: str | None = None
    residual_likelihood: int | None = None
    residual_impact: int | None = None
    owner_id: int | None = None
    review_on: str | None = None


class Closing(BaseModel):
    reason: str = ""


@router.get("/risk-library", summary="Reusable risk statements to draw from")
def risk_library(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(library.listing(session))


@router.get("/risks", summary="The risk register")
def list_risks(
    request: Request, status: str = "live", record: str | None = None, mine: bool = False
) -> dict[str, Any]:
    """Every risk you may see, highest first, with a count for each cell of the grid of
    likelihood against impact. ``status`` is ``live``, ``all``, or one standing. ``record``
    limits it to one record; ``mine`` to the risks you own."""
    principal = current(request)
    with reading(request) as session:
        about = find_any(session, record) if record else None
        found = risks.register(session, principal, status=status, record=about, mine=mine)
        return envelope(found["risks"], grid=found["grid"], by_level=found["by_level"])


@router.post("/risks", status_code=201, summary="Record a risk")
def add_risk(request: Request, body: NewRisk) -> dict[str, Any]:
    """On a record, on the use a review is about, or on the organization when neither is
    given. ``library_key`` draws the wording from the risk library. A reviewer may record a
    risk from a review they have a part in; it goes to the use's accountable owner."""
    principal = current(request)
    values = body.model_dump(exclude_unset=True, exclude={"record", "review"})
    with writing(request, principal.actor) as session:
        about, source, reviewing = None, None, False
        if body.review:
            found = review.find(session, principal, body.review)
            if not (principal.reviews and review.sees_internal(session, principal, found)):
                raise PermissionDenied("Only a reviewer of that request can record a risk from it.")
            use_case = review.subject_of(session, found)
            about, source, reviewing = (USE_CASE, use_case), f"Review {found.ref}", True
            values.setdefault("owner_id", review._accountable(session, use_case))
        elif body.record:
            about = find_any(session, body.record)
            if access.sight(session, principal, about[0], about[1]) is None:
                raise NotFound(f"There is no record {body.record}.")
        risk = risks.add(
            session, principal, values, record=about, source=source, as_reviewer=reviewing
        )
        return envelope(risks.view(session, principal, risk))


@router.get("/risks/{ref}", summary="One risk")
def show_risk(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(risks.view(session, principal, risks.find(session, ref)))


@router.patch("/risks/{ref}", summary="Rescore a risk, treat it, or pass it on")
def change_risk(request: Request, ref: str, body: RiskChange) -> dict[str, Any]:
    """Send only what changes. Scores run from 1 to 5. Giving a treatment and both residual
    scores marks the risk as treated; the treatment ``accept`` is governance's to give."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        risk = risks.find(session, ref)
        if not risks.can_see(session, principal, risk):
            raise NotFound(f"There is no risk {ref}.")
        risks.update(session, principal, risk, body.model_dump(exclude_unset=True))
        return envelope(risks.view(session, principal, risk))


@router.post("/risks/{ref}/close", summary="Close a risk that no longer applies")
def close_risk(request: Request, ref: str, body: Closing) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        risk = risks.close(session, principal, risks.find(session, ref), body.reason)
        return envelope(risks.view(session, principal, risk))
