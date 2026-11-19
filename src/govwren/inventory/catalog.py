"""The catalog: the AI systems the organization has evaluated, what each may be used with,
and the one-minute path for registering a use that fits (FDR-01 to FDR-03)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid
from govwren.db.models import AISystem, Condition, Decision, RecordLink, Vendor
from govwren.events import audit
from govwren.inventory import records
from govwren.inventory.registry import SYSTEM, USE_CASE
from govwren.program import vocab

LISTED = ("approved", "approved_with_restrictions", "under_evaluation", "not_approved")
USABLE = ("approved", "approved_with_restrictions")
ORDER = {status: index for index, status in enumerate(LISTED)}


def listing(session: Session, *, query: str = "") -> list[dict[str, Any]]:
    """Every system in the catalog, approved ones first. Visible to everyone signed in."""
    statement = select(AISystem).where(
        AISystem.catalog_status.in_(LISTED),
        AISystem.status == "active",
        AISystem.restricted.is_(False),
    )
    if query.strip():
        like = f"%{query.strip().lower()}%"
        vendors = select(Vendor.id).where(func.lower(Vendor.name).like(like))
        statement = statement.where(
            or_(
                func.lower(AISystem.name).like(like),
                func.lower(func.coalesce(AISystem.summary, "")).like(like),
                func.lower(func.coalesce(AISystem.edition, "")).like(like),
                AISystem.vendor_id.in_(vendors),
            )
        )
    systems = sorted(
        session.scalars(statement),
        key=lambda s: (ORDER[s.catalog_status], s.name.lower(), s.edition or ""),
    )
    vendor_ids = {s.vendor_id for s in systems if s.vendor_id}
    vendors_by_id = (
        {v.id: v.name for v in session.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))}
        if vendor_ids
        else {}
    )
    uses = dict(
        session.execute(
            select(RecordLink.to_id, func.count())
            .where(RecordLink.to_type == "system", RecordLink.relation == records.USES)
            .group_by(RecordLink.to_id)
        ).all()  # type: ignore[arg-type]
    )
    return [
        {
            "ref": s.ref,
            "name": s.name,
            "edition": s.edition,
            "summary": s.summary,
            "kind": s.kind,
            "vendor": vendors_by_id.get(s.vendor_id or 0),
            "catalog_status": s.catalog_status,
            "permitted_data_class": s.permitted_data_class,
            "excluded_data_categories": s.excluded_data_categories,
            "terms": s.terms,
            "trains_on_inputs": (s.data_handling or {}).get("trains_on_inputs"),
            "uses": uses.get(s.id, 0),
            "usable": s.catalog_status in USABLE,
        }
        for s in systems
    ]


def fits(
    session: Session, system: AISystem, data_class: str | None, categories: list[str]
) -> str | None:
    """Why this data may not be used with this system, or None if it may."""
    if system.catalog_status not in USABLE or system.status != "active":
        return "This system is not approved for use."
    labels = vocab.labels(session, "data_classes")
    if vocab.rank(session, "data_classes", data_class) > vocab.rank(
        session, "data_classes", system.permitted_data_class
    ):
        allowed = labels.get(system.permitted_data_class or "", "less sensitive")
        yours = labels.get(data_class or "", data_class)
        return f"It is approved for data up to {allowed}, and yours is {yours}."
    barred = [c for c in categories if c in (system.excluded_data_categories or [])]
    if barred:
        names = vocab.labels(session, "data_categories")
        return f"It is not approved for {', '.join(names.get(c, c).lower() for c in barred)}."
    return None


def register(
    session: Session, principal: Principal, system: AISystem, values: Mapping[str, Any]
) -> dict[str, Any]:
    """Register a use of a catalog system.

    If the use fits what the system is permitted for, and is an everyday one, it is approved
    at once under the catalog's terms. Otherwise a request is begun with what has been said
    carried forward, so nothing is typed twice.
    """
    name = str(values.get("name") or "").strip()
    data_class = values.get("data_class") or None
    categories = vocab.check_many(
        session, "data_categories", values.get("data_categories"), "data_categories"
    )
    errors = {}
    if not name:
        errors["name"] = "Say what you will use it for."
    if not values.get("org_unit_id"):
        errors["org_unit_id"] = "Say which unit this is for."
    if data_class not in vocab.keys(session, "data_classes"):
        errors["data_class"] = "Choose the most sensitive class of data involved."
    if errors:
        raise Invalid("The use was not registered.", errors)
    if system.catalog_status not in USABLE or system.status != "active":
        raise Conflict("This system is not approved for use, so a use of it cannot be registered.")

    problem = fits(session, system, data_class, categories)
    if problem is None and not values.get("everyday"):
        problem = (
            "It does more than produce output for a person to check, so it needs a closer look."
        )
    if problem is not None:
        from govwren.intake import service as intake

        version = intake.current_form(session)
        answers = {}
        targets = {
            "name": name,
            "org_unit_id": int(values["org_unit_id"]),
            "purpose": values.get("purpose"),
            "systems": [system.ref],
            "data_class": data_class,
            "data_categories": categories,
        }
        for section in version.schema["sections"]:
            for question in section["questions"]:
                if question.get("maps_to") in targets and targets[question["maps_to"]]:
                    answers[question["key"]] = targets[question["maps_to"]]
        use_case = intake.start(session, principal, answers)
        return {"registered": False, "reason": problem, "ref": use_case.ref}

    from govwren.review import service as review

    with audit.operation(session, "catalog.register", system=system.ref):
        use_case = records.create(
            session,
            principal,
            USE_CASE,
            {
                "name": name,
                "org_unit_id": values["org_unit_id"],
                "purpose": values.get("purpose"),
                "data_class": data_class,
                "data_categories": categories,
                "stage": "in_use",
            },
        )
        records.set_systems(session, principal, use_case, [system.ref])
        use_case.tier, use_case.tier_source = 1, "catalog"
        session.flush()
        opened = review.approve_under_catalog(session, principal, use_case, system.name)
        if system.terms:
            decision = session.scalars(
                select(Decision).where(Decision.review_id == opened.id)
            ).one()
            session.add(
                Condition(
                    decision_id=decision.id,
                    subject_type="use_case",
                    subject_id=use_case.id,
                    text=f"Follow the terms of use for {system.name}: {system.terms}",
                    kind="ongoing",
                    owner_id=principal.account_id,
                    status="open",
                )
            )
            if use_case.status == "approved":
                use_case.status = "approved_with_conditions"
        use_case.updated_at = utc_now()
        session.flush()
    return {"registered": True, "ref": use_case.ref, "approved_until": use_case.approved_until}


def find_system(session: Session, ref: str) -> AISystem:
    from govwren.inventory.registry import find

    return find(session, SYSTEM, ref)  # type: ignore[return-value]
