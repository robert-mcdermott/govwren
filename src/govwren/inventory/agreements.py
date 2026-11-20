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
from govwren.db.models import Account, Agreement, AISystem, Model, RecordLink, UseCase, Vendor
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import VENDOR
from govwren.program import settings, vocab

SOON = 90  # days: an agreement ending within this is worth a look
HEALTH_KIND = "health_information"
HEALTH_DATA = "health"  # the data category the rule is about
RULE_SETTING = "inventory.health_agreement_rule"
# The key an exception names when it departs from this rule.
RULE_KEY = "health_agreement"
WILLING = ("yes", "no", "unknown")


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


def view(
    session: Session, agreement: Agreement, principal: Principal | None = None
) -> dict[str, Any]:
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
        "covers": _covered(session, agreement, principal),
        "scope_note": agreement.scope_note,
        "notice_days": agreement.notice_days,
        "notice_by": agreement.expires_on - timedelta(days=agreement.notice_days)
        if agreement.expires_on and agreement.notice_days
        else None,
        "owner": {"id": owner.id, "name": owner.display_name} if owner else None,
        "notes": agreement.notes,
        "state": state(agreement, on),
        "days_left": (agreement.expires_on - on).days if agreement.expires_on else None,
    }


def _covered(
    session: Session, agreement: Agreement, principal: Principal | None = None
) -> list[dict[str, str]]:
    from govwren.inventory.registry import MODEL, SYSTEM

    out: list[dict[str, str]] = []
    for kind, record_type, ids in (
        ("system", SYSTEM, agreement.covered_systems),
        ("model", MODEL, agreement.covered_models),
    ):
        if ids:
            model: Any = record_type.model
            rows = session.scalars(
                select(model).where(model.id.in_(list(ids))).order_by(model.name)
            )
            out += [
                {"type": kind, "ref": row.ref, "name": row.name}
                for row in rows
                if access.may_name(session, principal, record_type, row)
            ]
    return out


# How an AI system stands for health information. The first two let health data be used.
HEALTH_OK = ("in_place", "not_needed")
HEALTH_WORDS = {
    "in_place": "An agreement covering health information is in place",
    "not_needed": "It runs on your own equipment, so no supplier receives the data",
    "ended": "The agreement covering health information has ended",
    "available": (
        "The vendor will sign an agreement covering health information, but none names it"
    ),
    "not_offered": "The vendor will not sign an agreement covering health information",
    "unknown": "No agreement covering health information names it",
}
# A cloud tenant is still someone else's equipment: its supplier needs an agreement too.
OWN_HOSTING = ("local", "on_premises")


def health_standing(session: Session, record: AISystem | Model) -> str:
    """Whether health information may go to this AI system or model, so far as agreements
    say. An agreement counts only if it names the record: a vendor's agreement for one
    product says nothing about another. A model counts as a supplier's only when it is
    reached through the supplier's service; the organization runs any other itself."""
    if isinstance(record, Model):
        if record.origin != "commercial_api":
            return "not_needed"
        column = "covered_models"
    else:
        if record.hosting in OWN_HOSTING:
            return "not_needed"
        column = "covered_systems"
    if record.vendor_id is None:
        return "unknown"
    naming = [
        row
        for row in session.scalars(
            select(Agreement).where(
                Agreement.vendor_id == record.vendor_id, Agreement.kind == HEALTH_KIND
            )
        )
        if record.id in (getattr(row, column) or [])
    ]
    if any(state(row) != "ended" for row in naming):
        return "in_place"
    if naming:
        return "ended"
    vendor = session.get(Vendor, record.vendor_id)
    willing = vendor.signs_health_agreement if vendor else "unknown"
    return {"yes": "available", "no": "not_offered"}.get(willing, "unknown")


def _models_of(session: Session, use_case: UseCase) -> list[Model]:
    ids = session.scalars(
        select(RecordLink.to_id).where(
            RecordLink.from_type == "use_case",
            RecordLink.from_id == use_case.id,
            RecordLink.relation == "uses",
            RecordLink.to_type == "model",
        )
    ).all()
    return list(session.scalars(select(Model).where(Model.id.in_(ids)))) if ids else []


def rule_on(session: Session) -> bool:
    """Whether health information needs a covering agreement before a use is approved."""
    return settings.get(session, RULE_SETTING, True) is not False


def health_gap(
    session: Session,
    use_case: UseCase,
    answers: Mapping[str, Any] | None = None,
    *,
    exceptions: bool = True,
) -> str | None:
    """Why this use may not be approved yet, so far as agreements go, or None.

    A use that involves health information needs every AI system it uses to be covered by
    an agreement, unless the data is de-identified first, the system runs on the
    organization's own equipment, or (for a person deciding, not for a rule) an approved
    exception is in force on the use."""
    if not rule_on(session) or HEALTH_DATA not in (use_case.data_categories or []):
        return None
    if (answers or {}).get("deidentified") in (True, "yes"):
        return None
    from govwren.inventory import records

    tools: list[AISystem | Model] = [
        *records.systems_of(session, [use_case.id]).get(use_case.id, []),
        *_models_of(session, use_case),
    ]
    lacking = [tool for tool in tools if health_standing(session, tool) not in HEALTH_OK]
    if not lacking:
        return None
    if exceptions:
        from govwren.oversight import exceptions as departures

        # Only an exception granted for this rule sets it aside: one granted for some
        # other requirement says nothing about agreements.
        if any(
            row.rule == RULE_KEY for row in departures.active_on(session, "use_case", use_case.id)
        ):
            return None
    first = lacking[0]
    return (
        f"This use involves health information, and {first.name} ({first.ref}) is not covered "
        f"for it: {HEALTH_WORDS[health_standing(session, first)].lower()}. Record the agreement "
        "on the vendor, or approve an exception to this rule for this use first."
    )


def health_view(session: Session, record: AISystem | Model) -> dict[str, Any]:
    standing = health_standing(session, record)
    return {"standing": standing, "ok": standing in HEALTH_OK, "words": HEALTH_WORDS[standing]}


def of(
    session: Session, vendor: Vendor, principal: Principal | None = None
) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(Agreement)
        .where(Agreement.vendor_id == vendor.id)
        .order_by(Agreement.expires_on.is_(None), Agreement.expires_on, Agreement.id)
    )
    return [view(session, row, principal) for row in rows]


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
    if "scope_note" in values:
        agreement.scope_note = str(values["scope_note"] or "").strip()[:500] or None
    if "covers" in values:
        wanted = [str(ref).strip().upper() for ref in values["covers"] or []]
        theirs: dict[str, tuple[str, int]] = {}
        for system in session.scalars(
            select(AISystem).where(AISystem.vendor_id == agreement.vendor_id)
        ):
            theirs[system.ref] = ("system", system.id)
        for model in session.scalars(select(Model).where(Model.vendor_id == agreement.vendor_id)):
            theirs[model.ref] = ("model", model.id)
        unknown = [ref for ref in wanted if ref not in theirs]
        if unknown:
            errors["covers"] = f"{unknown[0]} is not one of this vendor's AI systems or models."
        else:
            agreement.covered_systems = sorted(
                {theirs[ref][1] for ref in wanted if theirs[ref][0] == "system"}
            )
            agreement.covered_models = sorted(
                {theirs[ref][1] for ref in wanted if theirs[ref][0] == "model"}
            )
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


def _may_cover(
    principal: Principal, values: Mapping[str, Any], agreement: Agreement | None = None
) -> None:
    """An agreement covering health information decides whether health information may go to
    a tool, so only governance records one, changes one, or says what an agreement covers."""
    touches = (
        values.get("kind") == HEALTH_KIND
        or "covers" in values
        or (agreement is not None and agreement.kind == HEALTH_KIND)
    )
    if touches and not access.can_edit_catalog(principal):
        raise PermissionDenied(
            "Only governance records an agreement covering health information, or what an "
            "agreement covers."
        )


def create(
    session: Session, principal: Principal, vendor: Vendor, values: Mapping[str, Any]
) -> Agreement:
    _may(session, principal, vendor)
    _may_cover(principal, values)
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
    _may_cover(principal, values, agreement)
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
    _may_cover(principal, {}, agreement)
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
