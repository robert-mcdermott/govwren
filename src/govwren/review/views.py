"""What each person sees of a review, the queue, their own work, and their notices."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.db.models import (
    Account,
    Comment,
    Condition,
    Decision,
    IntakeDraft,
    Notification,
    RecordOwner,
    Review,
    ReviewTask,
    RuleSet,
    UseCase,
)
from govwren.intake import service as intake
from govwren.inventory import access, records
from govwren.inventory.registry import USE_CASE
from govwren.program import vocab
from govwren.review import routing, service

WAITING = {
    "triage": "governance, to triage it",
    "in_review": "reviewers",
    "with_requester": "the requester",
    "ready": "governance, to decide it",
    "decided": "nobody",
    "cancelled": "nobody",
}


def _names(session: Session, ids: set[int | None]) -> dict[int, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(wanted))
        ).all()
    )  # type: ignore[arg-type]


def _overdue(due: date | None, open_: bool) -> bool:
    return bool(open_ and due and due < today())


def condition_view(condition: Condition, names: dict[int, str]) -> dict[str, Any]:
    return {
        "id": condition.id,
        "text": condition.text,
        "kind": condition.kind,
        "owner": names.get(condition.owner_id or 0),
        "owner_id": condition.owner_id,
        "due_on": condition.due_on,
        "status": condition.status,
        "note": condition.note,
        "overdue": _overdue(condition.due_on, condition.status == "open"),
    }


def decision_view(decision: Decision, names: dict[int, str]) -> dict[str, Any]:
    return {
        "outcome": decision.outcome,
        "rationale": decision.rationale,
        "decided_by": names.get(decision.decided_by or 0),
        "by_rule": decision.by_rule,
        "authority": decision.authority,
        "over_objection": decision.over_objection,
        "approved_until": decision.approved_until,
        "decided_at": decision.decided_at,
    }


def _days(seconds: float) -> float:
    return round(seconds / 86400, 1)


def _subject(session: Session, principal: Principal, use_case: UseCase) -> dict[str, Any]:
    """The request under review. A reviewer sees all of it, whatever its unit, because they
    cannot review what they cannot read."""
    return records.detail(session, principal, USE_CASE, use_case, sight=access.FULL)


def packet(session: Session, principal: Principal, review: Review) -> dict[str, Any]:
    """Everything about a review that this person may see. A requester sees where it stands,
    what was asked of them, and what was decided; never findings or reviewers' own notes."""
    use_case = service.subject_of(session, review)
    internal = service.sees_internal(session, principal, review)
    requester = service.is_requester(session, principal, use_case)
    tasks = service.tasks_of(session, review)
    comments = session.scalars(
        select(Comment)
        .where(Comment.subject_type == "review", Comment.subject_id == review.id)
        .order_by(Comment.id)
    ).all()
    decisions = session.scalars(
        select(Decision).where(Decision.review_id == review.id).order_by(Decision.id)
    ).all()
    conditions = [
        c
        for c in service.conditions_of(session, use_case)
        if c.decision_id in {d.id for d in decisions}
    ]
    names = _names(
        session,
        {t.assignee_id for t in tasks}
        | {c.author_id for c in comments}
        | {d.decided_by for d in decisions}
        | {c.owner_id for c in conditions}
        | {review.opened_by},
    )
    functions = vocab.labels(session, "review_functions")
    open_ = review.status in service.OPEN
    end = review.closed_at or utc_now()
    paused = review.paused_seconds + (
        (utc_now() - review.paused_at).total_seconds() if review.paused_at and open_ else 0
    )
    rules = session.get(RuleSet, review.rule_set_id)
    templates = list(rules.definition.get("condition_templates", [])) if rules else []
    by_key = routing.templates_by_key(rules.definition) if rules else {}
    may_review = principal.reviews and not requester
    can = {
        "triage": principal.governs and not requester and review.status == "triage",
        "decide": principal.governs and not requester and open_,
        "comment_internal": internal and principal.reviews,
        "ask": internal and principal.reviews and open_,
        "reply": requester,
        "withdraw": (requester or principal.governs) and open_,
        "assign": principal.governs and open_,
    }
    task_views = []
    for task in tasks:
        mine = (
            may_review
            and task.status == "pending"
            and review.status in ("in_review", "ready", "with_requester")
            and (principal.governs or service._reviews_function(principal, task.review_function))
        )
        view: dict[str, Any] = {
            "id": task.id,
            "function": task.review_function,
            "label": functions.get(task.review_function, task.review_function),
            "status": task.status,
            "due_on": task.due_on,
            "overdue": _overdue(task.due_on, task.status == "pending" and open_),
            "completed_at": task.completed_at,
        }
        if internal:
            view.update(
                assignee=names.get(task.assignee_id or 0),
                assignee_id=task.assignee_id,
                required_by=task.required_by,
                finding=task.finding,
                notes=task.notes,
                recommended_conditions=task.recommended_conditions,
                can_complete=bool(mine),
                can_claim=bool(mine) and task.assignee_id != principal.account_id,
            )
        task_views.append(view)
    proposed: list[dict[str, Any]] = []
    if internal:
        for key in review.routing.get("conditions", []):
            if key in by_key:
                proposed.append(
                    {
                        "template_key": key,
                        "text": by_key[key]["text"],
                        "kind": by_key[key].get("kind", "ongoing"),
                        "from": "The rules",
                    }
                )
        for task in tasks:
            for item in task.recommended_conditions or []:
                if all(p["text"] != item["text"] for p in proposed):
                    proposed.append(
                        {**item, "from": f"{functions.get(task.review_function, 'A')} review"}
                    )
    return {
        "ref": review.ref,
        "kind": review.kind,
        "status": review.status,
        "waiting_on": WAITING[review.status],
        "authority": review.authority,
        "tier_at_open": review.tier_at_open,
        "opened_at": review.opened_at,
        "opened_by": names.get(review.opened_by or 0),
        "due_on": review.due_on,
        "overdue": _overdue(review.due_on, open_),
        "closed_at": review.closed_at,
        "by_rule": any(d.by_rule for d in decisions),
        "time": {
            "with_reviewers_days": _days(
                max(0.0, (end - review.opened_at).total_seconds() - paused)
            ),
            "with_requester_days": _days(paused),
        },
        "subject": _subject(session, principal, use_case),
        "assessment": intake.assessment_view(session, service.latest_assessment(session, use_case)),
        "routing": {
            "rules": review.routing.get("rules", []),
            "require": review.routing.get("require", []),
        }
        if internal
        else None,
        "tasks": task_views,
        "comments": [
            {
                "id": c.id,
                "author": names.get(c.author_id or 0, "GovWren"),
                "mine": c.author_id == principal.account_id,
                "body": c.body,
                "visibility": c.visibility,
                "is_question": c.is_question,
                "created_at": c.created_at,
            }
            for c in comments
            if internal or c.visibility == "requester"
        ],
        "decisions": [decision_view(d, names) for d in decisions],
        "conditions": [condition_view(c, names) for c in conditions],
        "proposed_conditions": proposed,
        "condition_templates": templates if internal else [],
        "review_functions": [{"key": k, "label": v} for k, v in functions.items()]
        if can["triage"]
        else [],
        "internal": internal,
        "can": can,
    }


def _visible_reviews(session: Session, principal: Principal, *, open_only: bool) -> list[Review]:
    statement = select(Review).order_by(Review.due_on.is_(None), Review.due_on, Review.id)
    if open_only:
        statement = statement.where(Review.status.in_(service.OPEN))
    reviews = list(session.scalars(statement))
    if principal.reads_all:
        return reviews
    return [review for review in reviews if service.can_see(session, principal, review)]


def queue(session: Session, principal: Principal, *, scope: str = "open") -> list[dict[str, Any]]:
    """Reviews this person has a part in, soonest due first."""
    reviews = _visible_reviews(session, principal, open_only=scope != "all")
    if not reviews:
        return []
    subjects = {
        u.id: u
        for u in session.scalars(
            select(UseCase).where(UseCase.id.in_({r.subject_id for r in reviews}))
        )
    }
    tasks: dict[int, list[ReviewTask]] = {}
    for task in session.scalars(
        select(ReviewTask).where(ReviewTask.review_id.in_({r.id for r in reviews}))
    ):
        tasks.setdefault(task.review_id, []).append(task)
    functions = vocab.labels(session, "review_functions")
    out = []
    for review in reviews:
        use_case = subjects[review.subject_id]
        requester = service.is_requester(session, principal, use_case)
        pending = [t for t in tasks.get(review.id, []) if t.status == "pending"]
        mine = [
            functions.get(t.review_function, t.review_function)
            for t in pending
            if principal.reviews
            and not requester
            and review.status != "triage"
            and (principal.governs or service._reviews_function(principal, t.review_function))
        ]
        open_ = review.status in service.OPEN
        out.append(
            {
                "ref": review.ref,
                "status": review.status,
                "waiting_on": WAITING[review.status],
                "subject": {
                    "ref": use_case.ref,
                    "name": use_case.name,
                    "org_unit_id": use_case.org_unit_id,
                },
                "tier": use_case.tier,
                "due_on": review.due_on,
                "overdue": _overdue(review.due_on, open_),
                "opened_at": review.opened_at,
                "tasks_done": len(tasks.get(review.id, [])) - len(pending),
                "tasks_total": len(tasks.get(review.id, [])),
                "my_tasks": mine,
                "needs_me": bool(mine)
                or (principal.governs and not requester and review.status in ("triage", "ready")),
            }
        )
    return out


def my_work(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """What is waiting on this person, overdue first: one list for every kind of thing."""
    items: list[dict[str, Any]] = []
    me = principal.account_id

    def add(kind: str, title: str, detail: str, href: str, due: date | None = None) -> None:
        items.append(
            {
                "kind": kind,
                "title": title,
                "detail": detail,
                "href": href,
                "due_on": due,
                "overdue": bool(due and due < today()),
            }
        )

    for card in queue(session, principal):
        name, href = card["subject"]["name"], f"/reviews?open={card['ref']}"
        if card["status"] == "triage" and card["needs_me"]:
            add(
                "triage",
                f"Triage: {name}",
                "A new request, waiting to be routed",
                href,
                card["due_on"],
            )
        elif card["status"] == "ready" and card["needs_me"] and not card["my_tasks"]:
            add("decide", f"Decide: {name}", "Every review is finished", href, card["due_on"])
        for function in card["my_tasks"]:
            add("task", f"{function} review: {name}", "Record your finding", href, card["due_on"])

    if me is not None:
        owned = select(RecordOwner.record_id).where(
            RecordOwner.record_type == "use_case",
            RecordOwner.account_id == me,
            RecordOwner.kind != "contact",
        )
        mine = list(
            session.scalars(
                select(UseCase).where((UseCase.created_by == me) | UseCase.id.in_(owned))
            )
        )
        drafts = set(session.scalars(select(IntakeDraft.use_case_id)))
        for use_case in mine:
            if use_case.status == "returned":
                add(
                    "question",
                    f"Answer a question: {use_case.name}",
                    "Governance needs something from you",
                    f"/use-cases/{use_case.ref}",
                )
            elif use_case.status == "draft" and use_case.id in drafts:
                add(
                    "draft",
                    f"Finish your request: {use_case.name}",
                    "Not submitted yet",
                    f"/use-cases/{use_case.ref}/request",
                )
        names = {u.id: u for u in mine}
        open_conditions = session.scalars(
            select(Condition)
            .where(Condition.owner_id == me, Condition.status == "open")
            .order_by(Condition.due_on)
        )
        for condition in open_conditions:
            use_case = names.get(condition.subject_id) or session.get(UseCase, condition.subject_id)
            if use_case is None or condition.kind == "ongoing":
                continue  # an ongoing condition is something to keep to, not something to finish
            add(
                "condition",
                condition.text,
                f"A condition on {use_case.name}",
                f"/use-cases/{use_case.ref}",
                condition.due_on,
            )
    items.sort(
        key=lambda item: (not item["overdue"], item["due_on"] is None, item["due_on"] or date.max)
    )
    return items


def review_summary(
    session: Session, principal: Principal, use_case: UseCase
) -> dict[str, Any] | None:
    """The latest review of a use case, as its page shows it."""
    if access.sight(session, principal, USE_CASE, use_case) != access.FULL:
        return None
    review = service.latest_review(session, use_case)
    if review is None:
        return None
    view = packet(session, principal, review)
    view.pop("subject", None)
    names = _names(session, {c.owner_id for c in service.conditions_of(session, use_case)})
    view["all_conditions"] = [
        condition_view(c, names) for c in service.conditions_of(session, use_case)
    ]
    view["in_effect"] = service.in_effect(session, use_case)
    view["can_close_conditions"] = principal.governs or access.can_edit(
        session, principal, USE_CASE, use_case
    )
    view["can_waive_conditions"] = principal.governs
    return view


def notifications(session: Session, principal: Principal, *, limit: int = 30) -> dict[str, Any]:
    rows = session.scalars(
        select(Notification)
        .where(Notification.account_id == principal.account_id)
        .order_by(Notification.id.desc())
        .limit(limit)
    ).all()
    unread = session.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.account_id == principal.account_id, Notification.read_at.is_(None))
    ).scalar_one()
    return {
        "unread": unread,
        "items": [
            {
                "id": n.id,
                "kind": n.kind,
                "title": n.title,
                "href": n.href,
                "created_at": n.created_at,
                "read": n.read_at is not None,
            }
            for n in rows
        ],
    }


def mark_read(session: Session, principal: Principal, ids: list[int] | None) -> None:
    statement = (
        update(Notification)
        .where(Notification.account_id == principal.account_id, Notification.read_at.is_(None))
        .values(read_at=utc_now())
    )
    if ids:
        statement = statement.where(Notification.id.in_(ids))
    session.execute(statement)
