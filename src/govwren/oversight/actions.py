"""Actions: what a named person must do by a date. One list holds them all: the corrective
actions that follow an incident, and the conditions that came with a decision."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Action, Condition, Incident, UseCase
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, USE_CASE
from govwren.review import service as review


def find(session: Session, ref: str) -> Action:
    action = session.scalars(select(Action).where(Action.ref == ref.strip().upper())).first()
    if action is None:
        raise NotFound(f"There is no action {ref}.")
    return action


def add(
    session: Session,
    principal: Principal,
    *,
    title: str,
    owner_id: int | None,
    due_on: date | None,
    detail: str = "",
    source: tuple[str, int] | None = None,
    subject: tuple[str, int] | None = None,
) -> Action:
    """Give someone something to do. Governance sets actions."""
    if not principal.governs:
        raise PermissionDenied("Only governance can set an action.")
    title, errors = title.strip(), {}
    if not 3 <= len(title) <= 300:
        errors["title"] = "Say what must be done."
    owner = session.get(Account, owner_id) if owner_id else None
    if owner is None or owner.status != "active":
        errors["owner_id"] = "Choose who will do it."
    if due_on is None or due_on < today():
        errors["due_on"] = "Choose the date it is due."
    if errors:
        raise Invalid("The action was not added.", errors)
    assert owner is not None
    with audit.operation(session, "action.add"):
        action = Action(
            ref=next_ref(session, "ACT"),
            title=title,
            detail=detail.strip() or None,
            source_type=source[0] if source else None,
            source_id=source[1] if source else None,
            subject_type=subject[0] if subject else None,
            subject_id=subject[1] if subject else None,
            owner_id=owner.id,
            due_on=due_on,
            status="open",
            created_by=principal.account_id,
            created_at=utc_now(),
        )
        session.add(action)
        session.flush()
    review.notify(
        session,
        [owner.id],
        "action",
        f"An action for you: {title}",
        "/actions",
        skip=principal.account_id,
    )
    return action


def close(
    session: Session, principal: Principal, action: Action, *, status: str, note: str = ""
) -> Action:
    """The owner says it is done, or governance cancels it."""
    if action.status != "open":
        raise Conflict("This action is already closed.")
    mine = action.owner_id == principal.account_id
    if status == "done" and not (mine or principal.governs):
        raise PermissionDenied("Only its owner or governance can close this action.")
    if status == "cancelled" and not principal.governs:
        raise PermissionDenied("Only governance can cancel an action.")
    note = note.strip()
    if status not in ("done", "cancelled") or len(note) < 5:
        raise Invalid(
            "The action was not closed.",
            {"note": "Say what was done." if status == "done" else "Say why it is not needed."},
        )
    with audit.operation(session, f"action.{status}"):
        action.status, action.note = status, note
        action.closed_by, action.closed_at = principal.account_id, utc_now()
        session.flush()
    if not mine or action.created_by not in (None, principal.account_id):
        review.notify(
            session,
            {action.created_by} - {None},
            "action",  # type: ignore[arg-type]
            f"Action {'done' if status == 'done' else 'cancelled'}: {action.title}",
            "/actions",
            skip=principal.account_id,
        )
    return action


def _source(session: Session, action: Action) -> dict[str, Any] | None:
    if action.source_type == "incident" and action.source_id:
        incident = session.get(Incident, action.source_id)
        if incident is not None:
            return {"label": f"Incident {incident.ref}", "href": f"/incidents/{incident.ref}"}
    return None


def _about(session: Session, kind: str | None, identifier: int | None) -> dict[str, Any] | None:
    record_type = TYPES.get(kind or "")
    record = session.get(record_type.model, identifier) if record_type and identifier else None
    if record is None or record_type is None:
        return None
    return {"ref": record.ref, "name": record.name, "href": f"/{record_type.path}/{record.ref}"}


def listing(
    session: Session, principal: Principal, *, scope: str = "mine", status: str = "open"
) -> list[dict[str, Any]]:
    """Everything someone must do, in one list: actions, and the conditions of decisions
    that have a date or must be met before use. ``scope`` is ``mine`` or ``all``; only those
    who see everything may ask for all."""
    everything = scope == "all" and principal.reads_all
    me = principal.account_id
    rows: list[dict[str, Any]] = []
    actions = select(Action)
    conditions = select(Condition).where(Condition.kind != "ongoing")
    if status == "open":
        actions = actions.where(Action.status == "open")
        conditions = conditions.where(Condition.status == "open")
    if not everything:
        actions = actions.where(Action.owner_id == me)
        conditions = conditions.where(Condition.owner_id == me)
    found_actions = session.scalars(actions).all()
    found_conditions = session.scalars(conditions).all()
    owners = {a.owner_id for a in found_actions} | {c.owner_id for c in found_conditions}
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(owners - {None} or {0}))
        ).all()  # type: ignore[arg-type]
    )
    now = today()
    for action in found_actions:
        rows.append(
            {
                "kind": "action",
                "id": action.ref,
                "title": action.title,
                "detail": action.detail,
                "about": _about(session, action.subject_type, action.subject_id),
                "source": _source(session, action),
                "owner": names.get(action.owner_id),
                "due_on": action.due_on,
                "status": action.status,
                "note": action.note,
                "overdue": action.status == "open" and bool(action.due_on and action.due_on < now),
                "can_close": action.status == "open"
                and (action.owner_id == me or principal.governs),
                "can_cancel": action.status == "open" and principal.governs,
            }
        )
    for condition in found_conditions:
        use_case = session.get(UseCase, condition.subject_id)
        if use_case is None or (status == "open" and use_case.status not in review.APPROVED):
            continue
        rows.append(
            {
                "kind": "condition",
                "id": condition.id,
                "title": condition.text,
                "detail": "Must be met before use" if condition.kind == "before_use" else None,
                "about": {
                    "ref": use_case.ref,
                    "name": use_case.name,
                    "href": f"/use-cases/{use_case.ref}",
                },
                "source": {
                    "label": "A condition of approval",
                    "href": f"/use-cases/{use_case.ref}",
                },
                "owner": names.get(condition.owner_id or 0),
                "due_on": condition.due_on,
                "status": {"met": "done", "waived": "cancelled"}.get(condition.status, "open"),
                "note": condition.note,
                "overdue": condition.status == "open"
                and bool(condition.due_on and condition.due_on < now),
                "can_close": condition.status == "open"
                and (principal.governs or access.can_edit(session, principal, USE_CASE, use_case)),
                "can_cancel": condition.status == "open" and principal.governs,
            }
        )
    rows.sort(
        key=lambda r: (
            r["status"] != "open",
            not r["overdue"],
            r["due_on"] is None,
            r["due_on"] or date.max,
            r["title"],
        )
    )
    return rows


def for_source(
    session: Session, principal: Principal, source: tuple[str, int]
) -> list[dict[str, Any]]:
    """The actions that came out of one incident, whoever owns them."""
    found = session.scalars(
        select(Action)
        .where(Action.source_type == source[0], Action.source_id == source[1])
        .order_by(Action.id)
    ).all()
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_({a.owner_id for a in found} or {0})
            )
        ).all()  # type: ignore[arg-type]
    )
    now = today()
    me = principal.account_id
    return [
        {
            "id": a.ref,
            "title": a.title,
            "owner": names.get(a.owner_id),
            "due_on": a.due_on,
            "status": a.status,
            "note": a.note,
            "overdue": a.status == "open" and bool(a.due_on and a.due_on < now),
            "can_close": a.status == "open" and (a.owner_id == me or principal.governs),
            "can_cancel": a.status == "open" and principal.governs,
        }
        for a in found
    ]
