"""Exceptions: approved, time-limited departures from a requirement.

Someone responsible for a record asks; they say what requirement cannot be met, why, and
what is done instead. Governance approves or declines. An approved exception always has an
end date, shows on the record and on everything that relies on it, and expires by itself.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, ExceptionRecord, Reminder
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, VENDOR, RecordType
from govwren.review import service as review

MAX_DAYS = 366  # an exception that is still needed after a year is renewed, in the open
SOON_DAYS = 21
OPEN = ("requested", "approved")


# The rules of GovWren's own that an exception can set aside. An exception that names none is
# a departure from a requirement of the organization's, recorded but enforced by people.
RULES = {"health_agreement": "Health information needs a covering agreement"}


def find(session: Session, ref: str) -> ExceptionRecord:
    found = session.scalars(
        select(ExceptionRecord).where(ExceptionRecord.ref == ref.strip().upper())
    ).first()
    if found is None:
        raise NotFound(f"There is no exception {ref}.")
    return found


def _record(session: Session, exception: ExceptionRecord) -> tuple[RecordType, Any]:
    record_type = TYPES[exception.subject_type]
    return record_type, session.get(record_type.model, exception.subject_id)


def can_see(session: Session, principal: Principal, exception: ExceptionRecord) -> bool:
    if principal.reads_all or exception.requested_by == principal.account_id:
        return True
    record_type, record = _record(session, exception)
    return record is not None and (
        access.sight(session, principal, record_type, record) == access.FULL
    )


def _check(values: dict[str, str], ends_on: date | None, start: date) -> dict[str, str]:
    errors = {}
    if not 3 <= len(values["title"]) <= 200:
        errors["title"] = "Give it a short name."
    for field, words in (
        ("requirement", "Say which requirement cannot be met."),
        ("justification", "Say why it cannot be met for now."),
        ("measures", "Say what is done instead to keep the risk down."),
    ):
        if len(values[field]) < 10:
            errors[field] = words
    if ends_on is None or ends_on <= start:
        errors["ends_on"] = "Choose the date it ends. An exception always ends."
    elif ends_on > start + timedelta(days=MAX_DAYS):
        errors["ends_on"] = "An exception runs for a year at most. It can be renewed."
    return errors


def request(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    *,
    title: str,
    requirement: str,
    justification: str,
    measures: str,
    ends_on: date | None,
    renews: ExceptionRecord | None = None,
    rule: str | None = None,
) -> ExceptionRecord:
    """Ask for an exception on a record. Its owners, its unit's stewards, and governance may.
    ``rule`` names a rule of GovWren's own that the exception departs from, if it is one."""
    if record_type is VENDOR or not access.can_edit(session, principal, record_type, record):
        raise PermissionDenied("Only those responsible for a record can ask for an exception.")
    values = {
        "title": title.strip(), "requirement": requirement.strip(),
        "justification": justification.strip(), "measures": measures.strip(),
    }  # fmt: skip
    errors = _check(values, ends_on, today())
    rule = rule or None
    if rule is not None and rule not in RULES:
        errors["rule"] = f"Choose one of: {', '.join(RULES)}, or none."
    if errors:
        raise Invalid("The exception was not requested.", errors)
    assert ends_on is not None
    with audit.operation(session, "exception.request"):
        exception = ExceptionRecord(
            ref=next_ref(session, "EXC"),
            subject_type=record_type.key,
            subject_id=record.id,
            org_unit_id=getattr(record, "org_unit_id", None),
            status="requested",
            ends_on=ends_on,
            renews_id=renews.id if renews else None,
            requested_by=principal.account_id,
            requested_at=utc_now(),
            rule=rule,
            **values,
        )
        session.add(exception)
        session.flush()
    review.notify(
        session, review.holders(session, roles.GOVERNANCE), "exception",
        f"Exception to decide: {exception.title}", f"/exceptions/{exception.ref}",
        skip=principal.account_id,
    )  # fmt: skip
    return exception


def renew(
    session: Session, principal: Principal, exception: ExceptionRecord, *,
    justification: str, ends_on: date | None,
) -> ExceptionRecord:  # fmt: skip
    """Ask for more time. It is a new request, decided afresh, that points to the old one."""
    if exception.status not in ("approved", "expired"):
        raise Conflict("Only an exception that was approved can be renewed.")
    record_type, record = _record(session, exception)
    pending = session.scalars(
        select(ExceptionRecord.id).where(
            ExceptionRecord.renews_id == exception.id, ExceptionRecord.status == "requested"
        )
    ).first()
    if pending is not None:
        raise Conflict("A renewal of this exception is already waiting for a decision.")
    return request(
        session, principal, record_type, record, title=exception.title,
        requirement=exception.requirement, justification=justification,
        measures=exception.measures, ends_on=ends_on, renews=exception, rule=exception.rule,
    )  # fmt: skip


def decide(
    session: Session, principal: Principal, exception: ExceptionRecord, *,
    outcome: str, note: str, ends_on: date | None = None,
) -> ExceptionRecord:  # fmt: skip
    """Approve or decline. Nobody decides an exception they asked for."""
    if not principal.governs:
        raise PermissionDenied("Only governance can decide an exception.")
    if exception.requested_by == principal.account_id:
        raise PermissionDenied("You cannot decide an exception you asked for.")
    if exception.status != "requested":
        raise Conflict("This exception has already been decided.")
    note, errors = note.strip(), {}
    if outcome not in ("approved", "declined"):
        errors["outcome"] = "Approve or decline it."
    if len(note) < 10:
        errors["note"] = "Give the reason. It is shown to whoever asked."
    until = ends_on or exception.ends_on
    if outcome == "approved" and (until <= today() or until > today() + timedelta(days=MAX_DAYS)):
        errors["ends_on"] = "Choose an end date within a year from today."
    if errors:
        raise Invalid("The decision was not recorded.", errors)
    with audit.operation(session, "exception.decide"):
        exception.status = outcome
        exception.decided_by, exception.decided_at = principal.account_id, utc_now()
        exception.decision_note = note
        if outcome == "approved":
            exception.ends_on = until
        else:
            exception.closed_at = utc_now()
        session.flush()
    if exception.requested_by is not None:
        words = f"approved until {until:%b} {until.day}" if outcome == "approved" else "declined"
        review.notify(
            session, [exception.requested_by], "exception",
            f"Your exception was {words}: {exception.title}", f"/exceptions/{exception.ref}",
            skip=principal.account_id,
        )  # fmt: skip
    return exception


def end(
    session: Session, principal: Principal, exception: ExceptionRecord, reason: str = ""
) -> ExceptionRecord:
    """The requester takes back a request, or governance revokes an approved exception."""
    mine = exception.requested_by == principal.account_id
    if exception.status == "requested" and (mine or principal.governs):
        status = "withdrawn"
    elif exception.status == "approved" and principal.governs:
        status = "revoked"
        if len(reason.strip()) < 10:
            raise Invalid("It was not revoked.", {"reason": "Say why it is being revoked."})
    elif exception.status in OPEN:
        raise PermissionDenied("That is not yours to end.")
    else:
        raise Conflict("This exception has already ended.")
    with audit.operation(session, f"exception.{status}", reason=reason.strip()):
        exception.status, exception.closed_at = status, utc_now()
        session.flush()
    if status == "revoked" and exception.requested_by is not None:
        review.notify(
            session, [exception.requested_by], "exception",
            f"Your exception was revoked: {exception.title}", f"/exceptions/{exception.ref}",
            skip=principal.account_id,
        )  # fmt: skip
    return exception


# --- What falls due -----------------------------------------------------------------------


def expire(session: Session) -> int:
    """End every approved exception whose date has passed, and say so to whoever asked and
    to governance. Before that, remind the requester once that the end is coming."""
    now = today()
    governance = review.holders(session, roles.GOVERNANCE)
    approved = session.scalars(
        select(ExceptionRecord)
        .where(ExceptionRecord.status == "approved")
        .order_by(ExceptionRecord.id)
    ).all()
    ended = 0
    for exception in approved:
        href = f"/exceptions/{exception.ref}"
        asked = {exception.requested_by} if exception.requested_by is not None else set()
        if exception.ends_on < now:
            reason = f"It ended on {exception.ends_on:%Y-%m-%d}."
            with audit.operation(session, "exception.expire", reason=reason):
                exception.status, exception.closed_at = "expired", utc_now()
                session.flush()
            review.notify(session, asked | governance, "exception",
                          f"Exception ended: {exception.title}", href)  # fmt: skip
            ended += 1
        elif (exception.ends_on - now).days <= SOON_DAYS:
            sent = session.scalars(
                select(Reminder.id).where(
                    Reminder.subject_type == "exception", Reminder.subject_id == exception.id,
                    Reminder.stage == "soon",
                )
            ).first()  # fmt: skip
            if sent is None:
                session.add(Reminder(subject_type="exception", subject_id=exception.id,
                                     stage="soon", sent_on=now))  # fmt: skip
                review.notify(
                    session, asked, "reminder",
                    f"Exception ends {exception.ends_on:%b} {exception.ends_on.day}: renew it, "
                    f"or meet the requirement: {exception.title}", href,
                )  # fmt: skip
    session.flush()
    return ended


# --- Looking at exceptions ----------------------------------------------------------------


def _view(
    session: Session, principal: Principal, exception: ExceptionRecord, names: dict[int, str]
) -> dict[str, Any]:
    record_type, record = _record(session, exception)
    mine = exception.requested_by == principal.account_id
    renewal = session.scalars(
        select(ExceptionRecord.ref)
        .where(ExceptionRecord.renews_id == exception.id)
        .order_by(ExceptionRecord.id.desc())
    ).first()
    renews = session.get(ExceptionRecord, exception.renews_id) if exception.renews_id else None
    left = (exception.ends_on - today()).days
    return {
        "ref": exception.ref,
        "title": exception.title,
        "status": exception.status,
        "requirement": exception.requirement,
        "rule": exception.rule,
        "rule_label": RULES.get(exception.rule or ""),
        "justification": exception.justification,
        "measures": exception.measures,
        "ends_on": exception.ends_on,
        "ending_soon": exception.status == "approved" and left <= SOON_DAYS,
        "record": {"type": record_type.key, "path": record_type.path, "ref": record.ref,
                   "name": record.name} if record is not None else None,
        "org_unit_id": exception.org_unit_id,
        "requested_by": names.get(exception.requested_by or 0),
        "requested_at": exception.requested_at,
        "decided_by": names.get(exception.decided_by or 0),
        "decided_at": exception.decided_at,
        "decision_note": exception.decision_note,
        "closed_at": exception.closed_at,
        "renews": renews.ref if renews else None,
        "renewed_by": renewal,
        "can": {
            "decide": exception.status == "requested" and principal.governs and not mine,
            "withdraw": exception.status == "requested" and (mine or principal.governs),
            "revoke": exception.status == "approved" and principal.governs,
            "renew": exception.status in ("approved", "expired") and renewal is None
            and record is not None and access.can_edit(session, principal, record_type, record),
        },
    }  # fmt: skip


def _names(session: Session, rows: list[ExceptionRecord]) -> dict[int, str]:
    ids = {r.requested_by for r in rows} | {r.decided_by for r in rows}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(ids - {None} or {0}))
        ).all()  # type: ignore[arg-type]
    )


def view(session: Session, principal: Principal, exception: ExceptionRecord) -> dict[str, Any]:
    if not can_see(session, principal, exception):
        raise NotFound(f"There is no exception {exception.ref}.")
    return _view(session, principal, exception, _names(session, [exception]))


def register(
    session: Session, principal: Principal, *, status: str | None = None,
    record: tuple[RecordType, Any] | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """The register: every exception the person may see, those needing attention first."""
    statement = select(ExceptionRecord)
    if status == "open":
        statement = statement.where(ExceptionRecord.status.in_(OPEN))
    elif status:
        statement = statement.where(ExceptionRecord.status == status)
    if record is not None:
        statement = statement.where(
            ExceptionRecord.subject_type == record[0].key,
            ExceptionRecord.subject_id == record[1].id,
        )
    rows = [r for r in session.scalars(statement) if can_see(session, principal, r)]
    order = {"requested": 0, "approved": 1}
    rows.sort(key=lambda r: (order.get(r.status, 2), r.ends_on if r.status in OPEN else date.max,
                             -r.id))  # fmt: skip
    names = _names(session, rows)
    return [_view(session, principal, row, names) for row in rows]


def active_on(session: Session, subject_type: str, subject_id: int) -> list[ExceptionRecord]:
    return list(
        session.scalars(
            select(ExceptionRecord).where(
                ExceptionRecord.subject_type == subject_type,
                ExceptionRecord.subject_id == subject_id,
                ExceptionRecord.status == "approved",
            )
        )
    )
