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
from govwren.oversight import (
    actions,
    campaigns,
    changes,
    exceptions,
    findings,
    incidents,
    retirement,
)

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


class NewException(BaseModel):
    record: str
    title: str
    requirement: str = ""
    justification: str = ""
    measures: str = ""
    ends_on: date | None = None


class ExceptionDecision(BaseModel):
    outcome: str
    note: str = ""
    ends_on: date | None = None


class Renewal(BaseModel):
    justification: str = ""
    ends_on: date | None = None


class Report(BaseModel):
    title: str
    description: str = ""
    occurred_on: date | None = None
    records: list[str] = Field(default_factory=list)
    org_unit_id: int | None = None


class Triage(BaseModel):
    category: str = ""
    severity: str = ""
    lead_id: int | None = None
    records: list[str] | None = None
    dismiss: str = ""


class OnRecord(BaseModel):
    record: str
    reason: str = ""


class Progress(BaseModel):
    status: str
    containment: str = ""
    cause: str = ""
    lessons: str = ""


class NewAction(BaseModel):
    title: str
    owner_id: int | None = None
    due_on: date | None = None
    record: str | None = None


class Closure(BaseModel):
    status: str = "done"
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


@router.get("/exceptions", summary="The exception register")
def list_exceptions(
    request: Request, status: str | None = None, record: str | None = None
) -> dict[str, Any]:
    """Every exception you may see: all of them for governance, auditors, and administrators;
    otherwise those you asked for and those on records you see in full. ``status=open``
    gives the ones waiting for a decision or in force. ``record`` limits it to one record."""
    principal = current(request)
    with reading(request) as session:
        about = find_any(session, record) if record else None
        return envelope(exceptions.register(session, principal, status=status, record=about))


@router.post("/exceptions", status_code=201, summary="Ask for an exception")
def request_exception(request: Request, body: NewException) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        record_type, record = find_any(session, body.record)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no record {body.record}.")
        made = exceptions.request(
            session, principal, record_type, record, title=body.title,
            requirement=body.requirement, justification=body.justification,
            measures=body.measures, ends_on=body.ends_on,
        )  # fmt: skip
        return envelope(exceptions.view(session, principal, made))


@router.get("/exceptions/{ref}", summary="One exception")
def show_exception(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(exceptions.view(session, principal, exceptions.find(session, ref)))


@router.post("/exceptions/{ref}/decision", summary="Approve or decline an exception")
def decide_exception(request: Request, ref: str, body: ExceptionDecision) -> dict[str, Any]:
    """``ends_on`` may bring the end date forward. An exception runs for a year at most."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        found = exceptions.decide(
            session, principal, exceptions.find(session, ref), outcome=body.outcome,
            note=body.note, ends_on=body.ends_on,
        )  # fmt: skip
        return envelope(exceptions.view(session, principal, found))


@router.post("/exceptions/{ref}/end", summary="Withdraw a request, or revoke an exception")
def end_exception(request: Request, ref: str, body: Retirement) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        found = exceptions.find(session, ref)
        if not exceptions.can_see(session, principal, found):
            raise NotFound(f"There is no exception {ref}.")
        exceptions.end(session, principal, found, body.reason)
        return envelope(exceptions.view(session, principal, found))


@router.post("/exceptions/{ref}/renewal", status_code=201, summary="Ask for more time")
def renew_exception(request: Request, ref: str, body: Renewal) -> dict[str, Any]:
    """A renewal is a new request, decided afresh, that points to the exception it renews."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        found = exceptions.find(session, ref)
        if not exceptions.can_see(session, principal, found):
            raise NotFound(f"There is no exception {ref}.")
        made = exceptions.renew(
            session, principal, found, justification=body.justification, ends_on=body.ends_on
        )
        return envelope(exceptions.view(session, principal, made))


@router.get("/incidents", summary="The incident register")
def list_incidents(request: Request, status: str | None = None) -> dict[str, Any]:
    """Every incident you may see: all of them for governance, auditors, and administrators;
    otherwise those you reported and those that involve a record you are responsible for."""
    principal = current(request)
    with reading(request) as session:
        return envelope(incidents.register(session, principal, status=status))


@router.post("/incidents", status_code=201, summary="Report an incident or a near miss")
def report_incident(request: Request, body: Report) -> dict[str, Any]:
    """Anyone signed in may report. Describe what happened; do not paste sensitive data."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        incident = incidents.report(
            session, principal, title=body.title, description=body.description,
            occurred_on=body.occurred_on, records=body.records, org_unit_id=body.org_unit_id,
        )  # fmt: skip
        return envelope(incidents.view(session, principal, incident))


@router.get("/incidents/{ref}", summary="One incident")
def show_incident(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(incidents.view(session, principal, incidents.find(session, ref)))


def _incident(request: Request, ref: str, run: Any) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        incident = incidents.find(session, ref)
        run(session, principal, incident)
        return envelope(incidents.view(session, principal, incident))


@router.post("/incidents/{ref}/triage", summary="Triage an incident, or dismiss it")
def triage_incident(request: Request, ref: str, body: Triage) -> dict[str, Any]:
    """Sets the category, the severity, who leads, and the records involved. May be sent
    again to correct them. ``dismiss`` closes a report that is not an incident, with why."""
    return _incident(request, ref, lambda s, p, i: incidents.triage(
        s, p, i, category=body.category, severity=body.severity, lead_id=body.lead_id,
        records=body.records, dismiss=body.dismiss,
    ))  # fmt: skip


@router.post("/incidents/{ref}/suspend", summary="Suspend the approval of a use it involves")
def suspend(request: Request, ref: str, body: OnRecord) -> dict[str, Any]:
    return _incident(
        request, ref, lambda s, p, i: incidents.suspend(s, p, i, body.record, body.reason)
    )


@router.post("/incidents/{ref}/lift", summary="Lift a suspension")
def lift(request: Request, ref: str, body: OnRecord) -> dict[str, Any]:
    return _incident(
        request, ref, lambda s, p, i: incidents.lift(s, p, i, body.record, body.reason)
    )


@router.post("/incidents/{ref}/review", summary="Open a review of a use it involves")
def incident_review(request: Request, ref: str, body: OnRecord) -> dict[str, Any]:
    """The review goes to triage with the reviews the rules require. Approving it lifts
    any suspension; it does not restart the approval period."""
    return _incident(
        request, ref, lambda s, p, i: incidents.open_review(s, p, i, body.record, body.reason)
    )


@router.post("/incidents/{ref}/progress", summary="Mark an incident contained, or close it")
def progress(request: Request, ref: str, body: Progress) -> dict[str, Any]:
    """Closing needs the cause and what was learned, and no approval still suspended."""
    return _incident(request, ref, lambda s, p, i: incidents.progress(
        s, p, i, status=body.status, containment=body.containment, cause=body.cause,
        lessons=body.lessons,
    ))  # fmt: skip


@router.post("/incidents/{ref}/actions", status_code=201, summary="Set an action")
def incident_action(request: Request, ref: str, body: NewAction) -> dict[str, Any]:
    return _incident(request, ref, lambda s, p, i: incidents.add_action(
        s, p, i, title=body.title, owner_id=body.owner_id, due_on=body.due_on, record=body.record,
    ))  # fmt: skip


@router.get("/actions", summary="Everything someone must do, in one list")
def list_actions(request: Request, scope: str = "mine", status: str = "open") -> dict[str, Any]:
    """Actions set after incidents, and the conditions of decisions that have a date or must
    be met before use. ``scope=all`` is for those who see everything; ``status=all``
    includes what is finished. A condition is closed through its own route."""
    principal = current(request)
    with reading(request) as session:
        return envelope(actions.listing(session, principal, scope=scope, status=status))


@router.post("/actions/{ref}/close", summary="Say an action is done, or cancel it")
def close_action(request: Request, ref: str, body: Closure) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        action = actions.close(
            session, principal, actions.find(session, ref), status=body.status, note=body.note
        )
        return envelope({"id": action.ref, "status": action.status})
