"""Who may see and change an inventory record (see spec/security.md).

A viewer has one of three *sights* of a record: all of it, a summary, or nothing. Systems
and vendors are reference data that everyone signed in may read. Use cases follow the
organization's visibility setting.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, exists, false, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from govwren.access.principal import Principal
from govwren.db.models import RecordOwner
from govwren.inventory.registry import USE_CASE, VENDOR, RecordType
from govwren.program import settings

FULL, SUMMARY = "full", "summary"
VISIBILITY_SETTING = "inventory.visibility"
VISIBILITIES = {
    "open": "Everyone sees every approved use case in full",
    "summary": "Everyone sees a summary of approved use cases, and full detail for their own units",
    "unit": "People see only the use cases of their own units",
}
# A use case that has been approved is part of the organization's record, whatever happened
# to it afterwards.
ESTABLISHED = ("approved", "approved_with_conditions", "suspended", "lapsed", "retired")
EDITING_KINDS = ("accountable", "technical")


def visibility(session: Session) -> str:
    value = settings.get(session, VISIBILITY_SETTING, "summary")
    return value if value in VISIBILITIES else "summary"


def owner_kinds(
    session: Session, record_type: RecordType, record_id: int, account_id: int | None
) -> set[str]:
    if account_id is None:
        return set()
    return set(
        session.scalars(
            select(RecordOwner.kind).where(
                RecordOwner.record_type == record_type.key,
                RecordOwner.record_id == record_id,
                RecordOwner.account_id == account_id,
            )
        )
    )


def sight(
    session: Session,
    principal: Principal,
    record_type: RecordType,
    record: Any,
    *,
    owned: bool | None = None,
    setting: str | None = None,
) -> str | None:
    """How much of this record the person may see: ``FULL``, ``SUMMARY``, or None."""
    if principal.reads_all:
        return FULL
    if owned is None:
        owned = bool(owner_kinds(session, record_type, record.id, principal.account_id))
    unit = getattr(record, "org_unit_id", None)
    if owned or principal.stewards_unit(unit):
        return FULL
    mine = record.created_by is not None and record.created_by == principal.account_id
    if record_type is not USE_CASE:
        return None if record.restricted and not mine else FULL
    if record.status == "draft":
        return FULL if mine else None
    if record.restricted:
        return None
    if unit in principal.member_units:
        return FULL
    if record.status not in ESTABLISHED:
        return None
    setting = setting or visibility(session)
    return {"open": FULL, "summary": SUMMARY}.get(setting)


def visible(
    session: Session, principal: Principal, record_type: RecordType
) -> ColumnElement[bool] | None:
    """A condition that keeps only the records the person may see at all, or None for all."""
    if principal.reads_all:
        return None
    model: Any = record_type.model
    me = principal.account_id
    owned = exists(
        select(RecordOwner.id).where(
            RecordOwner.record_type == record_type.key,
            RecordOwner.record_id == model.id,
            RecordOwner.account_id == me,
        )
    )
    mine = model.created_by == me
    if record_type is not USE_CASE:
        stewarded = (
            model.org_unit_id.in_(principal.steward_units) if record_type.has_unit else false()
        )
        return or_(model.restricted.is_(False), owned, mine, stewarded)
    conditions = [
        owned,
        model.org_unit_id.in_(principal.steward_units),
        and_(mine, model.status == "draft"),
        and_(
            model.restricted.is_(False),
            model.status != "draft",
            model.org_unit_id.in_(principal.member_units),
        ),
    ]
    if visibility(session) in ("open", "summary"):
        conditions.append(and_(model.restricted.is_(False), model.status.in_(ESTABLISHED)))
    return or_(*conditions)


def can_edit(session: Session, principal: Principal, record_type: RecordType, record: Any) -> bool:
    if principal.edits_all:
        return True
    if principal.stewards_unit(getattr(record, "org_unit_id", None)):
        return True
    if owner_kinds(session, record_type, record.id, principal.account_id) & set(EDITING_KINDS):
        return True
    mine = record.created_by is not None and record.created_by == principal.account_id
    if not mine:
        return False
    # Whoever added a record may keep shaping it until governance has taken it up.
    if record_type is USE_CASE:
        return record.status == "draft"
    if record_type is VENDOR:
        return record.status == "prospective"
    return record.catalog_status == "not_listed"


def can_edit_catalog(principal: Principal) -> bool:
    """A system's standing in the catalog, and a vendor's standing, are governance's to set."""
    return principal.edits_all
