"""Incidents: anyone reports one; governance triages it, links the records involved, may
suspend an approval or open a review, sets actions, and closes it with what was learned."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Incident, IncidentRecord, OrgUnit, UseCase
from govwren.db.models.oversight import INCIDENT_CATEGORIES, SEVERITIES
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, USE_CASE, VENDOR, find_any
from govwren.oversight import actions
from govwren.review import service as review

LIVE = ("reported", "open", "contained")
CATEGORY_LABELS = {
    "wrong_output": "Wrong or harmful output",
    "data_exposure": "Data went where it should not",
    "misuse": "Used in a way that was not approved",
    "unapproved_use": "An unapproved tool or use",
    "outage": "A tool failed or was unavailable",
    "near_miss": "A near miss",
    "other": "Something else",
}


def find(session: Session, ref: str) -> Incident:
    incident = session.scalars(select(Incident).where(Incident.ref == ref.strip().upper())).first()
    if incident is None:
        raise NotFound(f"There is no incident {ref}.")
    return incident


def links_of(session: Session, incident: Incident) -> list[IncidentRecord]:
    return list(
        session.scalars(
            select(IncidentRecord)
            .where(IncidentRecord.incident_id == incident.id)
            .order_by(IncidentRecord.id)
        )
    )


def _record(session: Session, link: IncidentRecord) -> Any:
    return session.get(TYPES[link.subject_type].model, link.subject_id)


def can_see(session: Session, principal: Principal, incident: Incident) -> bool:
    """Governance, auditors, and administrators see every incident. So does whoever
    reported it, and whoever is responsible for a record it involves."""
    if principal.reads_all or incident.reported_by == principal.account_id:
        return True
    for link in links_of(session, incident):
        record = _record(session, link)
        if record is not None and access.can_edit(
            session, principal, TYPES[link.subject_type], record
        ):
            return True
    return False


def _set_records(session: Session, incident: Incident, refs: Iterable[str]) -> None:
    wanted: dict[tuple[str, int], Any] = {}
    for ref in dict.fromkeys(r.strip().upper() for r in refs if r and r.strip()):
        try:
            record_type, record = find_any(session, ref)
        except NotFound as exc:
            raise Invalid("It was not saved.", {"records": f"There is no record {ref}."}) from exc
        if record_type is VENDOR:
            raise Invalid("It was not saved.", {"records": "Link the tool, not its vendor."})
        wanted[(record_type.key, record.id)] = record
    existing = {(link.subject_type, link.subject_id): link for link in links_of(session, incident)}
    for key, link in existing.items():
        if key not in wanted:
            if link.suspended:
                raise Conflict("Lift the suspension before unlinking that record.")
            session.delete(link)
    for key in wanted:
        if key not in existing:
            session.add(
                IncidentRecord(
                    incident_id=incident.id, subject_type=key[0], subject_id=key[1], suspended=False
                )
            )
    session.flush()


def report(
    session: Session,
    principal: Principal,
    *,
    title: str,
    description: str,
    occurred_on: date | None = None,
    records: Iterable[str] = (),
    org_unit_id: int | None = None,
) -> Incident:
    """Report an incident or a near miss. Anyone signed in may; governance is told at once."""
    title, description, errors = title.strip(), description.strip(), {}
    if not 3 <= len(title) <= 200:
        errors["title"] = "Say in a few words what happened."
    if len(description) < 10:
        errors["description"] = "Describe what happened. Do not paste sensitive data here."
    if occurred_on is not None and occurred_on > today():
        errors["occurred_on"] = "That date has not come yet."
    if org_unit_id is not None and session.get(OrgUnit, org_unit_id) is None:
        errors["org_unit_id"] = "Choose a unit."
    if errors:
        raise Invalid("The incident was not reported.", errors)
    with audit.operation(session, "incident.report"):
        incident = Incident(
            ref=next_ref(session, "INC"),
            title=title,
            description=description,
            occurred_on=occurred_on,
            org_unit_id=org_unit_id,
            status="reported",
            reported_by=principal.account_id,
            reported_at=utc_now(),
        )
        session.add(incident)
        session.flush()
        _set_records(session, incident, records)
    review.notify(
        session,
        review.holders(session, roles.GOVERNANCE),
        "incident",
        f"Incident reported: {title}",
        f"/incidents/{incident.ref}",
        skip=principal.account_id,
    )
    return incident


def _governs(principal: Principal) -> None:
    if not principal.governs:
        raise PermissionDenied("Only governance can do that to an incident.")


def _live(incident: Incident) -> None:
    if incident.status not in LIVE:
        raise Conflict("This incident is closed.")


def triage(
    session: Session,
    principal: Principal,
    incident: Incident,
    *,
    category: str,
    severity: str,
    lead_id: int | None = None,
    records: Iterable[str] | None = None,
    dismiss: str = "",
) -> Incident:
    """Say what kind of incident it is and how serious, who leads on it, and which records
    it involves. Or dismiss it, with the reason, if it is not an incident."""
    _governs(principal)
    _live(incident)
    if dismiss.strip():
        if len(dismiss.strip()) < 10:
            raise Invalid("It was not dismissed.", {"dismiss": "Say why it is not an incident."})
        if any(link.suspended for link in links_of(session, incident)):
            raise Conflict("Lift the suspension before dismissing this incident.")
        with audit.operation(session, "incident.dismiss", reason=dismiss.strip()):
            incident.status, incident.lessons = "dismissed", dismiss.strip()
            incident.closed_by, incident.closed_at = principal.account_id, utc_now()
            session.flush()
        if incident.reported_by is not None:
            review.notify(
                session,
                [incident.reported_by],
                "incident",
                f"Your report was looked at and closed: {incident.title}",
                f"/incidents/{incident.ref}",
                skip=principal.account_id,
            )
        return incident
    errors = {}
    if category not in INCIDENT_CATEGORIES:
        errors["category"] = "Choose what kind of incident it is."
    if severity not in SEVERITIES:
        errors["severity"] = "Choose how serious it is."
    lead = session.get(Account, lead_id) if lead_id else None
    if lead_id and lead is None:
        errors["lead_id"] = "Choose who leads on it."
    if errors:
        raise Invalid("The triage was not saved.", errors)
    with audit.operation(session, "incident.triage"):
        first = incident.status == "reported"
        incident.category, incident.severity = category, severity
        incident.lead_id = lead.id if lead else (incident.lead_id or principal.account_id)
        if first:
            incident.status, incident.triaged_at = "open", utc_now()
        if records is not None:
            _set_records(session, incident, records)
        session.flush()
    if first:
        told: set[int] = set()
        for link in links_of(session, incident):
            record = _record(session, link)
            if link.subject_type == "use_case" and record is not None:
                told |= review.requester_ids(session, record)
        review.notify(
            session,
            told,
            "incident",
            f"An incident involves a record of yours: {incident.title}",
            f"/incidents/{incident.ref}",
            skip=principal.account_id,
        )
    return incident


def _link(session: Session, incident: Incident, ref: str) -> tuple[IncidentRecord, UseCase]:
    record_type, record = find_any(session, ref)
    if record_type is not USE_CASE:
        raise Invalid("That was not done.", {"record": "Only a use case has an approval."})
    link = session.scalars(
        select(IncidentRecord).where(
            IncidentRecord.incident_id == incident.id,
            IncidentRecord.subject_type == "use_case",
            IncidentRecord.subject_id == record.id,  # type: ignore[attr-defined]
        )
    ).first()
    if link is None:
        raise Invalid("That was not done.", {"record": "Link the record to the incident first."})
    return link, record  # type: ignore[return-value]


def suspend(
    session: Session, principal: Principal, incident: Incident, ref: str, reason: str
) -> UseCase:
    """Suspend the approval of a use the incident involves, until the suspension is lifted."""
    _governs(principal)
    _live(incident)
    link, use_case = _link(session, incident, ref)
    if use_case.status not in review.APPROVED:
        raise Conflict("Only an approval in force can be suspended.")
    reason = reason.strip()
    if len(reason) < 10:
        raise Invalid("It was not suspended.", {"reason": "Say why the approval is suspended."})
    with audit.operation(session, "use_case.suspend", reason=reason, incident=incident.ref):
        link.suspended, link.prior_status = True, use_case.status
        use_case.status = "suspended"
        use_case.version += 1
        session.flush()
    review.notify(
        session,
        review.requester_ids(session, use_case) | review.stewards_of(session, use_case.org_unit_id),
        "suspended",
        f"Approval suspended: {use_case.name}",
        f"/use-cases/{use_case.ref}",
        skip=principal.account_id,
    )
    return use_case


def lift(
    session: Session, principal: Principal, incident: Incident, ref: str, reason: str
) -> UseCase:
    """Lift a suspension. The use goes back to the standing it had."""
    _governs(principal)
    link, use_case = _link(session, incident, ref)
    if not link.suspended or use_case.status != "suspended":
        raise Conflict("That approval is not suspended by this incident.")
    reason = reason.strip()
    if len(reason) < 10:
        raise Invalid("It was not lifted.", {"reason": "Say why the suspension is lifted."})
    with audit.operation(session, "use_case.reinstate", reason=reason, incident=incident.ref):
        ended = use_case.approved_until is not None and use_case.approved_until < today()
        use_case.status = "lapsed" if ended else (link.prior_status or "approved")
        use_case.version += 1
        link.suspended = False
        session.flush()
    review.notify(
        session,
        review.requester_ids(session, use_case),
        "suspended",
        f"Suspension lifted: {use_case.name}",
        f"/use-cases/{use_case.ref}",
        skip=principal.account_id,
    )
    return use_case


def open_review(
    session: Session, principal: Principal, incident: Incident, ref: str, reason: str
) -> Any:
    """Open a review of a use the incident involves. Approving it lifts any suspension."""
    _governs(principal)
    _live(incident)
    _, use_case = _link(session, incident, ref)
    reason = reason.strip()
    if len(reason) < 10:
        raise Invalid(
            "The review was not opened.", {"reason": "Say what the review should look at."}
        )
    return review.open_incident_review(session, principal, use_case, incident.ref, reason)


def progress(
    session: Session,
    principal: Principal,
    incident: Incident,
    *,
    status: str,
    containment: str = "",
    cause: str = "",
    lessons: str = "",
) -> Incident:
    """Record that the incident is contained, or close it with its cause and what was learned."""
    _governs(principal)
    _live(incident)
    if incident.status == "reported":
        raise Conflict("Triage this incident first.")
    containment, cause, lessons = containment.strip(), cause.strip(), lessons.strip()
    errors = {}
    if status not in ("contained", "closed"):
        errors["status"] = "Mark it contained, or close it."
    if len(containment or incident.containment or "") < 10:
        errors["containment"] = "Say what was done to stop it or limit it."
    if status == "closed":
        if len(cause) < 10:
            errors["cause"] = "Say what caused it."
        if len(lessons) < 10:
            errors["lessons"] = "Say what will be done differently."
        if any(link.suspended for link in links_of(session, incident)):
            errors["status"] = (
                "An approval is still suspended. Lift it, or decide its review, first."
            )
    if errors:
        raise Invalid("The incident was not updated.", errors)
    with audit.operation(session, f"incident.{'close' if status == 'closed' else 'contain'}"):
        incident.status = status
        incident.containment = containment or incident.containment
        if status == "closed":
            incident.cause, incident.lessons = cause, lessons
            incident.closed_by, incident.closed_at = principal.account_id, utc_now()
        session.flush()
    if status == "closed" and incident.reported_by is not None:
        review.notify(
            session,
            [incident.reported_by],
            "incident",
            f"The incident you reported is closed: {incident.title}",
            f"/incidents/{incident.ref}",
            skip=principal.account_id,
        )
    return incident


def add_action(
    session: Session,
    principal: Principal,
    incident: Incident,
    *,
    title: str,
    owner_id: int | None,
    due_on: date | None,
    record: str | None = None,
) -> Any:
    _governs(principal)
    _live(incident)
    subject = None
    if record:
        record_type, found = find_any(session, record)
        subject = (record_type.key, found.id)  # type: ignore[attr-defined]
    return actions.add(
        session,
        principal,
        title=title,
        owner_id=owner_id,
        due_on=due_on,
        source=("incident", incident.id),
        subject=subject,
    )


# --- Looking at incidents -----------------------------------------------------------------


def live_on(session: Session, subject_type: str, subject_id: int) -> list[Incident]:
    """The incidents still open against a record."""
    return list(
        session.scalars(
            select(Incident)
            .join(IncidentRecord, IncidentRecord.incident_id == Incident.id)
            .where(
                IncidentRecord.subject_type == subject_type,
                IncidentRecord.subject_id == subject_id,
                Incident.status.in_(("open", "contained")),
            )
            .order_by(Incident.id)
        )
    )


def _summary(incident: Incident, names: dict[int, str]) -> dict[str, Any]:
    return {
        "ref": incident.ref,
        "title": incident.title,
        "status": incident.status,
        "category": incident.category,
        "category_label": CATEGORY_LABELS.get(incident.category or ""),
        "severity": incident.severity,
        "occurred_on": incident.occurred_on,
        "reported_by": names.get(incident.reported_by or 0),
        "reported_at": incident.reported_at,
        "lead": names.get(incident.lead_id or 0),
        "closed_at": incident.closed_at,
    }


def _names(session: Session, incidents: list[Incident]) -> dict[int, str]:
    ids = {i.reported_by for i in incidents} | {i.lead_id for i in incidents}
    ids |= {i.closed_by for i in incidents}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(ids - {None} or {0}))
        ).all()  # type: ignore[arg-type]
    )


def register(
    session: Session, principal: Principal, *, status: str | None = None
) -> list[dict[str, Any]]:
    statement = select(Incident).order_by(Incident.id.desc())
    if status == "open":
        statement = statement.where(Incident.status.in_(LIVE))
    rows = [i for i in session.scalars(statement) if can_see(session, principal, i)]
    names = _names(session, rows)
    order = {"reported": 0, "open": 1, "contained": 2}
    severity = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
    rows.sort(key=lambda i: (order.get(i.status, 3), severity.get(i.severity or "", 4), -i.id))
    return [_summary(incident, names) for incident in rows]


def view(session: Session, principal: Principal, incident: Incident) -> dict[str, Any]:
    if not can_see(session, principal, incident):
        raise NotFound(f"There is no incident {incident.ref}.")
    names = _names(session, [incident])
    involved = []
    for link in links_of(session, incident):
        record_type, record = TYPES[link.subject_type], _record(session, link)
        if record is None:
            continue
        seen = access.sight(session, principal, record_type, record) is not None
        open_ = review.open_review(session, record) if record_type is USE_CASE else None
        involved.append(
            {
                "type": record_type.key,
                "ref": record.ref,
                "name": record.name if seen else "A record you do not have access to",
                "href": f"/{record_type.path}/{record.ref}" if seen else None,
                "status": record.status,
                "suspended": link.suspended,
                "review": open_.ref if open_ is not None and principal.reviews else None,
                "can_suspend": principal.governs
                and incident.status in LIVE
                and record_type is USE_CASE
                and record.status in review.APPROVED,
                "can_lift": principal.governs and link.suspended and record.status == "suspended",
                "can_review": principal.governs
                and incident.status in LIVE
                and record_type is USE_CASE
                and open_ is None
                and record.status in (*review.APPROVED, "suspended"),
            }
        )
    live = incident.status in LIVE
    return {
        **_summary(incident, names),
        "description": incident.description,
        "org_unit_id": incident.org_unit_id,
        "containment": incident.containment,
        "cause": incident.cause,
        "lessons": incident.lessons,
        "closed_by": names.get(incident.closed_by or 0),
        "records": involved,
        "actions": actions.for_source(session, principal, ("incident", incident.id)),
        "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
        "can": {
            "triage": principal.governs and live,
            "progress": principal.governs and incident.status in ("open", "contained"),
            "act": principal.governs and live,
        },
    }
