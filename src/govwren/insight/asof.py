"""A record, and the inventory, as they stood on a chosen date (RPT-07).

Nothing is stored for this. The history holds every change to every row as the value
before and the value after, so the state on any day is the changes up to the end of that
day, applied in order.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today
from govwren.core.errors import Invalid, NotFound
from govwren.db.models import Event
from govwren.insight.measures import IN_USE
from govwren.inventory import access, history
from govwren.inventory.registry import TYPES, USE_CASE, RecordType

# Bookkeeping that says nothing about the record itself.
_SKIP = frozenset({"id", "ref", "created_by", "created_at", "updated_at", "version", "tags"})
_SKIP |= {"restricted", "search_text", "agent_profile"}
_LABELS = {"org_unit_id": "Unit", "vendor_id": "Supplier"}


def moment(on: date) -> datetime:
    """The end of a day: everything recorded on it counts."""
    return datetime.combine(on + timedelta(days=1), time.min, tzinfo=UTC)


def parse(value: str | None) -> date:
    try:
        on = date.fromisoformat(value or "")
    except ValueError as exc:
        raise Invalid("That date is not valid.", {"on": "Give a date as year-month-day."}) from exc
    if on > today():
        raise Invalid("That date is not valid.", {"on": "Choose today or a day before it."})
    return on


def _replay(events: Iterable[Event]) -> dict[int, dict[str, Any]]:
    """Apply changes in order. What is left is each row as it stood after the last of them;
    a row that was deleted is gone."""
    rows: dict[int, dict[str, Any]] = {}
    for event in events:
        if event.subject_id is None:
            continue
        if event.action == "deleted":
            rows.pop(event.subject_id, None)
            continue
        row = rows.setdefault(event.subject_id, {})
        for field, change in (event.changes or {}).items():
            if isinstance(change, list) and len(change) == 2:
                row[field] = change[1]
    return rows


def _own(session: Session, key: str, record_id: int, until: datetime | None) -> dict[str, Any]:
    statement = select(Event).where(Event.subject_type == key, Event.subject_id == record_id)
    if until is not None:
        statement = statement.where(Event.at < until)
    return _replay(session.scalars(statement.order_by(Event.id))).get(record_id, {})


def _children(
    session: Session, key: str, record_id: int, kind: str, until: datetime
) -> list[dict[str, Any]]:
    rows = _replay(
        session.scalars(
            select(Event)
            .where(
                Event.subject_type == kind,
                Event.parent_type == key,
                Event.parent_id == record_id,
                Event.at < until,
            )
            .order_by(Event.id)
        )
    )
    return [rows[row_id] for row_id in sorted(rows)]


def record(
    session: Session, principal: Principal, record_type: RecordType, found: Any, on: date
) -> dict[str, Any]:
    """One record as it stood at the end of a day, beside how it stands now."""
    if access.sight(session, principal, record_type, found) != access.FULL:
        raise NotFound(f"There is no {record_type.label} {found.ref}.")
    until = moment(on)
    then = _own(session, record_type.key, found.id, until)
    now = _own(session, record_type.key, found.id, None)
    lookups = history._Lookups(session)
    lookups.kind_vocabulary = history.KIND_VOCABULARY.get(record_type.key, "system_kinds")
    fields = []
    for field in now:
        if field in _SKIP:
            continue
        was, is_ = lookups.value(field, then.get(field)), lookups.value(field, now.get(field))
        if was is None and is_ is None:
            continue
        fields.append(
            {
                "field": field,
                "label": _LABELS.get(field) or history._words(field.removesuffix("_id")),
                "then": was,
                "now": is_,
                "changed": then.get(field) != now.get(field),
            }
        )
    fields.sort(key=lambda item: not item["changed"])  # what changed comes first
    owners = [
        {
            "name": lookups.name("account", row.get("account_id")),
            "kind": lookups.vocab("owner_kinds", row.get("kind")),
        }
        for row in _children(session, record_type.key, found.id, "record_owner", until)
    ]
    relies_on = [
        {
            "relation": history._words(str(row.get("relation") or "uses")),
            "name": lookups.name(str(row.get("to_type") or "system"), row.get("to_id")),
        }
        for row in _children(session, record_type.key, found.id, "record_link", until)
        if row.get("to_type") in TYPES and row.get("to_type") != "vendor"
    ]
    conditions = [
        {"text": row.get("text"), "status": history._words(str(row.get("status") or "open"))}
        for row in _children(session, record_type.key, found.id, "condition", until)
    ]
    since = session.execute(
        select(func.count())
        .select_from(Event)
        .where(
            Event.at >= until,
            ((Event.subject_type == record_type.key) & (Event.subject_id == found.id))
            | ((Event.parent_type == record_type.key) & (Event.parent_id == found.id)),
        )
    ).scalar_one()
    return {
        "type": record_type.key,
        "ref": found.ref,
        "name": then.get("name") or found.name,
        "name_now": found.name,
        "on": on,
        "existed": bool(then),
        "created_on": str(now.get("created_at") or "")[:10] or None,
        "fields": fields if then else [],
        "owners": owners,
        "relies_on": relies_on,
        "conditions": conditions,
        "changes_since": since,
    }


def inventory(session: Session, on: date) -> dict[str, Any]:
    """Every use that was on the record at the end of a day, as it stood then."""
    until = moment(on)
    rows = _replay(
        session.scalars(
            select(Event)
            .where(Event.subject_type == USE_CASE.key, Event.at < until)
            .order_by(Event.id)
        )
    )
    current = dict(
        session.execute(select(USE_CASE.model.id, USE_CASE.model.status)).all()  # type: ignore[attr-defined]
    )
    lookups = history._Lookups(session)
    uses = []
    for row_id in sorted(rows):
        row = rows[row_id]
        if row.get("status") in (None, "draft") or row_id not in current:
            continue
        uses.append(
            {
                "ref": row.get("ref"),
                "name": row.get("name"),
                "status": row.get("status"),
                "status_now": current[row_id],
                "tier": row.get("tier"),
                "tier_label": lookups.tier(row["tier"]) if row.get("tier") else None,
                "unit": lookups.name("unit", row["org_unit_id"])
                if row.get("org_unit_id")
                else None,
                "approved_until": row.get("approved_until"),
            }
        )
    by_status = Counter(use["status"] for use in uses)
    by_tier = Counter(use["tier_label"] for use in uses if use["status"] in IN_USE and use["tier"])
    return {
        "on": on,
        "uses": uses,
        "in_use": sum(by_status[status] for status in IN_USE),
        "by_status": dict(by_status),
        "by_tier": dict(by_tier),
        "changed_since": sum(1 for use in uses if use["status"] != use["status_now"]),
    }
