"""Committee sessions: the reviews a meeting will consider, the decisions made in it, and
its minutes. Once closed, a session is a fixed record of what the body decided and when."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Account,
    CommitteeSession,
    Decision,
    Review,
    ReviewTask,
    SessionItem,
    UseCase,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.review import service

OUTCOME_WORDS = {
    "approved": "Approved",
    "approved_with_conditions": "Approved with conditions",
    "declined": "Declined",
    "returned": "Returned to the requester",
    "withdrawn": "Withdrawn",
}


def find(session: Session, ref: str) -> CommitteeSession:
    meeting = session.scalars(
        select(CommitteeSession).where(CommitteeSession.ref == ref.strip().upper())
    ).first()
    if meeting is None:
        raise NotFound(f"There is no session {ref}.")
    return meeting


def _governs(principal: Principal) -> None:
    if not principal.governs:
        raise PermissionDenied("Only governance can do that to a session.")


def _open(meeting: CommitteeSession) -> None:
    if meeting.status != "planned":
        raise Conflict("This session is closed. Its record cannot be changed.")


def plan(
    session: Session,
    principal: Principal,
    *,
    title: str,
    held_on: date | None,
    reviews: Iterable[str] = (),
) -> CommitteeSession:
    _governs(principal)
    title, errors = title.strip(), {}
    if not 3 <= len(title) <= 200:
        errors["title"] = "Give the session a name."
    if held_on is None:
        errors["held_on"] = "Choose the date of the meeting."
    if errors:
        raise Invalid("The session was not planned.", errors)
    assert held_on is not None
    with audit.operation(session, "session.plan"):
        meeting = CommitteeSession(
            ref=next_ref(session, "SES"),
            title=title,
            held_on=held_on,
            status="planned",
            created_by=principal.account_id,
            created_at=utc_now(),
        )
        session.add(meeting)
        session.flush()
        set_agenda(session, principal, meeting, reviews)
    return meeting


def items_of(session: Session, meeting: CommitteeSession) -> list[SessionItem]:
    return list(
        session.scalars(
            select(SessionItem)
            .where(SessionItem.session_id == meeting.id)
            .order_by(SessionItem.position, SessionItem.id)
        )
    )


def set_agenda(
    session: Session, principal: Principal, meeting: CommitteeSession, reviews: Iterable[str]
) -> None:
    """Put these reviews on the agenda, in this order. A review already decided in the
    session stays on it."""
    _governs(principal)
    _open(meeting)
    wanted: list[Review] = []
    for ref in dict.fromkeys(r.strip().upper() for r in reviews if r and r.strip()):
        found = session.scalars(select(Review).where(Review.ref == ref)).first()
        if found is None:
            raise Invalid("The agenda was not saved.", {"reviews": f"There is no review {ref}."})
        wanted.append(found)
    existing = {item.review_id: item for item in items_of(session, meeting)}
    decided_here = set(
        session.scalars(select(Decision.review_id).where(Decision.session_id == meeting.id))
    )
    for review in wanted:
        if review.id not in existing and review.status not in service.OPEN:
            raise Invalid(
                "The agenda was not saved.",
                {"reviews": f"{review.ref} has already been decided."},
            )
    with audit.operation(session, "session.agenda"):
        keep = {review.id for review in wanted} | decided_here
        for review_id, item in existing.items():
            if review_id not in keep:
                session.delete(item)
        for position, review in enumerate(wanted):
            item = existing.get(review.id)
            if item is None:
                session.add(
                    SessionItem(session_id=meeting.id, review_id=review.id, position=position)
                )
            else:
                item.position = position
        session.flush()


def for_decision(session: Session, review: Review, ref: str) -> int:
    """The session a decision is being made in. The review must be on its agenda."""
    meeting = find(session, ref)
    _open(meeting)
    on_agenda = session.scalars(
        select(SessionItem.id).where(
            SessionItem.session_id == meeting.id, SessionItem.review_id == review.id
        )
    ).first()
    if on_agenda is None:
        raise Conflict(f"{review.ref} is not on the agenda of {meeting.ref}.")
    return meeting.id


def record(
    session: Session,
    principal: Principal,
    meeting: CommitteeSession,
    *,
    attendees: str | None = None,
    minutes: str | None = None,
    close: bool = False,
) -> CommitteeSession:
    """Write down who attended and the minutes. Closing the session fixes its record."""
    _governs(principal)
    _open(meeting)
    if attendees is not None:
        meeting.attendees = attendees.strip() or None
    if minutes is not None:
        meeting.minutes = minutes.strip() or None
    if close:
        errors = {}
        if len(meeting.attendees or "") < 3:
            errors["attendees"] = "Say who attended."
        if len(meeting.minutes or "") < 10:
            errors["minutes"] = "Write the minutes before closing the session."
        if errors:
            raise Invalid("The session was not closed.", errors)
    with audit.operation(session, "session.close" if close else "session.record"):
        if close:
            meeting.status = "closed"
            meeting.closed_by, meeting.closed_at = principal.account_id, utc_now()
        session.flush()
    return meeting


# --- Looking at sessions ------------------------------------------------------------------


def listing(session: Session) -> list[dict[str, Any]]:
    meetings = session.scalars(
        select(CommitteeSession).order_by(
            CommitteeSession.held_on.desc(), CommitteeSession.id.desc()
        )
    ).all()
    counts = dict(
        session.execute(
            select(SessionItem.session_id, func.count()).group_by(SessionItem.session_id)
        ).all()  # type: ignore[arg-type]
    )
    decided = dict(
        session.execute(
            select(Decision.session_id, func.count())
            .where(Decision.session_id.is_not(None), Decision.outcome != "returned")
            .group_by(Decision.session_id)
        ).all()  # type: ignore[arg-type]
    )
    return [
        {
            "ref": m.ref,
            "title": m.title,
            "held_on": m.held_on,
            "status": m.status,
            "items": counts.get(m.id, 0),
            "decided": decided.get(m.id, 0),
        }
        for m in meetings
    ]


def candidates(session: Session, meeting: CommitteeSession | None = None) -> list[dict[str, Any]]:
    """Open reviews that a committee decides and that are on no other planned session."""
    taken = set(
        session.scalars(
            select(SessionItem.review_id)
            .join(CommitteeSession, CommitteeSession.id == SessionItem.session_id)
            .where(CommitteeSession.status == "planned")
        )
    )
    rows = session.execute(
        select(Review, UseCase)
        .join(UseCase, UseCase.id == Review.subject_id)
        .where(Review.status.in_(service.OPEN), Review.authority != "governance")
        .order_by(Review.status != "ready", Review.due_on.is_(None), Review.due_on, Review.id)
    ).all()
    return [
        {"ref": r.ref, "name": u.name, "tier": u.tier, "status": r.status, "due_on": r.due_on}
        for r, u in rows
        if r.id not in taken
    ]


def view(session: Session, principal: Principal, meeting: CommitteeSession) -> dict[str, Any]:
    items = items_of(session, meeting)
    review_ids = [item.review_id for item in items]
    reviews = {
        r.id: (r, u)
        for r, u in session.execute(
            select(Review, UseCase)
            .join(UseCase, UseCase.id == Review.subject_id)
            .where(Review.id.in_(review_ids or [0]))
        )
    }
    findings: dict[int, list[str]] = {}
    for task in session.scalars(
        select(ReviewTask).where(ReviewTask.review_id.in_(review_ids or [0]))
    ):
        if task.status == "completed" and task.finding:
            findings.setdefault(task.review_id, []).append(task.finding)
    decisions: dict[int, Decision] = {}
    for decision in session.scalars(
        select(Decision).where(Decision.session_id == meeting.id).order_by(Decision.id)
    ):
        decisions[decision.review_id] = decision
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_(
                    {d.decided_by for d in decisions.values()} | {meeting.closed_by} - {None} or {0}
                )
            )
        ).all()  # type: ignore[arg-type]
    )
    agenda = []
    for item in items:
        review, use_case = reviews[item.review_id]
        decision = decisions.get(review.id)
        found = findings.get(review.id, [])
        asked = service.acceptance_of(session, review) if service.needs_acceptance(review) else None
        agenda.append(
            {
                "review": review.ref,
                "kind": review.kind,
                "status": review.status,
                "use_case": {"ref": use_case.ref, "name": use_case.name},
                "tier": use_case.tier,
                "authority": review.authority,
                "objections": found.count("objection"),
                "with_conditions": found.count("conditions"),
                "no_concerns": found.count("no_concerns"),
                "acceptance": asked.status
                if asked
                else ("needed" if service.needs_acceptance(review) else None),
                "decision": {
                    "outcome": decision.outcome,
                    "words": OUTCOME_WORDS.get(decision.outcome, decision.outcome),
                    "rationale": decision.rationale,
                    "decided_by": names.get(decision.decided_by or 0),
                    "over_objection": decision.over_objection,
                }
                if decision
                else None,
            }
        )
    planned = meeting.status == "planned"
    return {
        "ref": meeting.ref,
        "title": meeting.title,
        "held_on": meeting.held_on,
        "status": meeting.status,
        "attendees": meeting.attendees,
        "minutes": meeting.minutes,
        "closed_at": meeting.closed_at,
        "closed_by": names.get(meeting.closed_by or 0),
        "agenda": agenda,
        "candidates": candidates(session, meeting) if planned and principal.governs else [],
        "can_edit": planned and principal.governs,
    }
