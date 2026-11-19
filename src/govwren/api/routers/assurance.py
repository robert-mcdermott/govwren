"""Assurance: the risk library and the risk register."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.assurance import assessments, controls, library, policies, risks
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


class Standing(BaseModel):
    record: str | None = None
    status: str
    note: str = ""
    owner_id: int | None = None
    checked: bool = False


class NewPolicy(BaseModel):
    title: str
    summary: str | None = None
    body: str = ""
    owner_id: int | None = None
    review_on: str | None = None
    control_keys: list[str] | None = None


class PolicyChange(BaseModel):
    title: str | None = None
    summary: str | None = None
    owner_id: int | None = None
    review_on: str | None = None
    control_keys: list[str] | None = None


class Draft(BaseModel):
    body: str
    change_note: str = ""


class Asking(BaseModel):
    unit_id: int | None = None
    due_on: date | None = None


class Answers(BaseModel):
    answers: dict[str, Any]
    submit: bool = False


class Reviewed(BaseModel):
    note: str = ""


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


@router.get("/controls", summary="The control library, or the controls of one record")
def list_controls(request: Request, record: str | None = None) -> dict[str, Any]:
    """With no ``record``: every control, with how it stands for the program or how many of
    the records it applies to have it in place. With one: the controls that apply to that
    record, each with how it stands there."""
    principal = current(request)
    with reading(request) as session:
        if record is None:
            return envelope(controls.library(session, principal))
        record_type, found = find_any(session, record)
        if access.sight(session, principal, record_type, found) != access.FULL:
            raise NotFound(f"There is no record {record}.")
        return envelope(
            controls.for_record(session, principal, record_type, found),
            record={"ref": found.ref, "name": found.name, "type": record_type.key},  # type: ignore[attr-defined]
        )


@router.get("/controls/{key}", summary="One control, and where it stands")
def show_control(request: Request, key: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(controls.detail(session, principal, controls.find(session, key)))


@router.put("/controls/{key}/standing", summary="Say how a control stands")
def set_control(request: Request, key: str, body: Standing) -> dict[str, Any]:
    """For the program, or for one ``record`` the control applies to. ``status`` is
    ``not_started``, ``in_progress``, ``implemented``, or ``not_applicable``; the last needs
    a note saying why, and is governance's to give. ``checked`` records that a control in
    place was checked today, and sets the date of the next check."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        control = controls.find(session, key)
        about = None
        if body.record:
            about = find_any(session, body.record)
            if access.sight(session, principal, about[0], about[1]) is None:
                raise NotFound(f"There is no record {body.record}.")
        controls.set_standing(
            session, principal, control, body.model_dump(exclude={"record"}), record=about
        )
        if about is not None:
            return envelope(controls.for_record(session, principal, about[0], about[1]))
        return envelope(controls.detail(session, principal, control))


@router.get("/policies", summary="Policies")
def list_policies(request: Request) -> dict[str, Any]:
    """Policies in force, each with whether you have been asked to acknowledge it.
    Governance, auditors, and administrators also see drafts and retired policies."""
    principal = current(request)
    with reading(request) as session:
        return envelope(policies.listing(session, principal))


@router.post("/policies", status_code=201, summary="Start a policy")
def create_policy(request: Request, body: NewPolicy) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        policy = policies.create(session, principal, body.model_dump(exclude_unset=True))
        return envelope(policies.view(session, principal, policy))


@router.get("/policies/{ref}", summary="One policy: its text, versions, and controls")
def show_policy(request: Request, ref: str) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(policies.view(session, principal, policies.find(session, ref)))


def _policy(request: Request, ref: str, run: Any) -> dict[str, Any]:
    principal = current(request)
    with writing(request, principal.actor) as session:
        policy = policies.find(session, ref)
        run(session, principal, policy)
        return envelope(policies.view(session, principal, policy))


@router.patch("/policies/{ref}", summary="Change a policy's name, owner, review date, or controls")
def change_policy(request: Request, ref: str, body: PolicyChange) -> dict[str, Any]:
    return _policy(
        request,
        ref,
        lambda s, p, pol: policies.update(s, p, pol, body.model_dump(exclude_unset=True)),
    )


@router.put("/policies/{ref}/draft", summary="Write the next version of a policy")
def draft_policy(request: Request, ref: str, body: Draft) -> dict[str, Any]:
    """The version in force is not touched until the draft is published."""
    return _policy(
        request,
        ref,
        lambda s, p, pol: policies.save_draft(
            s, p, pol, body=body.body, change_note=body.change_note
        ),
    )


@router.post("/policies/{ref}/publish", summary="Put the draft in force")
def publish_policy(request: Request, ref: str) -> dict[str, Any]:
    return _policy(request, ref, policies.publish)


@router.post("/policies/{ref}/retire", summary="Retire a policy")
def retire_policy(request: Request, ref: str) -> dict[str, Any]:
    return _policy(request, ref, policies.retire)


@router.post("/policies/{ref}/ask", summary="Ask people to acknowledge a policy")
def ask_policy(request: Request, ref: str, body: Asking) -> dict[str, Any]:
    """Everyone in ``unit_id`` and the units beneath it, or everyone when it is left out,
    is asked to acknowledge the version in force by ``due_on``."""
    return _policy(
        request,
        ref,
        lambda s, p, pol: policies.ask(s, p, pol, unit_id=body.unit_id, due_on=body.due_on),
    )


@router.post("/policies/{ref}/acknowledge", summary="Say you have read a policy")
def acknowledge_policy(request: Request, ref: str) -> dict[str, Any]:
    return _policy(request, ref, policies.acknowledge)


@router.get("/assessments/{ref}/{template}", summary="An assessment of a record")
def show_assessment(request: Request, ref: str, template: str) -> dict[str, Any]:
    """The questions of the template and the latest answers. ``template`` is
    ``impact_assessment`` for a use case or ``vendor_due_diligence`` for a vendor."""
    principal = current(request)
    with reading(request) as session:
        record_type, record = find_any(session, ref)
        return envelope(assessments.view(session, principal, record_type, record, template))


@router.put("/assessments/{ref}/{template}", summary="Save or submit an assessment")
def save_assessment(request: Request, ref: str, template: str, body: Answers) -> dict[str, Any]:
    """Saved as a draft unless ``submit`` is set, which needs every required answer."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        record_type, record = find_any(session, ref)
        if access.sight(session, principal, record_type, record) is None:
            raise NotFound(f"There is no record {ref}.")
        assessments.save(
            session, principal, record_type, record, template, body.answers, submit=body.submit
        )
        return envelope(assessments.view(session, principal, record_type, record, template))


@router.post(
    "/assessments/{ref}/{template}/review", summary="Record that an assessment was reviewed"
)
def review_assessment(request: Request, ref: str, template: str, body: Reviewed) -> dict[str, Any]:
    """For a vendor, this completes its due diligence."""
    principal = current(request)
    with writing(request, principal.actor) as session:
        record_type, record = find_any(session, ref)
        found = assessments.latest(session, record_type, record, template)
        if found is None:
            raise NotFound("There is no assessment to review.")
        assessments.mark_reviewed(session, principal, found, body.note)
        return envelope(assessments.view(session, principal, record_type, record, template))
