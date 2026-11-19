"""What falls due: periodic reviews opened ahead of an approval's end, approvals that run
out, and reminders about work that is nearly late or late.

Each function looks at the whole inventory, does what is due, and can be run again at any
time without doing it twice. Nothing here changes a standing silently: every change is an
event with a reason, and the people it affects are told.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access import roles
from govwren.core.clock import today
from govwren.db.models import Condition, Reminder, Review, ReviewTask, UseCase
from govwren.events import audit
from govwren.review import service as review

LEAD_DAYS = 60  # how long before an approval ends its periodic review opens
SOON_DAYS = 14  # when "nearly due" starts for owners
TASK_SOON_DAYS = 2  # and for reviewers, whose tasks are short


def open_periodic_reviews(session: Session) -> int:
    """Open a periodic review for every approval that ends within the lead time, or has
    ended, and has no review in progress."""
    horizon = today() + timedelta(days=LEAD_DAYS)
    due = session.scalars(
        select(UseCase)
        .where(
            UseCase.status.in_((*review.APPROVED, "lapsed")),
            UseCase.next_review_on.is_not(None),
            UseCase.next_review_on <= horizon,
        )
        .order_by(UseCase.next_review_on, UseCase.id)
    ).all()
    opened = 0
    for use_case in due:
        if review.open_review(session, use_case) is None:
            review.open_periodic(session, use_case)
            opened += 1
    return opened


def lapse_approvals(session: Session) -> int:
    """Mark as lapsed every approval whose end date has passed without being renewed."""
    now = today()
    ended = session.scalars(
        select(UseCase)
        .where(
            UseCase.status.in_(review.APPROVED),
            UseCase.approved_until.is_not(None),
            UseCase.approved_until < now,
        )
        .order_by(UseCase.id)
    ).all()
    for use_case in ended:
        reason = (
            f"The approval ended on {use_case.approved_until:%Y-%m-%d} and no periodic review "
            "had renewed it."
        )
        with audit.operation(session, "use_case.lapse", reason=reason):
            use_case.status = "lapsed"
            use_case.version += 1
            session.flush()
        review.notify(
            session,
            review.requester_ids(session, use_case)
            | review.stewards_of(session, use_case.org_unit_id),
            "lapsed",
            f"Approval lapsed: {use_case.name}",
            f"/use-cases/{use_case.ref}",
        )
    return len(ended)


class _Sent:
    """Which reminders have gone, so that each is sent once."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.seen = {
            (kind, subject, stage)
            for kind, subject, stage in session.execute(
                select(Reminder.subject_type, Reminder.subject_id, Reminder.stage)
            )
        }

    def first(self, subject_type: str, subject_id: int, stage: str) -> bool:
        """True the first time a reminder is asked for, and never again for the same thing."""
        key = (subject_type, subject_id, stage)
        if key in self.seen:
            return False
        self.seen.add(key)
        self.session.add(
            Reminder(subject_type=subject_type, subject_id=subject_id, stage=stage, sent_on=today())
        )
        return True


def _stage(due: date | None, soon_days: int) -> str | None:
    if due is None:
        return None
    left = (due - today()).days
    return "overdue" if left < 0 else "soon" if left <= soon_days else None


def _when(due: date) -> str:
    return f"{due:%b} {due.day}"


def send_reminders(session: Session) -> int:
    """Remind whoever a piece of work is waiting on when it is nearly due, and tell the next
    person up when it is late: governance for a review task, the unit's steward for an
    owner's work."""
    sent = 0
    once = _Sent(session).first

    def tell(ids: Iterable[int], kind: str, title: str, href: str) -> None:
        nonlocal sent
        people = set(ids)
        if people:
            review.notify(session, people, kind, title, href)
            sent += len(people)

    governance = review.holders(session, roles.GOVERNANCE)

    tasks = session.execute(
        select(ReviewTask, Review)
        .join(Review, Review.id == ReviewTask.review_id)
        .where(
            ReviewTask.status == "pending",
            ReviewTask.due_on.is_not(None),
            Review.status == "in_review",
        )
        .order_by(ReviewTask.id)
    ).all()
    for task, its_review in tasks:
        stage = _stage(task.due_on, TASK_SOON_DAYS)
        if stage is None or not once("review_task", task.id, stage):
            continue
        use_case = review.subject_of(session, its_review)
        label = task.review_function.replace("_", " ").replace("-", " ").capitalize()
        href = f"/reviews?open={its_review.ref}"
        assigned = (
            {task.assignee_id}
            if task.assignee_id is not None
            else review.holders(session, roles.REVIEWER, task.review_function)
        )
        requesters = review.requester_ids(session, use_case)
        if stage == "soon":
            tell(
                assigned - requesters,
                "reminder",
                f"Due {_when(task.due_on)}: {label} review of {use_case.name}",
                href,
            )
        else:
            tell(
                (assigned | governance) - requesters,
                "overdue",
                f"Overdue: {label} review of {use_case.name}",
                href,
            )

    waiting = session.scalars(
        select(Review)
        .where(
            Review.kind != "initial",
            Review.status == "with_requester",
            Review.due_on.is_not(None),
        )
        .order_by(Review.id)
    ).all()
    for its_review in waiting:
        stage = _stage(its_review.due_on, SOON_DAYS)
        if stage is None or not once("review", its_review.id, stage):
            continue
        use_case = review.subject_of(session, its_review)
        owners = review.requester_ids(session, use_case)
        href = f"/use-cases/{use_case.ref}/request"
        if stage == "soon":
            tell(
                owners,
                "reminder",
                f"Approval ends {_when(its_review.due_on)}: confirm {use_case.name}",
                href,
            )
        else:
            stewards = review.stewards_of(session, use_case.org_unit_id)
            tell(
                owners | stewards,
                "overdue",
                f"Overdue: periodic review of {use_case.name} is waiting on its owner",
                href,
            )

    conditions = session.scalars(
        select(Condition)
        .where(Condition.status == "open", Condition.due_on.is_not(None))
        .order_by(Condition.id)
    ).all()
    for condition in conditions:
        stage = _stage(condition.due_on, SOON_DAYS)
        if stage is None or not once("condition", condition.id, stage):
            continue
        use_case = session.get(UseCase, condition.subject_id)
        if use_case is None or use_case.status not in review.APPROVED:
            continue
        owner = {condition.owner_id} if condition.owner_id is not None else set()
        href = f"/use-cases/{use_case.ref}"
        if stage == "soon":
            tell(
                owner,
                "reminder",
                f"Due {_when(condition.due_on)}: a condition on {use_case.name}",
                href,
            )
        else:
            stewards = review.stewards_of(session, use_case.org_unit_id)
            tell(owner | stewards, "overdue", f"Overdue: a condition on {use_case.name}", href)
    session.flush()
    from govwren.oversight import campaigns

    return sent + campaigns.remind(session)


def run_all(session: Session) -> dict[str, int]:
    """Everything that depends on the date, in the order that makes sense for one day."""
    return {
        "lapsed": lapse_approvals(session),
        "periodic_reviews": open_periodic_reviews(session),
        "reminders": send_reminders(session),
    }
