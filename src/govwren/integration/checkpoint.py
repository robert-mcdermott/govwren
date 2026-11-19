"""The checkpoint: one question another system may ask before it proceeds (PLT-19).

"Is this reference approved, for what data, and until when?" A purchasing form, an ethics
application, or a data access request cites a GovWren reference; the system that receives
it asks here. The answer is the record's standing and nothing about its content, so it is
given to anyone who may call the API, whatever they may see of the record itself.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from govwren.core.clock import today
from govwren.core.errors import Invalid
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, USE_CASE, VENDOR, find_any
from govwren.program import vocab

IN_FORCE = ("approved", "approved_with_conditions")


def check(session: Session, ref: str, data_class: str | None = None) -> dict[str, Any]:
    """A record's standing, and whether it covers a class of data if one is named."""
    record_type, record = find_any(session, ref)
    classes = vocab.keys(session, "data_classes", active_only=False)
    if data_class is not None and data_class not in classes:
        raise Invalid(
            "That is not a data class.", {"data_class": f"Use one of: {', '.join(classes)}."}
        )
    labels = vocab.labels(session, "data_classes")
    answer: dict[str, Any] = {
        "ref": record.ref,
        "type": record_type.key,
        "name": record.name,
        "checked_on": today(),
    }
    covers: str | None = None
    if record_type is USE_CASE:
        ended = record.approved_until is not None and record.approved_until < today()
        answer.update(
            status=record.status,
            approved=record.status in IN_FORCE and not ended,
            approved_until=record.approved_until,
            tier=record.tier,
        )
        covers = record.data_class
    elif record_type in (SYSTEM, MODEL):
        answer.update(
            status=record.catalog_status,
            approved=record.status == "active"
            and record.catalog_status in ("approved", "approved_with_restrictions"),
            approved_until=None,
            excluded_data_categories=list(record.excluded_data_categories or []),
        )
        covers = record.permitted_data_class
    elif record_type is DATASET:
        answer.update(status=record.status, approved=None, approved_until=None)
        covers = record.data_class
    else:
        assert record_type is VENDOR
        answer.update(status=record.status, approved=record.status == "active", approved_until=None)
    answer["data_class"] = covers
    answer["data_class_label"] = labels.get(covers or "", None)
    if data_class is not None and record_type is not DATASET:
        within = covers is not None and classes.index(data_class) <= classes.index(covers)
        answer["asked_data_class"] = data_class
        answer["allowed"] = bool(answer["approved"]) and within
    return answer
