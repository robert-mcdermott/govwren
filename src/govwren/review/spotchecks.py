"""Spot checks: a second look at a sample of the approvals that rules made by themselves,
so that the rules are known to be deciding what a person would."""

from __future__ import annotations

import hashlib
import random
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Decision, Review, SpotCheck, UseCase
from govwren.events import audit
from govwren.review import service

WINDOW_DAYS = 120  # how far back a sample is drawn from
ONE_IN = 10  # the share the scheduler draws by itself


def _unsampled(session: Session) -> list[Decision]:
    """Approvals made by rule in the window that have not been drawn before."""
    since = utc_now() - timedelta(days=WINDOW_DAYS)
    drawn = select(SpotCheck.decision_id)
    return list(
        session.scalars(
            select(Decision)
            .where(
                Decision.by_rule.is_not(None),
                Decision.outcome.in_(service.APPROVED),
                Decision.decided_at >= since,
                Decision.id.not_in(drawn),
            )
            .order_by(Decision.id)
        )
    )


def _add(session: Session, decisions: list[Decision], by: int | None) -> int:
    now = utc_now()
    for decision in decisions:
        session.add(
            SpotCheck(
                decision_id=decision.id,
                review_id=decision.review_id,
                status="pending",
                sampled_by=by,
                sampled_at=now,
            )
        )
    session.flush()
    return len(decisions)


def draw(session: Session, principal: Principal, count: int) -> int:
    """Draw a random sample of automatic approvals for a person to check."""
    if not principal.governs:
        raise PermissionDenied("Only governance can draw a sample.")
    if not 1 <= count <= 50:
        raise Invalid("No sample was drawn.", {"count": "Choose between 1 and 50."})
    pool = _unsampled(session)
    if not pool:
        raise Conflict("Every automatic approval of the last four months has been drawn already.")
    with audit.operation(session, "spot_check.draw"):
        return _add(
            session, random.SystemRandom().sample(pool, min(count, len(pool))), principal.account_id
        )


def draw_scheduled(session: Session) -> int:
    """The scheduler's share: about one automatic approval in ten, chosen by a rule that
    gives the same answer whenever it is run, so nothing is drawn twice or skipped."""
    chosen = [
        decision
        for decision in _unsampled(session)
        if int(hashlib.sha256(f"spot:{decision.id}".encode()).hexdigest(), 16) % ONE_IN == 0
    ]
    if not chosen:
        return 0
    with audit.operation(session, "spot_check.draw"):
        drawn = _add(session, chosen, None)
    service.notify(
        session,
        service.holders(session, roles.GOVERNANCE),
        "spot_check",
        f"{drawn} automatic approval{'' if drawn == 1 else 's'} to spot-check",
        "/spot-checks",
    )
    return drawn


def check(
    session: Session, principal: Principal, check_id: int, *, agree: bool, note: str
) -> SpotCheck:
    """Record the checker's view. Disagreeing calls the approval in: a review opens."""
    if not principal.governs:
        raise PermissionDenied("Only governance can record a spot check.")
    found = session.get(SpotCheck, check_id)
    if found is None:
        raise NotFound("There is no such spot check.")
    if found.status != "pending":
        raise Conflict("This one has already been checked.")
    review = session.get(Review, found.review_id)
    assert review is not None
    use_case = service.subject_of(session, review)
    if service.is_requester(session, principal, use_case):
        raise PermissionDenied("You cannot check the approval of your own request.")
    note = note.strip()
    if not agree and len(note) < 10:
        raise Invalid("The check was not recorded.", {"note": "Say what the rule got wrong."})
    with audit.operation(session, "spot_check.record"):
        found.status = "agreed" if agree else "disagreed"
        found.note = note or None
        found.checked_by, found.checked_at = principal.account_id, utc_now()
        session.flush()
        if (
            not agree
            and use_case.status in service.APPROVED
            and service.open_review(session, use_case) is None
        ):
            called = service.open_called_review(
                session,
                principal,
                use_case,
                kind="periodic",
                why={"spot_check": {"note": note, "decision_of": review.ref}},
                operation="review.called_in",
                reason=note,
            )
            found.followup_review_id = called.id
            session.flush()
    return found


def listing(session: Session, principal: Principal) -> dict[str, Any]:
    rows = session.execute(
        select(SpotCheck, Decision, Review, UseCase)
        .join(Decision, Decision.id == SpotCheck.decision_id)
        .join(Review, Review.id == SpotCheck.review_id)
        .join(UseCase, UseCase.id == Review.subject_id)
        .order_by(SpotCheck.status != "pending", SpotCheck.id.desc())
        .limit(200)
    ).all()
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_({c.checked_by for c, *_ in rows} - {None} or {0})
            )
        ).all()  # type: ignore[arg-type]
    )
    followups = {
        r.id: r.ref
        for r in session.scalars(
            select(Review).where(
                Review.id.in_({c.followup_review_id for c, *_ in rows} - {None} or {0})
            )
        )
    }
    checks = [
        {
            "id": check_.id,
            "status": check_.status,
            "note": check_.note,
            "sampled_at": check_.sampled_at,
            "by_scheduler": check_.sampled_by is None,
            "checked_by": names.get(check_.checked_by or 0),
            "checked_at": check_.checked_at,
            "followup": followups.get(check_.followup_review_id or 0),
            "review": review.ref,
            "rule": decision.by_rule,
            "decided_at": decision.decided_at,
            "use_case": {
                "ref": use_case.ref,
                "name": use_case.name,
                "tier": use_case.tier,
                "status": use_case.status,
                "org_unit_id": use_case.org_unit_id,
            },
            "can_check": check_.status == "pending"
            and principal.governs
            and not service.is_requester(session, principal, use_case),
        }
        for check_, decision, review, use_case in rows
    ]
    done = [c for c in checks if c["status"] != "pending"]
    agreed = sum(1 for c in done if c["status"] == "agreed")
    return {
        "checks": checks,
        "pending": len(checks) - len(done),
        "checked": len(done),
        "agreed": agreed,
        "agreement": round(100 * agreed / len(done)) if done else None,
        "available": len(_unsampled(session)),
        "can_draw": principal.governs,
    }
