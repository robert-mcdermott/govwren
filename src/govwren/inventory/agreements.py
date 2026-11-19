"""Agreements with vendors: what each covers, when it ends, and how much notice it needs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, Agreement, Vendor
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import VENDOR
from govwren.program import vocab

SOON = 90  # days: an agreement ending within this is worth a look


def _date(value: Any, field: str, errors: dict[str, str]) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors[field] = "Give the date as year-month-day."
        return None


def state(agreement: Agreement, on: date | None = None) -> str:
    """Where an agreement stands today: current, ending soon, in its notice period, or ended."""
    on = on or today()
    if agreement.expires_on is None:
        return "current"
    if agreement.expires_on < on:
        return "current" if agreement.auto_renews else "ended"
    notice = agreement.expires_on - timedelta(days=agreement.notice_days or 0)
    if agreement.notice_days and notice <= on:
        return "notice"
    return "ending" if agreement.expires_on <= on + timedelta(days=SOON) else "current"


def view(session: Session, agreement: Agreement) -> dict[str, Any]:
    owner = session.get(Account, agreement.owner_id) if agreement.owner_id else None
    on = today()
    return {
        "id": agreement.id,
        "kind": agreement.kind,
        "title": agreement.title,
        "reference": agreement.reference,
        "effective_on": agreement.effective_on,
        "expires_on": agreement.expires_on,
        "auto_renews": agreement.auto_renews,
        "notice_days": agreement.notice_days,
        "notice_by": agreement.expires_on - timedelta(days=agreement.notice_days)
        if agreement.expires_on and agreement.notice_days
        else None,
        "owner": {"id": owner.id, "name": owner.display_name} if owner else None,
        "notes": agreement.notes,
        "state": state(agreement, on),
        "days_left": (agreement.expires_on - on).days if agreement.expires_on else None,
    }


def of(session: Session, vendor: Vendor) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(Agreement)
        .where(Agreement.vendor_id == vendor.id)
        .order_by(Agreement.expires_on.is_(None), Agreement.expires_on, Agreement.id)
    )
    return [view(session, row) for row in rows]


def _apply(
    session: Session, agreement: Agreement, values: Mapping[str, Any], creating: bool
) -> None:
    errors: dict[str, str] = {}
    if "kind" in values or creating:
        if values.get("kind") not in vocab.keys(session, "agreement_kinds"):
            errors["kind"] = "Choose what kind of agreement it is."
        else:
            agreement.kind = values["kind"]
    if "title" in values or creating:
        title = str(values.get("title") or "").strip()
        if not title or len(title) > 200:
            errors["title"] = "Give it a title of up to 200 characters."
        else:
            agreement.title = title
    if "reference" in values:
        agreement.reference = str(values["reference"] or "").strip()[:120] or None
    if "effective_on" in values:
        agreement.effective_on = _date(values["effective_on"], "effective_on", errors)
    if "expires_on" in values:
        agreement.expires_on = _date(values["expires_on"], "expires_on", errors)
    if "auto_renews" in values:
        agreement.auto_renews = bool(values["auto_renews"])
    if "notice_days" in values:
        days = values["notice_days"]
        if days in (None, ""):
            agreement.notice_days = None
        elif not isinstance(days, int) or isinstance(days, bool) or not 0 <= days <= 730:
            errors["notice_days"] = "Give the notice period as a number of days."
        else:
            agreement.notice_days = days
    if "owner_id" in values:
        owner = values["owner_id"]
        if owner in (None, ""):
            agreement.owner_id = None
        elif session.get(Account, int(owner)) is None:
            errors["owner_id"] = "Choose a person."
        else:
            agreement.owner_id = int(owner)
    if "notes" in values:
        agreement.notes = str(values["notes"] or "").strip() or None
    if (
        agreement.effective_on
        and agreement.expires_on
        and agreement.expires_on < agreement.effective_on
    ):
        errors["expires_on"] = "It cannot end before it starts."
    if errors:
        raise Invalid("The agreement was not saved.", errors)


def _may(session: Session, principal: Principal, vendor: Vendor) -> None:
    if not access.can_edit(session, principal, VENDOR, vendor):
        raise PermissionDenied("You cannot edit this vendor's agreements.")


def create(
    session: Session, principal: Principal, vendor: Vendor, values: Mapping[str, Any]
) -> Agreement:
    _may(session, principal, vendor)
    agreement = Agreement(vendor_id=vendor.id, auto_renews=False)
    with session.no_autoflush:
        _apply(session, agreement, values, True)
    with audit.operation(session, "vendor.agreement", vendor=vendor.ref):
        session.add(agreement)
        session.flush()
    return agreement


def _find(session: Session, principal: Principal, agreement_id: int) -> tuple[Agreement, Vendor]:
    agreement = session.get(Agreement, agreement_id)
    vendor = session.get(Vendor, agreement.vendor_id) if agreement else None
    if agreement is None or vendor is None:
        raise NotFound("There is no such agreement.")
    _may(session, principal, vendor)
    return agreement, vendor


def update(
    session: Session, principal: Principal, agreement_id: int, values: Mapping[str, Any]
) -> Agreement:
    agreement, vendor = _find(session, principal, agreement_id)
    with audit.operation(session, "vendor.agreement", vendor=vendor.ref):
        try:
            with session.no_autoflush:
                _apply(session, agreement, values, False)
        except Invalid:
            session.expire(agreement)
            raise
        session.flush()
    return agreement


def remove(session: Session, principal: Principal, agreement_id: int) -> None:
    agreement, vendor = _find(session, principal, agreement_id)
    with audit.operation(session, "vendor.agreement", vendor=vendor.ref):
        session.delete(agreement)
        session.flush()


def needing_attention(session: Session) -> list[tuple[Agreement, Vendor]]:
    """Agreements that have ended, are in their notice period, or end soon."""
    rows = session.execute(
        select(Agreement, Vendor)
        .join(Vendor, Vendor.id == Agreement.vendor_id)
        .where(Agreement.expires_on.is_not(None))
        .order_by(Agreement.expires_on)
    ).all()
    return [(a, v) for a, v in rows if state(a) != "current"]
