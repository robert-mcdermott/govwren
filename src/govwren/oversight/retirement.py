"""Retiring a record: it stays in the inventory, with its history, marked as no longer in use."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.models import IntakeDraft, ReviewTask
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import USE_CASE, VENDOR, RecordType
from govwren.review import service as review


def is_retired(record_type: RecordType, record: Any) -> bool:
    return record.status == ("former" if record_type is VENDOR else "retired")


def retire(
    session: Session, principal: Principal, record_type: RecordType, record: Any, reason: str
) -> Any:
    """Mark a record as no longer in use, with the reason. Any review of it in progress is
    cancelled, and nothing more falls due for it."""
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
    return record
