"""Intake: the form, a request's answers, and its tier."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.core.errors import NotFound
from govwren.intake import service
from govwren.inventory import access, records
from govwren.inventory.registry import USE_CASE, find

router = APIRouter(prefix="/api/v1", tags=["intake"])


class Answers(BaseModel):
    answers: dict[str, Any] = Field(description="Answers by question key")


class Override(BaseModel):
    tier: int
    reason: str = Field(max_length=4000)


def _use_case(session: Any, principal: Any, ref: str) -> Any:
    use_case = find(session, USE_CASE, ref)
    if access.sight(session, principal, USE_CASE, use_case) is None:
        raise NotFound(f"There is no use case {ref}.")
    return use_case


@router.get("/intake", summary="The intake form and scoring model in force")
def program(request: Request) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(service.program(session))


@router.post("/intake", status_code=201, summary="Begin a request")
def start(request: Request, body: Answers) -> dict[str, Any]:
    """Needs only what the request is for and which unit it belongs to. The rest can follow."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        use_case = service.start(session, principal, body.answers)
        return envelope(service.view(session, principal, use_case))


@router.get("/use-cases/{ref}/intake", summary="A request's form and answers")
def show(request: Request, ref: str) -> dict[str, Any]:
    """The draft being written, or what was submitted, with the version of the form it was
    answered on."""
    principal = current(request)
    with reading(request) as session:
        return envelope(service.view(session, principal, _use_case(session, principal, ref)))


@router.put("/use-cases/{ref}/intake", summary="Save a draft's answers")
def save(request: Request, ref: str, body: Answers) -> dict[str, Any]:
    """Saves whatever has been answered so far. Nothing needs to be complete."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        use_case = _use_case(session, principal, ref)
        errors = service.save(session, principal, use_case, body.answers)
        return envelope({"saved": True, "errors": errors, "name": use_case.name})


@router.post("/use-cases/{ref}/submit", summary="Submit a request")
def submit(request: Request, ref: str) -> dict[str, Any]:
    """Checks the answers are complete, fills the record from them, and works out the tier."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        use_case = _use_case(session, principal, ref)
        assessment = service.submit(session, principal, use_case)
        return envelope(
            {
                "record": records.detail(session, principal, USE_CASE, use_case),
                "assessment": service.assessment_view(session, assessment),
            }
        )


@router.get("/use-cases/{ref}/tier", summary="Why a use case has the tier it has")
def tier(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        use_case = _use_case(session, principal, ref)
        if access.sight(session, principal, USE_CASE, use_case) != access.FULL:
            raise NotFound(f"There is no use case {ref}.")
        return envelope(
            service.assessment_view(session, service.latest_assessment(session, use_case))
        )


@router.post("/use-cases/{ref}/tier", summary="Change a tier, with a reason")
def override(request: Request, ref: str, body: Override) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        use_case = _use_case(session, principal, ref)
        assessment = service.override_tier(session, principal, use_case, body.tier, body.reason)
        return envelope(service.assessment_view(session, assessment))
