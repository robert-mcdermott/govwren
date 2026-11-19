"""A review's life: opened by the rules, triaged, reviewed in parallel, discussed with the
requester, decided, and followed by its conditions.

Two rules hold throughout. Nobody reviews, triages, or decides a request they made or own.
And what reviewers say among themselves is never shown to the requester.
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied, StoreError
from govwren.db.models import (
    Account,
    Comment,
    Condition,
    Decision,
    FormResponse,
    IncidentRecord,
    IntakeDraft,
    Notification,
    RecordOwner,
    Review,
    ReviewTask,
    RiskAcceptance,
    RoleGrant,
    RuleSet,
    TierAssessment,
    UseCase,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.intake import forms
from govwren.inventory import access, records
from govwren.inventory.registry import USE_CASE
from govwren.people import units
from govwren.program import packs, vocab
from govwren.review import routing

OPEN = ("triage", "in_review", "with_requester", "ready")
APPROVED = ("approved", "approved_with_conditions")
FINDING_WORDS = {
    "no_concerns": "no concerns",
    "conditions": "acceptable with conditions",
    "objection": "objection",
}


# --- Small helpers ------------------------------------------------------------------------


def working_days_from(start: date, days: int) -> date:
    """The date this many working days after ``start``. Weekends do not count."""
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def add_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year, month = start.year + month // 12, month % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def current_rules(session: Session) -> RuleSet:
    rules = packs.published_rules(session)
    if rules is None:
        raise StoreError(
            "There are no routing rules. Run `govwren db upgrade` to load the default program."
        )
    return rules


def subject_of(session: Session, review: Review) -> UseCase:
    use_case = session.get(UseCase, review.subject_id)
    assert use_case is not None
    return use_case


def requester_ids(session: Session, use_case: UseCase) -> set[int]:
    """The people on the asking side: whoever made the request, and its owners."""
    ids = set(
        session.scalars(
            select(RecordOwner.account_id).where(
                RecordOwner.record_type == "use_case",
                RecordOwner.record_id == use_case.id,
                RecordOwner.kind != "contact",
            )
        )
    )
    if use_case.created_by is not None:
        ids.add(use_case.created_by)
    return ids


def is_requester(session: Session, principal: Principal, use_case: UseCase) -> bool:
    return principal.account_id is not None and principal.account_id in requester_ids(
        session, use_case
    )


def _not_own(session: Session, principal: Principal, use_case: UseCase, what: str) -> None:
    if is_requester(session, principal, use_case):
        raise PermissionDenied(f"You cannot {what} a request that is your own.")


def tasks_of(session: Session, review: Review) -> list[ReviewTask]:
    return list(
        session.scalars(
            select(ReviewTask).where(ReviewTask.review_id == review.id).order_by(ReviewTask.id)
        )
    )


def latest_assessment(session: Session, use_case: UseCase) -> TierAssessment | None:
    return session.scalars(
        select(TierAssessment)
        .where(TierAssessment.subject_type == "use_case", TierAssessment.subject_id == use_case.id)
        .order_by(TierAssessment.id.desc())
    ).first()


def latest_answers(session: Session, use_case: UseCase) -> dict[str, Any]:
    response = session.scalars(
        select(FormResponse)
        .where(FormResponse.subject_type == "use_case", FormResponse.subject_id == use_case.id)
        .order_by(FormResponse.id.desc())
    ).first()
    return dict(response.answers) if response else {}


def open_review(session: Session, use_case: UseCase) -> Review | None:
    return session.scalars(
        select(Review)
        .where(
            Review.subject_type == "use_case",
            Review.subject_id == use_case.id,
            Review.status.in_(OPEN),
        )
        .order_by(Review.id.desc())
    ).first()


def latest_review(session: Session, use_case: UseCase) -> Review | None:
    return session.scalars(
        select(Review)
        .where(Review.subject_type == "use_case", Review.subject_id == use_case.id)
        .order_by(Review.id.desc())
    ).first()


def holders(session: Session, role: str, function: str | None = None) -> set[int]:
    """Active accounts holding a role; for reviewers, those who review the given function."""
    statement = (
        select(RoleGrant.account_id, RoleGrant.review_function)
        .join(Account, Account.id == RoleGrant.account_id)
        .where(RoleGrant.role == role, Account.status == "active")
    )
    return {
        account_id
        for account_id, granted in session.execute(statement)
        if role != roles.REVIEWER or function is None or granted is None or granted == function
    }


def notify(
    session: Session,
    account_ids: Iterable[int],
    kind: str,
    title: str,
    href: str,
    *,
    skip: int | None = None,
) -> None:
    now = utc_now()
    for account_id in sorted(set(account_ids)):
        if account_id != skip:
            session.add(
                Notification(
                    account_id=account_id, kind=kind, title=title[:300], href=href, created_at=now
                )
            )


def _touch(use_case: UseCase, status: str | None = None) -> None:
    if status is not None:
        use_case.status = status
    use_case.version += 1
    use_case.updated_at = utc_now()


def _accountable(session: Session, use_case: UseCase) -> int | None:
    owners = session.scalars(
        select(RecordOwner.account_id)
        .where(
            RecordOwner.record_type == "use_case",
            RecordOwner.record_id == use_case.id,
            RecordOwner.kind == "accountable",
        )
        .order_by(RecordOwner.id)
    ).first()
    return owners if owners is not None else use_case.created_by


def _functions(principal: Principal) -> frozenset[str] | None:
    return principal.review_functions()


def _reviews_function(principal: Principal, function: str) -> bool:
    mine = _functions(principal)
    return mine is None or function in mine


def sees_internal(session: Session, principal: Principal, review: Review) -> bool:
    """May this person read findings and what reviewers say among themselves?"""
    if is_requester(session, principal, subject_of(session, review)):
        return False  # whatever their role: nobody reads the reviewers' notes on their own request
    if principal.reads_all:
        return True
    asked = acceptance_of(session, review)
    if asked is not None and asked.account_id == principal.account_id:
        return True  # whoever is asked to accept the risk sees what the reviewers found
    mine = _functions(principal)
    if mine is not None and not mine:
        return False
    return any(
        _reviews_function(principal, task.review_function) for task in tasks_of(session, review)
    )


def acceptance_of(session: Session, review: Review) -> RiskAcceptance | None:
    """The request for a named person to accept the risk that currently stands, if any."""
    return session.scalars(
        select(RiskAcceptance)
        .where(RiskAcceptance.review_id == review.id, RiskAcceptance.status != "replaced")
        .order_by(RiskAcceptance.id.desc())
    ).first()


def needs_acceptance(review: Review) -> bool:
    return review.authority == "committee_with_acceptance"


def request_acceptance(
    session: Session, principal: Principal, review: Review, account_id: int | None
) -> RiskAcceptance:
    """Ask a named person to accept the risk of a use. It cannot be someone on the asking
    side of the request, and asking someone new replaces whoever was asked before."""
    if not principal.governs:
        raise PermissionDenied("Only governance can ask someone to accept a risk.")
    use_case = subject_of(session, review)
    _not_own(session, principal, use_case, "ask for the risk of")
    if review.status not in OPEN:
        raise Conflict("This review has already been decided.")
    if not needs_acceptance(review):
        raise Conflict("The rules do not require a risk acceptance for this request.")
    named = session.get(Account, account_id) if account_id else None
    if named is None or named.status != "active":
        raise Invalid("Nobody was asked.", {"account_id": "Choose who will accept the risk."})
    if named.id in requester_ids(session, use_case):
        raise Invalid(
            "Nobody was asked.",
            {"account_id": "The risk cannot be accepted by someone who made or owns the request."},
        )
    with audit.operation(session, "review.acceptance", review=review.ref):
        earlier = acceptance_of(session, review)
        if earlier is not None:
            earlier.status = "replaced"
        asked = RiskAcceptance(
            review_id=review.id,
            account_id=named.id,
            status="requested",
            requested_by=principal.account_id,
            requested_at=utc_now(),
        )
        session.add(asked)
        session.flush()
    notify(
        session,
        [named.id],
        "acceptance",
        f"You are asked to accept the risk of: {use_case.name}",
        f"/reviews?open={review.ref}",
        skip=principal.account_id,
    )
    return asked


def answer_acceptance(
    session: Session, principal: Principal, review: Review, *, accept: bool, statement: str
) -> RiskAcceptance:
    """The named person accepts the risk, or declines to, in their own words."""
    asked = acceptance_of(session, review)
    if asked is None or asked.account_id != principal.account_id:
        raise PermissionDenied("You have not been asked to accept this risk.")
    if asked.status != "requested":
        raise Conflict("You have already answered.")
    if review.status not in OPEN:
        raise Conflict("This review has already been decided.")
    statement = statement.strip()
    if len(statement) < 10:
        raise Invalid(
            "Your answer was not recorded.",
            {"statement": "Say in your own words what you accept, or why you do not."},
        )
    use_case = subject_of(session, review)
    with audit.operation(session, "review.acceptance", review=review.ref):
        asked.status = "accepted" if accept else "declined"
        asked.statement, asked.answered_at = statement, utc_now()
        session.flush()
    notify(
        session,
        holders(session, roles.GOVERNANCE),
        "acceptance",
        f"Risk {'accepted' if accept else 'not accepted'}: {use_case.name}",
        f"/reviews?open={review.ref}",
        skip=principal.account_id,
    )
    return asked


def can_see(session: Session, principal: Principal, review: Review) -> bool:
    if sees_internal(session, principal, review):
        return True
    return access.sight(session, principal, USE_CASE, subject_of(session, review)) == access.FULL


def find(session: Session, principal: Principal, ref: str) -> Review:
    review = session.scalars(select(Review).where(Review.ref == ref.strip().upper())).first()
    if review is None or not can_see(session, principal, review):
        raise NotFound(f"There is no review {ref}.")
    return review


# --- Opening ------------------------------------------------------------------------------


def open_initial(session: Session, principal: Principal, use_case: UseCase) -> Review:
    """Open the review of a request that has just been submitted and tiered. The rules say
    who must look at it; if they say nobody need, and a rule approves it, it is approved."""
    assessment = latest_assessment(session, use_case)
    assert assessment is not None
    rules = current_rules(session)
    answers = latest_answers(session, use_case)
    route = routing.route(rules.definition, assessment.final_tier, answers, assessment.stops)
    opened = today()
    review = Review(
        ref=next_ref(session, "RV"),
        subject_type="use_case",
        subject_id=use_case.id,
        kind="initial",
        status="triage",
        tier_at_open=assessment.final_tier,
        rule_set_id=rules.id,
        authority=route["authority"],
        routing=route,
        opened_by=principal.account_id,
        opened_at=utc_now(),
        due_on=working_days_from(opened, route["due_days"]) if route["due_days"] else None,
        paused_seconds=0,
    )
    session.add(review)
    session.flush()
    if route["auto_approve"]:
        _approve_by_rule(session, review, use_case, rules, route)
        return review
    for entry in route["require"]:
        session.add(
            ReviewTask(
                review_id=review.id,
                review_function=entry["function"],
                status="pending",
                required_by=entry["rule"],
                recommended_conditions=[],
                due_on=review.due_on,
            )
        )
    _touch(use_case, "in_review")
    session.flush()
    href = f"/reviews?open={review.ref}"
    notify(
        session,
        holders(session, roles.GOVERNANCE),
        "triage",
        f"New request to triage: {use_case.name}",
        href,
        skip=principal.account_id,
    )
    return review


def _open_keys(session: Session, use_case: UseCase) -> set[str]:
    """The standard conditions already open on a use case, by template."""
    return {
        c.template_key
        for c in conditions_of(session, use_case)
        if c.status == "open" and c.template_key
    }


def _conditions_from_templates(
    session: Session, decision: Decision, use_case: UseCase, rules: RuleSet, keys: Iterable[str]
) -> list[Condition]:
    templates = routing.templates_by_key(rules.definition)
    owner = _accountable(session, use_case)
    standing = _open_keys(session, use_case)
    made = []
    for key in keys:
        template = templates.get(key)
        if template is None or key in standing:
            continue  # a renewal does not set again a standard condition that still stands
        kind = template.get("kind", "ongoing")
        due = working_days_from(today(), template["due_days"]) if template.get("due_days") else None
        condition = Condition(
            decision_id=decision.id,
            subject_type="use_case",
            subject_id=use_case.id,
            template_key=key,
            text=template["text"],
            kind=kind,
            owner_id=owner,
            due_on=due,
            status="open",
        )
        session.add(condition)
        made.append(condition)
    return made


def _approve_by_rule(
    session: Session, review: Review, use_case: UseCase, rules: RuleSet, route: Mapping[str, Any]
) -> None:
    now = utc_now()
    until = add_months(today(), route["cadence_months"] or 12)
    decision = Decision(
        review_id=review.id,
        outcome="approved_with_conditions" if route["conditions"] else "approved",
        rationale=f"Approved by rule: {route['auto_approve']}. No rule required a review, "
        "and nothing about the request is a prohibited use.",
        decided_by=None,
        authority="rule",
        by_rule=route["auto_approve"],
        over_objection=False,
        tier=review.tier_at_open,
        approved_until=until,
        decided_at=now,
    )
    session.add(decision)
    session.flush()
    _conditions_from_templates(session, decision, use_case, rules, route["conditions"])
    review.status = "decided"
    review.closed_at = now
    use_case.approved_until = until
    use_case.next_review_on = until
    _touch(use_case, decision.outcome)
    session.flush()


def resubmitted(session: Session, principal: Principal, use_case: UseCase) -> Review | None:
    """The requester changed their answers while the request was back with them: note it,
    with the tier it now has, and put the review back where it was."""
    review = open_review(session, use_case)
    if review is None:
        return open_initial(session, principal, use_case)
    assessment = latest_assessment(session, use_case)
    labels = _tier_labels(session, assessment)
    tier = (
        labels.get(assessment.final_tier, str(assessment.final_tier)) if assessment else "not set"
    )
    session.add(
        Comment(
            subject_type="review",
            subject_id=review.id,
            author_id=principal.account_id,
            visibility="requester",
            body=f"Updated the answers to the request. The tier is now {tier}.",
            is_question=False,
            created_at=utc_now(),
        )
    )
    _resume(session, review, use_case)
    notify(
        session,
        _reviewing_side(session, review),
        "reply",
        f"The requester updated {use_case.name}",
        f"/reviews?open={review.ref}",
        skip=principal.account_id,
    )
    return review


def _tier_labels(session: Session, assessment: TierAssessment | None) -> dict[int, str]:
    from govwren.db.models import ScoringModel

    model = session.get(ScoringModel, assessment.scoring_model_id) if assessment else None
    return {tier["level"]: tier["label"] for tier in model.definition["tiers"]} if model else {}


def _reviewing_side(session: Session, review: Review) -> set[int]:
    ids = holders(session, roles.GOVERNANCE)
    for task in tasks_of(session, review):
        if task.assignee_id is not None:
            ids.add(task.assignee_id)
    return ids


def _standing(use_case: UseCase, review: Review, status: str) -> None:
    """A first review moves the request's standing as it goes. A later review of something
    already decided leaves the standing alone until it is itself decided."""
    _touch(use_case, status if review.kind == "initial" else None)


def _pause(session: Session, review: Review, use_case: UseCase) -> None:
    if review.status != "with_requester":
        review.resume_status = review.status
        review.status = "with_requester"
        review.paused_at = utc_now()
        _standing(use_case, review, "returned")


def _resume(session: Session, review: Review, use_case: UseCase) -> None:
    if review.status == "with_requester":
        if review.paused_at is not None:
            review.paused_seconds += int((utc_now() - review.paused_at).total_seconds())
        review.status = review.resume_status or "in_review"
        review.resume_status = None
        review.paused_at = None
        _settle(session, review)
        _standing(use_case, review, "in_review")


def _settle(session: Session, review: Review) -> None:
    """Once triage is done and every task is finished, the review is ready for a decision."""
    if review.status == "in_review" and all(
        task.status != "pending" for task in tasks_of(session, review)
    ):
        review.status = "ready"
        use_case = subject_of(session, review)
        notify(
            session,
            holders(session, roles.GOVERNANCE),
            "decide",
            f"Ready for a decision: {use_case.name}",
            f"/reviews?open={review.ref}",
        )


# --- Periodic review ----------------------------------------------------------------------


def stewards_of(session: Session, org_unit_id: int | None) -> set[int]:
    """Active stewards of a unit: those granted it, or any unit above it."""
    if org_unit_id is None:
        return set()
    covered = [org_unit_id, *(unit.id for unit in units.ancestors(session, org_unit_id))]
    return set(
        session.scalars(
            select(RoleGrant.account_id)
            .join(Account, Account.id == RoleGrant.account_id)
            .where(
                RoleGrant.role == roles.STEWARD,
                RoleGrant.org_unit_id.in_(covered),
                Account.status == "active",
            )
        )
    )


def awaiting_owner(session: Session, use_case: UseCase) -> Review | None:
    """The review of an approved use that is waiting for its owner to confirm the answers."""
    review = open_review(session, use_case)
    if review is not None and review.kind != "initial" and review.status == "with_requester":
        return review
    return None


def _drop_draft(session: Session, use_case: UseCase) -> None:
    draft = session.get(IntakeDraft, use_case.id)
    if draft is not None:
        session.delete(draft)


def open_called_review(
    session: Session,
    principal: Principal,
    use_case: UseCase,
    *,
    kind: str,
    why: Mapping[str, Any],
    operation: str,
    reason: str,
) -> Review:
    """Open a review of a use that already has an approval, at governance's call. It goes
    straight to triage with the reviews the rules require of the use as it stands."""
    if use_case.status not in (*APPROVED, "suspended"):
        raise Conflict("Only a use with an approval can be reviewed again.")
    if open_review(session, use_case) is not None:
        raise Conflict("A review of this use is already open.")
    rules = current_rules(session)
    assessment = latest_assessment(session, use_case)
    tier = use_case.tier or (assessment.final_tier if assessment else 1)
    route = routing.route(rules.definition, tier, latest_answers(session, use_case), [])
    with audit.operation(session, operation, reason=reason):
        review = Review(
            ref=next_ref(session, "RV"),
            subject_type="use_case",
            subject_id=use_case.id,
            kind=kind,
            status="triage",
            tier_at_open=tier,
            rule_set_id=rules.id,
            authority=route["authority"],
            routing={**route, **why},
            opened_by=principal.account_id,
            opened_at=utc_now(),
            due_on=working_days_from(today(), route["due_days"]) if route["due_days"] else None,
            paused_seconds=0,
        )
        session.add(review)
        session.flush()
        for entry in route["require"]:
            session.add(
                ReviewTask(
                    review_id=review.id,
                    review_function=entry["function"],
                    status="pending",
                    required_by=entry["rule"],
                    recommended_conditions=[],
                    due_on=review.due_on,
                )
            )
        _touch(use_case)
        session.flush()
    label = "Incident review" if kind == "incident" else "Review called in"
    notify(
        session,
        holders(session, roles.GOVERNANCE),
        "triage",
        f"{label} to triage: {use_case.name}",
        f"/reviews?open={review.ref}",
        skip=principal.account_id,
    )
    return review


def open_incident_review(
    session: Session, principal: Principal, use_case: UseCase, incident_ref: str, reason: str
) -> Review:
    """Open a review of an approved or suspended use because of an incident."""
    return open_called_review(
        session,
        principal,
        use_case,
        kind="incident",
        why={"incident": {"ref": incident_ref, "reason": reason}},
        operation="review.incident",
        reason=reason,
    )


def carry_forward(session: Session, use_case: UseCase, answers: Mapping[str, Any]) -> None:
    """Put the answers given last time back in front of the owner, as a draft to correct."""
    if session.get(IntakeDraft, use_case.id) is not None:
        return
    form = packs.published_form(session, "use_case_intake")
    if form is None:
        return
    if not answers:
        linked = [s.ref for s in records.systems_of(session, [use_case.id]).get(use_case.id, [])]
        answers = forms.prefill(form.schema, use_case, linked)
    session.add(
        IntakeDraft(
            use_case_id=use_case.id,
            form_version_id=form.id,
            answers=dict(answers),
            updated_at=utc_now(),
        )
    )


def open_periodic(session: Session, use_case: UseCase) -> Review:
    """Open the review an approval needs before it ends. It starts with the owner: the
    answers given last time are put back in front of them to confirm or correct, and the
    standing of the use does not change while they do."""
    rules = current_rules(session)
    assessment = latest_assessment(session, use_case)
    answers = latest_answers(session, use_case)
    tier = use_case.tier or (assessment.final_tier if assessment else 1)
    now = utc_now()
    with audit.operation(session, "review.periodic", due=str(use_case.next_review_on)):
        review = Review(
            ref=next_ref(session, "RV"),
            subject_type="use_case",
            subject_id=use_case.id,
            kind="periodic",
            status="with_requester",
            tier_at_open=tier,
            rule_set_id=rules.id,
            authority="governance",
            routing=routing.route(rules.definition, tier, answers, []),
            opened_by=None,
            opened_at=now,
            due_on=use_case.approved_until or use_case.next_review_on,
            paused_at=now,
            paused_seconds=0,
        )
        session.add(review)
        carry_forward(session, use_case, answers)
        _touch(use_case)
        session.flush()
    notify(
        session,
        requester_ids(session, use_case),
        "periodic",
        f"Periodic review: confirm {use_case.name} is still accurate",
        f"/use-cases/{use_case.ref}/request",
    )
    return review


def confirmed(session: Session, principal: Principal, use_case: UseCase, review: Review) -> Review:
    """The owner has confirmed or corrected the answers for a periodic review. The rules are
    applied to them as they now stand: approved again on the spot, or on to reviewers."""
    assessment = latest_assessment(session, use_case)
    assert assessment is not None
    now = utc_now()
    href = f"/reviews?open={review.ref}"
    if review.resume_status is not None:  # sent back with a question, now answered
        _resume(session, review, use_case)
        notify(
            session,
            _reviewing_side(session, review),
            "reply",
            f"The owner updated {use_case.name}",
            href,
            skip=principal.account_id,
        )
        return review
    rules = current_rules(session)
    route = routing.route(
        rules.definition, assessment.final_tier, latest_answers(session, use_case), assessment.stops
    )
    if review.paused_at is not None:
        review.paused_seconds += int((now - review.paused_at).total_seconds())
        review.paused_at = None
    limited: set[str] | None = None
    if review.kind == "change":
        from govwren.oversight import changes

        form = packs.published_form(session, "use_case_intake")
        earlier = changes.previous_answers(session, use_case)
        verdict = changes.judge(
            rules.definition,
            changes.differences(
                session, form.schema if form else {"sections": []}, earlier,
                latest_answers(session, use_case),
            ),
            tier_before=review.tier_at_open or assessment.final_tier,
            tier_after=assessment.final_tier,
            required_before={entry["function"] for entry in review.routing.get("require", [])},
            required_after={entry["function"] for entry in route["require"]},
        )  # fmt: skip
        route = {**route, "change": {**review.routing.get("change", {}), **verdict}}
        # A change review looks at what changed: the reviews newly required if there are
        # any, and otherwise those the use already needed.
        limited = set(verdict["new_functions"]) or None
        if not verdict["material"]:
            review.rule_set_id, review.routing = rules.id, route
            _record_not_material(session, review, use_case, verdict)
            return review
    review.rule_set_id, review.routing, review.authority = rules.id, route, route["authority"]
    review.tier_at_open = assessment.final_tier
    review.opened_by = review.opened_by or principal.account_id
    review.due_on = working_days_from(today(), route["due_days"]) if route["due_days"] else None
    if route["auto_approve"] and review.kind != "change":
        _approve_by_rule(session, review, use_case, rules, route)
        return review
    for entry in route["require"]:
        if limited is not None and entry["function"] not in limited:
            continue
        session.add(
            ReviewTask(
                review_id=review.id,
                review_function=entry["function"],
                status="pending",
                required_by=entry["rule"],
                recommended_conditions=[],
                due_on=review.due_on,
            )
        )
    review.status = "triage"
    _touch(use_case)
    session.flush()
    notify(
        session,
        holders(session, roles.GOVERNANCE),
        "triage",
        f"{'Change' if review.kind == 'change' else 'Periodic review'} to triage: {use_case.name}",
        href,
        skip=principal.account_id,
    )
    return review


def _record_not_material(
    session: Session, review: Review, use_case: UseCase, verdict: Mapping[str, Any]
) -> None:
    """A declared change that the rules do not count as material: it is recorded, and the
    approval stands as it was, with the same end date."""
    now = utc_now()
    count = len(verdict["changed"])
    decision = Decision(
        review_id=review.id,
        outcome=use_case.status if use_case.status in APPROVED else "approved",
        rationale="Recorded by rule: not a material change. "
        + (
            f"{count} answer{'' if count == 1 else 's'} changed, none that the approval "
            "rested on, and the risk tier is no higher."
            if count
            else "No answer changed."
        ),
        decided_by=None,
        authority="rule",
        by_rule="Not a material change",
        over_objection=False,
        tier=use_case.tier,
        approved_until=use_case.approved_until,
        decided_at=now,
    )
    session.add(decision)
    if review.paused_at is not None:
        review.paused_seconds += int((now - review.paused_at).total_seconds())
        review.paused_at = None
    review.status, review.closed_at = "decided", now
    _touch(use_case)
    session.flush()


# --- Triage and tasks ---------------------------------------------------------------------


def triage(
    session: Session,
    principal: Principal,
    review: Review,
    *,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
    reason: str = "",
) -> Review:
    """Confirm the reviews the rules require, or adjust them with a reason, and start them."""
    use_case = subject_of(session, review)
    if not principal.governs:
        raise PermissionDenied("Only governance can triage a request.")
    _not_own(session, principal, use_case, "triage")
    if review.status != "triage":
        raise Conflict("This review has already been triaged.")
    add, remove = list(dict.fromkeys(add)), list(dict.fromkeys(remove))
    known = vocab.keys(session, "review_functions")
    existing = {task.review_function: task for task in tasks_of(session, review)}
    errors = {}
    if any(function not in known for function in add):
        errors["add"] = "Choose from the review functions."
    if any(function not in existing for function in remove):
        errors["remove"] = "That review is not required here."
    if (add or remove) and len(reason.strip()) < 10:
        errors["reason"] = "Say why you are changing what the rules require."
    if errors:
        raise Invalid("The triage was not saved.", errors)
    with audit.operation(session, "review.triage", review=review.ref):
        for function in remove:
            existing[function].status = "waived"
            existing[function].notes = f"Not required: {reason.strip()}"
            existing[function].completed_by = principal.account_id
            existing[function].completed_at = utc_now()
        for function in add:
            if function not in existing:
                session.add(
                    ReviewTask(
                        review_id=review.id,
                        review_function=function,
                        status="pending",
                        required_by=f"Added at triage: {reason.strip()}",
                        recommended_conditions=[],
                        due_on=review.due_on,
                    )
                )
        review.status = "in_review"
        session.flush()
        href = f"/reviews?open={review.ref}"
        for task in tasks_of(session, review):
            if task.status == "pending":
                label = vocab.labels(session, "review_functions").get(
                    task.review_function, task.review_function
                )
                notify(
                    session,
                    holders(session, roles.REVIEWER, task.review_function)
                    - requester_ids(session, use_case),
                    "task",
                    f"{label} review needed: {use_case.name}",
                    href,
                    skip=principal.account_id,
                )
        _settle(session, review)
        session.flush()
    return review


def _task(session: Session, review: Review, task_id: int) -> ReviewTask:
    task = session.get(ReviewTask, task_id)
    if task is None or task.review_id != review.id:
        raise NotFound("There is no such review task.")
    return task


def claim(session: Session, principal: Principal, review: Review, task_id: int) -> ReviewTask:
    task = _task(session, review, task_id)
    use_case = subject_of(session, review)
    if not principal.reviews or not (
        principal.governs or _reviews_function(principal, task.review_function)
    ):
        raise PermissionDenied("You do not review for this function.")
    _not_own(session, principal, use_case, "review")
    if task.status != "pending":
        raise Conflict("This task is already finished.")
    with audit.operation(session, "review.claim", review=review.ref):
        task.assignee_id = principal.account_id
        session.flush()
    return task


def assign(
    session: Session, principal: Principal, review: Review, task_id: int, account_id: int | None
) -> ReviewTask:
    task = _task(session, review, task_id)
    use_case = subject_of(session, review)
    if not principal.governs:
        raise PermissionDenied("Only governance can assign a review task.")
    if task.status != "pending":
        raise Conflict("This task is already finished.")
    if account_id is not None:
        if account_id not in holders(session, roles.REVIEWER, task.review_function) | holders(
            session, roles.GOVERNANCE
        ):
            raise Invalid(
                "The task was not assigned.",
                {"account_id": "Choose someone who reviews for this function."},
            )
        if account_id in requester_ids(session, use_case):
            raise Invalid(
                "The task was not assigned.",
                {"account_id": "They cannot review their own request."},
            )
    with audit.operation(session, "review.assign", review=review.ref):
        task.assignee_id = account_id
        session.flush()
    if account_id is not None:
        notify(
            session,
            [account_id],
            "task",
            f"A review was assigned to you: {use_case.name}",
            f"/reviews?open={review.ref}",
            skip=principal.account_id,
        )
    return task


def _clean_conditions(
    session: Session, review: Review, given: Iterable[Mapping[str, Any]], *, need_due: bool
) -> list[dict[str, Any]]:
    rules = session.get(RuleSet, review.rule_set_id)
    assert rules is not None
    templates = routing.templates_by_key(rules.definition)
    cleaned: list[dict[str, Any]] = []
    for index, item in enumerate(given):
        key = item.get("template_key") or None
        template = templates.get(key) if key else None
        text = str(item.get("text") or (template or {}).get("text") or "").strip()
        kind = item.get("kind") or (template or {}).get("kind") or "ongoing"
        where = f"conditions[{index}]"
        if not text:
            raise Invalid("The conditions are not valid.", {where: "Write what is required."})
        if kind not in routing.CONDITION_KINDS:
            raise Invalid(
                "The conditions are not valid.",
                {where: "A condition is before use, by a date, or ongoing."},
            )
        due = item.get("due_on")
        if isinstance(due, str) and due:
            try:
                due = date.fromisoformat(due)
            except ValueError as exc:
                raise Invalid(
                    "The conditions are not valid.", {where: "Give the date as a date."}
                ) from exc
        elif not due and template and template.get("due_days"):
            due = working_days_from(today(), template["due_days"])
        if kind == "by_date" and not due and need_due:
            raise Invalid("The conditions are not valid.", {where: "Say by when."})
        cleaned.append(
            {
                "template_key": key if template else None,
                "text": text,
                "kind": kind,
                "due_on": due or None,
                "owner_id": item.get("owner_id"),
            }
        )
    return cleaned


def complete_task(
    session: Session,
    principal: Principal,
    review: Review,
    task_id: int,
    *,
    finding: str,
    notes: str = "",
    conditions: Iterable[Mapping[str, Any]] = (),
) -> ReviewTask:
    """Record a reviewer's finding. An objection, or conditions, need an explanation."""
    task = _task(session, review, task_id)
    use_case = subject_of(session, review)
    if not principal.reviews or not (
        principal.governs or _reviews_function(principal, task.review_function)
    ):
        raise PermissionDenied("You do not review for this function.")
    _not_own(session, principal, use_case, "review")
    if review.status == "triage":
        raise Conflict("This request has not been triaged yet.")
    if review.status not in OPEN or task.status != "pending":
        raise Conflict("This task is already finished.")
    errors = {}
    if finding not in FINDING_WORDS:
        errors["finding"] = "Choose a finding."
    proposed = _clean_conditions(session, review, conditions, need_due=False)
    if finding == "conditions" and not proposed:
        errors["conditions"] = "Say which conditions you recommend."
    if finding in ("conditions", "objection") and len(notes.strip()) < 10:
        errors["notes"] = "Explain the finding, so that whoever decides can weigh it."
    if errors:
        raise Invalid("The finding was not recorded.", errors)
    with audit.operation(session, "review.finding", review=review.ref):
        task.status = "completed"
        task.finding = finding
        task.notes = notes.strip() or None
        task.recommended_conditions = (
            [{**c, "due_on": c["due_on"].isoformat() if c["due_on"] else None} for c in proposed]
            if finding == "conditions"
            else []
        )
        task.assignee_id = task.assignee_id or principal.account_id
        task.completed_by = principal.account_id
        task.completed_at = utc_now()
        session.flush()
        _settle(session, review)
        session.flush()
    return task


# --- Discussion ---------------------------------------------------------------------------


def comment(
    session: Session,
    principal: Principal,
    review: Review,
    body: str,
    *,
    visibility: str = "internal",
    question: bool = False,
) -> Comment:
    """Add to the discussion. A question to the requester stops the clock until they answer."""
    use_case = subject_of(session, review)
    body = body.strip()
    if not body:
        raise Invalid("The comment was not added.", {"body": "Write something first."})
    if len(body) > 10_000:
        raise Invalid("The comment was not added.", {"body": "Keep it to 10,000 characters."})
    requester = is_requester(session, principal, use_case)
    # Reading a review is not taking part in it: an auditor reads everything and says nothing.
    insider = sees_internal(session, principal, review) and principal.reviews
    if not requester and not insider:
        raise PermissionDenied("You are not part of this review.")
    if requester:
        visibility, question = "requester", False  # whatever they asked for, it is for all to see
    if visibility not in ("requester", "internal"):
        raise Invalid("The comment was not added.", {"visibility": "Say who may see it."})
    if question:
        visibility = "requester"
        if review.status not in OPEN:
            raise Conflict("This review is closed.")
    href = f"/reviews?open={review.ref}"
    with audit.operation(session, "review.comment", review=review.ref):
        entry = Comment(
            subject_type="review",
            subject_id=review.id,
            author_id=principal.account_id,
            body=body,
            visibility=visibility,
            is_question=question,
            created_at=utc_now(),
        )
        session.add(entry)
        if question:
            _pause(session, review, use_case)
            notify(
                session,
                requester_ids(session, use_case),
                "question",
                f"A question about your request: {use_case.name}",
                f"/use-cases/{use_case.ref}",
                skip=principal.account_id,
            )
        elif requester:
            if review.status == "with_requester":
                _resume(session, review, use_case)
            notify(
                session,
                _reviewing_side(session, review),
                "reply",
                f"The requester replied about {use_case.name}",
                href,
                skip=principal.account_id,
            )
        elif visibility == "requester":
            notify(
                session,
                requester_ids(session, use_case),
                "comment",
                f"A note about your request: {use_case.name}",
                f"/use-cases/{use_case.ref}",
                skip=principal.account_id,
            )
        session.flush()
    return entry


# --- Decisions ----------------------------------------------------------------------------


def decide(
    session: Session,
    principal: Principal,
    review: Review,
    *,
    outcome: str,
    rationale: str,
    conditions: Iterable[Mapping[str, Any]] = (),
    at_session: str | None = None,
) -> Decision:
    """Approve, decline, or return a request. A rationale is always required. ``at_session``
    names the committee session the decision was made in, if it was made in one."""
    meeting_id: int | None = None
    if at_session:
        from govwren.review import sessions

        meeting_id = sessions.for_decision(session, review, at_session)
    use_case = subject_of(session, review)
    if not principal.governs:
        raise PermissionDenied("Only governance can decide a request.")
    _not_own(session, principal, use_case, "decide")
    if review.status not in OPEN:
        raise Conflict("This review has already been decided.")
    rationale = rationale.strip()
    errors = {}
    if outcome not in ("approved", "declined", "returned"):
        errors["outcome"] = "Approve, decline, or return the request."
    if len(rationale) < 10:
        errors["rationale"] = "Give the reason for the decision. It is shown to the requester."
    if errors:
        raise Invalid("The decision was not recorded.", errors)
    tasks = tasks_of(session, review)
    objected = any(task.finding == "objection" for task in tasks)
    assessment = latest_assessment(session, use_case)
    rules = session.get(RuleSet, review.rule_set_id)
    assert rules is not None
    cleaned: list[dict[str, Any]] = []
    until: date | None = None
    if outcome == "approved":
        if review.status == "triage":
            raise Conflict("Triage this request before deciding it.")
        if review.status == "with_requester":
            raise Conflict(
                "This request is back with the requester. Wait for their reply, or decline it."
            )
        waiting = [task for task in tasks if task.status == "pending"]
        if waiting:
            count = "1 review task is" if len(waiting) == 1 else f"{len(waiting)} review tasks are"
            raise Conflict(f"{count} not finished yet.")
        if assessment is not None and assessment.stops:
            raise Conflict(
                "This is a prohibited use and cannot be approved: "
                + " ".join(stop["reason"] for stop in assessment.stops)
            )
        if needs_acceptance(review):
            asked = acceptance_of(session, review)
            if asked is None or asked.status != "accepted":
                raise Conflict(
                    "The rules require a named person to accept the risk before this is "
                    "approved. "
                    + (
                        "Ask someone to accept it."
                        if asked is None or asked.status == "declined"
                        else "The person asked has not answered yet."
                    )
                )
        cleaned = _clean_conditions(session, review, conditions, need_due=True)
        owner_default = _accountable(session, use_case)
        for item in cleaned:
            owner = item["owner_id"] or owner_default
            if owner is None or session.get(Account, owner) is None:
                raise Invalid(
                    "The conditions are not valid.",
                    {"conditions": "Every condition needs an owner."},
                )
            item["owner_id"] = owner
        until = add_months(today(), review.routing.get("cadence_months") or 12)
        if review.kind in ("change", "incident") and use_case.approved_until is not None:
            until = use_case.approved_until  # these do not restart the approval period
    final = "approved_with_conditions" if outcome == "approved" and cleaned else outcome
    now = utc_now()
    with audit.operation(session, "review.decide", review=review.ref):
        decision = Decision(
            review_id=review.id,
            outcome=final,
            rationale=rationale,
            decided_by=principal.account_id,
            authority=review.authority,
            by_rule=None,
            over_objection=objected and outcome == "approved",
            tier=use_case.tier,
            approved_until=until,
            decided_at=now,
            session_id=meeting_id,
        )
        session.add(decision)
        session.flush()
        if outcome == "returned":
            session.add(
                Comment(
                    subject_type="review",
                    subject_id=review.id,
                    author_id=principal.account_id,
                    body=rationale,
                    visibility="requester",
                    is_question=True,
                    created_at=now,
                )
            )
            _pause(session, review, use_case)
        else:
            standing = _open_keys(session, use_case)
            for item in cleaned:
                if item.get("template_key") in standing:
                    continue  # it was set by an earlier decision and still stands
                session.add(
                    Condition(
                        decision_id=decision.id,
                        subject_type="use_case",
                        subject_id=use_case.id,
                        status="open",
                        **item,
                    )
                )
            if review.status == "with_requester" and review.paused_at is not None:
                review.paused_seconds += int((now - review.paused_at).total_seconds())
                review.paused_at = None
            review.status = "decided"
            review.closed_at = now
            if outcome == "approved":
                use_case.approved_until = until
                use_case.next_review_on = until
            elif review.kind != "initial":
                use_case.next_review_on = None  # the approval has ended; nothing is due
                _drop_draft(session, use_case)
            if review.kind != "initial":
                # Whatever suspended it, this decision is now what its standing rests on.
                for held in session.scalars(
                    select(IncidentRecord).where(
                        IncidentRecord.subject_type == "use_case",
                        IncidentRecord.subject_id == use_case.id,
                        IncidentRecord.suspended.is_(True),
                    )
                ):
                    held.suspended = False
            _touch(use_case, final)
        session.flush()
    words = {
        "approved": "was approved",
        "approved_with_conditions": "was approved, with conditions",
        "declined": "was declined",
        "returned": "needs something from you",
    }[final]
    notify(
        session,
        requester_ids(session, use_case),
        "decision",
        f"Your request {words}: {use_case.name}",
        f"/use-cases/{use_case.ref}",
        skip=principal.account_id,
    )
    return decision


def withdraw(
    session: Session, principal: Principal, review: Review, reason: str = ""
) -> Decision | None:
    """The requester takes the request back."""
    use_case = subject_of(session, review)
    if not is_requester(session, principal, use_case) and not principal.governs:
        raise PermissionDenied("Only the requester can withdraw a request.")
    if review.status not in OPEN:
        raise Conflict("This review has already been decided.")
    if review.kind == "change" and review.status == "with_requester" and not review.resume_status:
        # A change that was started and never submitted is simply dropped.
        with audit.operation(session, "review.abandon", review=review.ref):
            review.status, review.closed_at, review.paused_at = "cancelled", utc_now(), None
            _drop_draft(session, use_case)
            _touch(use_case)
            session.flush()
        return None
    if review.kind != "initial":
        raise Conflict(
            "A review of something already approved cannot be withdrawn. If the use has "
            "ended, retire it."
        )
    now = utc_now()
    with audit.operation(session, "review.withdraw", review=review.ref):
        decision = Decision(
            review_id=review.id,
            outcome="withdrawn",
            rationale=reason.strip() or "Withdrawn by the requester.",
            decided_by=principal.account_id,
            authority="requester",
            over_objection=False,
            tier=use_case.tier,
            decided_at=now,
        )
        session.add(decision)
        for task in tasks_of(session, review):
            if task.status == "pending":
                task.status = "waived"
                task.notes = "The request was withdrawn."
                task.completed_at = now
        review.status = "decided"
        review.closed_at = now
        review.paused_at = None
        _touch(use_case, "withdrawn")
        session.flush()
    notify(
        session,
        _reviewing_side(session, review),
        "withdrawn",
        f"Withdrawn: {use_case.name}",
        f"/reviews?open={review.ref}",
        skip=principal.account_id,
    )
    return decision


def close_condition(
    session: Session, principal: Principal, condition_id: int, *, status: str, note: str
) -> Condition:
    """Mark a condition as met, or waive it. Either needs a note saying how or why."""
    condition = session.get(Condition, condition_id)
    use_case = session.get(UseCase, condition.subject_id) if condition is not None else None
    if (
        condition is None
        or use_case is None
        or access.sight(session, principal, USE_CASE, use_case) != access.FULL
    ):
        raise NotFound("There is no such condition.")
    if condition.status != "open":
        raise Conflict("This condition is already closed.")
    if status not in ("met", "waived"):
        raise Invalid("The condition was not changed.", {"status": "Mark it as met, or waive it."})
    if status == "waived" and not principal.governs:
        raise PermissionDenied("Only governance can waive a condition.")
    if status == "met" and not (
        principal.governs or access.can_edit(session, principal, USE_CASE, use_case)
    ):
        raise PermissionDenied(
            "Only the record's owners, its unit's stewards, or governance can close a condition."
        )
    if len(note.strip()) < 10:
        raise Invalid(
            "The condition was not changed.", {"note": "Say how it was met, or why it is waived."}
        )
    with audit.operation(session, "condition.close"):
        condition.status = status
        condition.note = note.strip()
        condition.closed_by = principal.account_id
        condition.closed_at = utc_now()
        session.flush()
    return condition


def conditions_of(session: Session, use_case: UseCase) -> list[Condition]:
    return list(
        session.scalars(
            select(Condition)
            .where(Condition.subject_type == "use_case", Condition.subject_id == use_case.id)
            .order_by(Condition.id)
        )
    )


def in_effect(session: Session, use_case: UseCase) -> bool:
    """An approval takes effect once every before-use condition is met or waived."""
    if use_case.status not in APPROVED:
        return False
    return not any(
        c.kind == "before_use" and c.status == "open" for c in conditions_of(session, use_case)
    )


def approve_under_catalog(
    session: Session, principal: Principal, use_case: UseCase, system_name: str
) -> Review:
    """Record the approval of a use that fits what an approved system is already permitted
    for. The rule that approves it is the catalog entry itself."""
    rules = current_rules(session)
    answers = {
        "data_class": use_case.data_class,
        "data_categories": list(use_case.data_categories or []),
    }
    route = routing.route(rules.definition, 1, answers)
    route = {
        **route,
        "require": [],
        "auto_approve": f"Registered under the catalog terms of {system_name}",
    }
    review = Review(
        ref=next_ref(session, "RV"),
        subject_type="use_case",
        subject_id=use_case.id,
        kind="initial",
        status="triage",
        tier_at_open=1,
        rule_set_id=rules.id,
        authority="governance",
        routing=route,
        opened_by=principal.account_id,
        opened_at=utc_now(),
        paused_seconds=0,
    )
    session.add(review)
    session.flush()
    _approve_by_rule(session, review, use_case, rules, route)
    return review
