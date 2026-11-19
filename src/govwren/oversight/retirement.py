"""Retiring a record: it stays in the inventory, with its history, marked as no longer in use."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.models import IntakeDraft, RecordOwner, ReviewTask
from govwren.events import audit
from govwren.inventory import access, links
from govwren.inventory.registry import TYPES, USE_CASE, VENDOR, RecordType
from govwren.review import service as review


def is_retired(record_type: RecordType, record: Any) -> bool:
    return record.status == ("former" if record_type is VENDOR else "retired")


def retire(
    session: Session, principal: Principal, record_type: RecordType, record: Any, reason: str
) -> tuple[Any, int]:
    """Mark a record as no longer in use, with the reason. Any review of it in progress is
    cancelled, nothing more falls due for it, and the owners of whatever relies on it are
    told. Returns the record and how many dependents there are."""
    if not access.can_edit(session, principal, record_type, record):
        raise PermissionDenied(f"You cannot retire this {record_type.label}.")
    if is_retired(record_type, record):
        raise Conflict(f"This {record_type.label} is already retired.")
    reason = reason.strip()
    if len(reason) < 10:
        raise Invalid("It was not retired.", {"reason": "Say why it is no longer in use."})
    now = utc_now()
    with audit.operation(session, "record.retire", reason=reason):
        if record_type is USE_CASE:
            open_ = review.open_review(session, record)
            if open_ is not None:
                for task in session.query(ReviewTask).filter_by(
                    review_id=open_.id, status="pending"
                ):
                    task.status, task.notes, task.completed_at = (
                        "waived",
                        "The use was retired.",
                        now,
                    )
                open_.status, open_.closed_at, open_.paused_at = "cancelled", now, None
            draft = session.get(IntakeDraft, record.id)
            if draft is not None:
                session.delete(draft)
            record.next_review_on = None
        record.status = "former" if record_type is VENDOR else "retired"
        if hasattr(record, "catalog_status") and record.catalog_status != "not_listed":
            record.catalog_status = "retired"
        record.version += 1
        record.updated_at = now
        session.flush()
    told = _tell_dependents(session, principal, record_type, record)
    return record, told


def dependents(
    session: Session, record_type: RecordType, record: Any
) -> list[tuple[RecordType, Any]]:
    """The records that rely directly on this one, whoever may see them."""
    here = (record_type.key, record.id)
    found = []
    for source, relation, target in links._edges_of(session, here):
        if target != here or relation == "replaces":
            continue
        other_type = TYPES.get(source[0])
        other = session.get(other_type.model, source[1]) if other_type else None
        if other is not None and other_type is not None and not is_retired(other_type, other):
            found.append((other_type, other))
    return found


def _tell_dependents(
    session: Session, principal: Principal, record_type: RecordType, record: Any
) -> int:
    told = 0
    for other_type, other in dependents(session, record_type, record):
        people = set(
            session.scalars(
                select(RecordOwner.account_id).where(
                    RecordOwner.record_type == other_type.key,
                    RecordOwner.record_id == other.id,
                    RecordOwner.kind != "contact",
                )
            )
        ) or review.stewards_of(session, getattr(other, "org_unit_id", None))
        review.notify(
            session, people, "retired",
            f"{record.name}, which {other.name} relies on, has been retired",
            f"/{other_type.path}/{other.ref}",
            skip=principal.account_id,
        )  # fmt: skip
        told += 1
    return told
