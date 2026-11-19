"""Assessments: structured answers about one record, on a template from a pack. An impact
assessment of a use can be required by rule and is kept with its review; a due-diligence
questionnaire is kept with a vendor."""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core import conditions
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Assessment, UseCase, Vendor
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, USE_CASE, VENDOR, RecordType
from govwren.review import service as review

IMPACT = "impact_assessment"
DUE_DILIGENCE = "vendor_due_diligence"


@lru_cache(maxsize=1)
def pack() -> dict[str, Any]:
    text = (
        resources.files("govwren.resources.packs").joinpath("assessments.json").read_text("utf-8")
    )
    return json.loads(text)  # type: ignore[no-any-return]


def templates() -> dict[str, dict[str, Any]]:
    return {template["key"]: template for template in pack()["templates"]}


def template(key: str) -> dict[str, Any]:
    found = templates().get(key)
    if found is None:
        raise NotFound(f"There is no assessment called {key}.")
    return found


def questions(form: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [question for section in form["sections"] for question in section["questions"]]


def required(use_case: UseCase, answers: Mapping[str, Any]) -> bool:
    """Whether the rules require an impact assessment of this use."""
    when = template(IMPACT).get("required_when")
    return bool(when) and conditions.evaluate(
        when, {"tier": use_case.tier or 0, "answers": answers}
    )


def latest(session: Session, record_type: RecordType, record: Any, key: str) -> Assessment | None:
    return session.scalars(
        select(Assessment)
        .where(
            Assessment.subject_type == record_type.key,
            Assessment.subject_id == record.id,
            Assessment.template_key == key,
        )
        .order_by(Assessment.id.desc())
    ).first()


def _may_answer(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> bool:
    return principal.governs or access.can_edit(session, principal, record_type, record)


def _clean(
    form: Mapping[str, Any], answers: Mapping[str, Any], *, complete: bool
) -> dict[str, Any]:
    errors: dict[str, str] = {}
    out: dict[str, Any] = {}
    for question in questions(form):
        value = answers.get(question["key"])
        text = str(value).strip() if value is not None else ""
        if not text:
            if complete and question.get("required"):
                errors[question["key"]] = "Answer this question."
            continue
        if question["type"] == "choice" and text not in {o["key"] for o in question["options"]}:
            errors[question["key"]] = "Choose one of the answers."
            continue
        out[question["key"]] = text[:8000]
    if errors:
        raise Invalid("Some questions still need an answer.", errors)
    return out


def save(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    key: str,
    answers: Mapping[str, Any],
    *,
    submit: bool = False,
) -> Assessment:
    """Save answers as a draft, or submit them. A submitted assessment that has not been
    reviewed can still be corrected; a reviewed one starts a new assessment."""
    form = template(key)
    if form["subject"] != record_type.key:
        raise Invalid("Nothing was saved.", {"template": f"That is not for a {record_type.label}."})
    if not _may_answer(session, principal, record_type, record):
        raise PermissionDenied("Only those responsible for the record can answer this.")
    cleaned = _clean(form, answers, complete=submit)
    current = latest(session, record_type, record, key)
    now = utc_now()
    open_review = review.open_review(session, record) if record_type is USE_CASE else None
    with audit.operation(session, "assessment.submit" if submit else "assessment.save"):
        if current is None or current.status == "reviewed":
            current = Assessment(
                template_key=key,
                template_version=pack()["pack"].get("pack_version"),
                subject_type=record_type.key,
                subject_id=record.id,
                status="draft",
                answers={},
                updated_at=now,
            )
            session.add(current)
        current.answers, current.updated_at = cleaned, now
        if open_review is not None:
            current.review_id = open_review.id
        if submit:
            current.status = "submitted"
            current.submitted_by, current.submitted_at = principal.account_id, now
            if record_type is VENDOR and record.due_diligence_status == "not_started":
                record.due_diligence_status = "in_progress"
        session.flush()
    if submit:
        href = f"/assessments/{record.ref}/{key}"
        review.notify(
            session,
            review.holders(session, roles.GOVERNANCE),
            "assessment",
            f"{form['title']} to review: {record.name}",
            href,
            skip=principal.account_id,
        )
    return current


def mark_reviewed(
    session: Session, principal: Principal, assessment: Assessment, note: str
) -> Assessment:
    """Governance has read a submitted assessment. For a vendor, this completes due diligence."""
    if not principal.governs:
        raise PermissionDenied("Only governance can review an assessment.")
    if assessment.status != "submitted":
        raise Conflict("Only a submitted assessment can be reviewed.")
    if assessment.submitted_by == principal.account_id:
        raise PermissionDenied("You cannot review an assessment you submitted.")
    note = note.strip()
    if len(note) < 5:
        raise Invalid("The review was not recorded.", {"note": "Say what you concluded."})
    with audit.operation(session, "assessment.review"):
        assessment.status, assessment.review_note = "reviewed", note
        assessment.reviewed_by, assessment.reviewed_at = principal.account_id, utc_now()
        if assessment.subject_type == "vendor":
            vendor = session.get(Vendor, assessment.subject_id)
            if vendor is not None and vendor.due_diligence_status != "complete":
                vendor.due_diligence_status = "complete"
        session.flush()
    return assessment


def standing(
    session: Session, use_case: UseCase, answers: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Whether a use needs an impact assessment, and how far one has got."""
    found = latest(session, USE_CASE, use_case, IMPACT)
    needed = required(use_case, answers)
    if not needed and found is None:
        return None
    return {
        "required": needed,
        "status": found.status if found else "missing",
        "href": f"/assessments/{use_case.ref}/{IMPACT}",
    }


def view(
    session: Session, principal: Principal, record_type: RecordType, record: Any, key: str
) -> dict[str, Any]:
    form = template(key)
    if form["subject"] != record_type.key:
        raise NotFound(f"There is no {form['title'].lower()} for that record.")
    full = access.sight(session, principal, record_type, record) == access.FULL
    inside = False
    if record_type is USE_CASE:
        last = review.latest_review(session, record)
        inside = last is not None and review.sees_internal(session, principal, last)
    if not (full or inside or principal.reads_all):
        raise NotFound(f"There is no record {record.ref}.")
    found = latest(session, record_type, record, key)
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_({found.submitted_by, found.reviewed_by} - {None} or {0})
                if found
                else Account.id.in_({0})
            )
        ).all()  # type: ignore[arg-type]
    )
    may = _may_answer(session, principal, record_type, record)
    return {
        "template": {
            "key": key,
            "title": form["title"],
            "intro": form.get("intro"),
            "sections": form["sections"],
        },
        "record": {
            "type": record_type.key,
            "ref": record.ref,
            "name": record.name,
            "href": f"/{record_type.path}/{record.ref}",
        },
        "id": found.id if found else None,
        "status": found.status if found else "missing",
        "answers": found.answers if found else {},
        "submitted_by": names.get(found.submitted_by or 0) if found else None,
        "submitted_at": found.submitted_at if found else None,
        "reviewed_by": names.get(found.reviewed_by or 0) if found else None,
        "reviewed_at": found.reviewed_at if found else None,
        "review_note": found.review_note if found else None,
        "can": {
            "answer": may and (found is None or found.status != "reviewed" or principal.governs),
            "review": principal.governs
            and found is not None
            and found.status == "submitted"
            and found.submitted_by != principal.account_id,
        },
    }


def find(session: Session, assessment_id: int) -> Assessment:
    found = session.get(Assessment, assessment_id)
    if found is None or found.subject_type not in TYPES:
        raise NotFound("There is no such assessment.")
    return found
