"""The risk register: what could go wrong on a record or for the organization, how likely
and how bad before anything is done, what is done about it, and what is left."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.assurance import library
from govwren.core.clock import today, utc_now
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.models import Account, OrgUnit, Risk, RiskStatement
from govwren.db.models.assurance import TREATMENTS
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.inventory import access
from govwren.inventory.registry import TYPES, RecordType
from govwren.review import service as review

LEVELS = ("low", "moderate", "high", "critical")
LIVE = ("open", "treated", "accepted")
TREATMENT_WORDS = {
    "mitigate": "Reduce it",
    "accept": "Accept it",
    "transfer": "Pass it to someone else",
    "avoid": "Stop doing what causes it",
}


def level(likelihood: int | None, impact: int | None) -> str | None:
    """Likelihood times impact, in four bands: up to 4, up to 9, up to 16, and above."""
    if not likelihood or not impact:
        return None
    score = likelihood * impact
    return LEVELS[0 if score <= 4 else 1 if score <= 9 else 2 if score <= 16 else 3]


def current_level(risk: Risk) -> str:
    """What the risk stands at now: after treatment if it has been treated."""
    return (
        level(risk.residual_likelihood, risk.residual_impact)
        or level(risk.inherent_likelihood, risk.inherent_impact)
        or "low"
    )


def find(session: Session, ref: str) -> Risk:
    risk = session.scalars(select(Risk).where(Risk.ref == ref.strip().upper())).first()
    if risk is None:
        raise NotFound(f"There is no risk {ref}.")
    return risk


def _record(session: Session, risk: Risk) -> tuple[RecordType | None, Any]:
    record_type = TYPES.get(risk.subject_type or "")
    if record_type is None or risk.subject_id is None:
        return None, None
    return record_type, session.get(record_type.model, risk.subject_id)


def can_see(session: Session, principal: Principal, risk: Risk) -> bool:
    if principal.reads_all or principal.account_id in (risk.owner_id, risk.created_by):
        return True
    record_type, record = _record(session, risk)
    return (
        record_type is not None
        and record is not None
        and access.sight(session, principal, record_type, record) == access.FULL
    )


def can_change(session: Session, principal: Principal, risk: Risk) -> bool:
    if principal.governs or risk.owner_id == principal.account_id:
        return True
    record_type, record = _record(session, risk)
    return (
        record_type is not None
        and record is not None
        and access.can_edit(session, principal, record_type, record)
    )


def _score(
    values: Mapping[str, Any], name: str, errors: dict[str, str], *, needed: bool
) -> int | None:
    value = values.get(name)
    if value in (None, ""):
        if needed:
            errors[name] = "Choose from 1 to 5."
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
        errors[name] = "Choose from 1 to 5."
        return None
    return value


def _clean(session: Session, values: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    errors: dict[str, str] = {}
    out: dict[str, Any] = {}
    if creating or "title" in values:
        title = str(values.get("title") or "").strip()
        if not 3 <= len(title) <= 300:
            errors["title"] = "Say what could go wrong."
        out["title"] = title
    if "description" in values:
        out["description"] = str(values.get("description") or "").strip() or None
    if creating or "category" in values:
        known = library.categories(session)
        category = str(values.get("category") or "")
        if category not in known:
            errors["category"] = "Choose a category."
        out["category"] = category
    for name in ("inherent_likelihood", "inherent_impact"):
        if creating or name in values:
            out[name] = _score(values, name, errors, needed=True)
    for name in ("residual_likelihood", "residual_impact"):
        if name in values:
            out[name] = _score(values, name, errors, needed=False)
    if "treatment" in values:
        treatment = values.get("treatment") or None
        if treatment is not None and treatment not in TREATMENTS:
            errors["treatment"] = "Choose what is done about it."
        out["treatment"] = treatment
    if "treatment_note" in values:
        out["treatment_note"] = str(values.get("treatment_note") or "").strip() or None
    if "owner_id" in values:
        owner = session.get(Account, values["owner_id"]) if values.get("owner_id") else None
        if values.get("owner_id") and (owner is None or owner.status != "active"):
            errors["owner_id"] = "Choose who owns the risk."
        out["owner_id"] = owner.id if owner else None
    if "review_on" in values:
        when = values.get("review_on")
        if isinstance(when, str) and when:
            try:
                when = date.fromisoformat(when)
            except ValueError:
                errors["review_on"] = "That is not a date."
        out["review_on"] = when or None
    if errors:
        raise Invalid("The risk was not saved.", errors)
    return out


def _settle(risk: Risk) -> None:
    """A risk's standing follows from what has been done about it."""
    if risk.status == "closed":
        return
    if risk.treatment == "accept":
        risk.status = "accepted"
    elif risk.treatment and risk.residual_likelihood and risk.residual_impact:
        risk.status = "treated"
    else:
        risk.status = "open"


def add(
    session: Session,
    principal: Principal,
    values: Mapping[str, Any],
    *,
    record: tuple[RecordType, Any] | None = None,
    source: str | None = None,
    as_reviewer: bool = False,
) -> Risk:
    """Record a risk on a record, or on the organization when no record is given. Whoever
    is responsible for the record may; a risk to the organization is governance's to add.
    ``library_key`` draws the wording from the risk library."""
    if record is None:
        if not principal.governs:
            raise PermissionDenied("Only governance can record a risk to the organization.")
    elif not (
        as_reviewer
        or principal.governs
        or access.can_edit(session, principal, record[0], record[1])
    ):
        raise PermissionDenied("Only those responsible for a record can add a risk to it.")
    given = dict(values)
    drawn = None
    if given.get("library_key"):
        drawn = session.scalars(
            select(RiskStatement).where(RiskStatement.key == given["library_key"])
        ).first()
        if drawn is None:
            raise Invalid("The risk was not saved.", {"library_key": "That is not in the library."})
        given.setdefault("title", drawn.title)
        given.setdefault("description", drawn.description)
        given.setdefault("category", drawn.category)
    cleaned = _clean(session, given, creating=True)
    with audit.operation(session, "risk.add"):
        risk = Risk(
            ref=next_ref(session, "RSK"),
            subject_type=record[0].key if record else None,
            subject_id=record[1].id if record else None,
            org_unit_id=getattr(record[1], "org_unit_id", None) if record else None,
            library_key=drawn.key if drawn else None,
            status="open",
            source=source,
            created_by=principal.account_id,
            created_at=utc_now(),
            **{"description": None, **cleaned},
        )
        if risk.owner_id is None:
            risk.owner_id = principal.account_id
        _settle(risk)
        session.add(risk)
        session.flush()
    if risk.owner_id not in (None, principal.account_id):
        review.notify(
            session,
            [risk.owner_id],
            "risk",
            f"A risk is yours to own: {risk.title}",
            f"/risks/{risk.ref}",
        )
    return risk


def update(session: Session, principal: Principal, risk: Risk, values: Mapping[str, Any]) -> Risk:
    """Change a risk: rescore it, say what is done about it, pass it to another owner."""
    if not can_change(session, principal, risk):
        raise PermissionDenied("That risk is not yours to change.")
    if risk.status == "closed":
        raise Conflict("This risk is closed.")
    cleaned = _clean(session, values, creating=False)
    if cleaned.get("treatment") == "accept" and not principal.governs:
        raise PermissionDenied("Only governance can accept a risk as it stands.")
    before = risk.owner_id
    with audit.operation(session, "risk.update"):
        for name, value in cleaned.items():
            setattr(risk, name, value)
        _settle(risk)
        session.flush()
    if risk.owner_id not in (None, before, principal.account_id):
        review.notify(
            session,
            [risk.owner_id],
            "risk",
            f"A risk is yours to own: {risk.title}",
            f"/risks/{risk.ref}",
        )
    return risk


def close(session: Session, principal: Principal, risk: Risk, reason: str) -> Risk:
    """Close a risk that no longer applies, with why."""
    if not principal.governs:
        raise PermissionDenied("Only governance can close a risk.")
    if risk.status == "closed":
        raise Conflict("This risk is already closed.")
    reason = reason.strip()
    if len(reason) < 10:
        raise Invalid("The risk was not closed.", {"reason": "Say why it no longer applies."})
    with audit.operation(session, "risk.close", reason=reason):
        risk.status, risk.closed_at = "closed", utc_now()
        session.flush()
    return risk


# --- Looking at risks ---------------------------------------------------------------------


def _view(
    session: Session,
    principal: Principal,
    risk: Risk,
    names: dict[int, str],
    units: dict[int, str],
    labels: dict[str, str],
) -> dict[str, Any]:
    record_type, record = _record(session, risk)
    seen = (
        record_type is not None
        and record is not None
        and access.sight(session, principal, record_type, record) is not None
    )
    return {
        "ref": risk.ref,
        "title": risk.title,
        "description": risk.description,
        "category": risk.category,
        "category_label": labels.get(risk.category, risk.category),
        "library_key": risk.library_key,
        "status": risk.status,
        "inherent": {
            "likelihood": risk.inherent_likelihood,
            "impact": risk.inherent_impact,
            "level": level(risk.inherent_likelihood, risk.inherent_impact),
        },
        "residual": {
            "likelihood": risk.residual_likelihood,
            "impact": risk.residual_impact,
            "level": level(risk.residual_likelihood, risk.residual_impact),
        },
        "level": current_level(risk),
        "treatment": risk.treatment,
        "treatment_label": TREATMENT_WORDS.get(risk.treatment or ""),
        "treatment_note": risk.treatment_note,
        "owner_id": risk.owner_id,
        "owner": names.get(risk.owner_id or 0),
        "review_on": risk.review_on,
        "review_due": risk.status in LIVE and bool(risk.review_on and risk.review_on <= today()),
        "source": risk.source,
        "record": {
            "type": record_type.key,
            "ref": record.ref,
            "name": record.name,
            "href": f"/{record_type.path}/{record.ref}",
        }
        if seen and record_type and record
        else None,
        "organization": risk.subject_type is None,
        "unit": units.get(risk.org_unit_id or 0),
        "created_at": risk.created_at,
        "closed_at": risk.closed_at,
        "can": {
            "change": risk.status != "closed" and can_change(session, principal, risk),
            "accept": risk.status != "closed" and principal.governs,
            "close": risk.status != "closed" and principal.governs,
        },
    }


def _lookups(
    session: Session, rows: list[Risk]
) -> tuple[dict[int, str], dict[int, str], dict[str, str]]:
    names = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_({r.owner_id for r in rows} - {None} or {0})
            )
        ).all()  # type: ignore[arg-type]
    )
    units = dict(session.execute(select(OrgUnit.id, OrgUnit.name)).all())  # type: ignore[arg-type]
    return names, units, library.categories(session)


def view(session: Session, principal: Principal, risk: Risk) -> dict[str, Any]:
    if not can_see(session, principal, risk):
        raise NotFound(f"There is no risk {risk.ref}.")
    return _view(session, principal, risk, *_lookups(session, [risk]))


def register(
    session: Session,
    principal: Principal,
    *,
    status: str | None = "live",
    record: tuple[RecordType, Any] | None = None,
    mine: bool = False,
) -> dict[str, Any]:
    """The register, highest first, with a count for each cell of the five-by-five grid."""
    statement = select(Risk)
    if status == "live":
        statement = statement.where(Risk.status.in_(LIVE))
    elif status and status != "all":
        statement = statement.where(Risk.status == status)
    if record is not None:
        statement = statement.where(
            Risk.subject_type == record[0].key, Risk.subject_id == record[1].id
        )
    if mine:
        statement = statement.where(Risk.owner_id == principal.account_id)
    rows = [r for r in session.scalars(statement) if can_see(session, principal, r)]
    order = {name: position for position, name in enumerate(reversed(LEVELS))}
    rows.sort(key=lambda r: (order[current_level(r)], r.review_on or date.max, r.id))
    lookups = _lookups(session, rows)
    grid = [[0] * 5 for _ in range(5)]  # grid[impact - 1][likelihood - 1]
    by_level = dict.fromkeys(LEVELS, 0)
    for risk in rows:
        if risk.status in LIVE:
            likelihood = risk.residual_likelihood or risk.inherent_likelihood
            impact = risk.residual_impact or risk.inherent_impact
            grid[impact - 1][likelihood - 1] += 1
            by_level[current_level(risk)] += 1
    return {
        "risks": [_view(session, principal, risk, *lookups) for risk in rows],
        "grid": grid,
        "by_level": by_level,
        "can_add_for_organization": principal.governs,
    }


def serious_on(session: Session, subject_type: str, subject_id: int) -> list[Risk]:
    """The risks on a record that stand at the two highest levels."""
    rows = session.scalars(
        select(Risk).where(
            Risk.subject_type == subject_type, Risk.subject_id == subject_id, Risk.status.in_(LIVE)
        )
    )
    return [risk for risk in rows if current_level(risk) in ("high", "critical")]
