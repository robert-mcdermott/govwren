"""The catalog: the AI systems the organization has evaluated, what each may be used with,
and the one-minute path for registering a use that fits (FDR-01 to FDR-03)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import utc_now
from govwren.core.errors import Conflict, Invalid, NotFound
from govwren.db.models import (
    Account,
    AISystem,
    Condition,
    Decision,
    EvaluationRequest,
    Model,
    RecordLink,
    Vendor,
)
from govwren.events import audit
from govwren.inventory import agreements, records
from govwren.inventory.registry import MODEL, SYSTEM, USE_CASE, find_any
from govwren.program import vocab

LISTED = ("approved", "approved_with_restrictions", "under_evaluation", "not_approved")
USABLE = ("approved", "approved_with_restrictions")
ORDER = {status: index for index, status in enumerate(LISTED)}


def listing(session: Session, *, query: str = "") -> list[dict[str, Any]]:
    """Every tool and model in the catalog, approved ones first. Visible to everyone signed in."""
    like = f"%{query.strip().lower()}%" if query.strip() else None
    found: list[tuple[str, Any]] = []
    for kind, model in (("system", AISystem), ("model", Model)):
        statement = select(model).where(
            model.catalog_status.in_(LISTED), model.status == "active", model.restricted.is_(False)
        )
        if like:
            vendors = select(Vendor.id).where(func.lower(Vendor.name).like(like))
            extra = AISystem.edition if model is AISystem else Model.provider
            statement = statement.where(
                or_(
                    func.lower(model.name).like(like),
                    func.lower(func.coalesce(model.summary, "")).like(like),
                    func.lower(func.coalesce(extra, "")).like(like),
                    model.vendor_id.in_(vendors),
                )
            )
        found += [(kind, row) for row in session.scalars(statement)]
    found.sort(key=lambda item: (ORDER[item[1].catalog_status], item[1].name.lower(), item[0]))
    vendor_ids = {row.vendor_id for _, row in found if row.vendor_id}
    vendors_by_id = (
        {v.id: v.name for v in session.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))}
        if vendor_ids
        else {}
    )
    uses: dict[tuple[str, int], int] = {
        (to_type, to_id): number
        for to_type, to_id, number in session.execute(
            select(RecordLink.to_type, RecordLink.to_id, func.count())
            .where(RecordLink.relation == records.USES)
            .group_by(RecordLink.to_type, RecordLink.to_id)
        )
    }
    out = []
    for kind, row in found:
        system = kind == "system"
        out.append(
            {
                "type": kind,
                "ref": row.ref,
                "name": row.name,
                "edition": row.edition if system else row.version_label,
                "summary": row.summary,
                "kind": row.kind,
                "origin": None if system else row.origin,
                "vendor": vendors_by_id.get(row.vendor_id or 0)
                or (None if system else row.provider),
                "catalog_status": row.catalog_status,
                "permitted_data_class": row.permitted_data_class,
                "excluded_data_categories": row.excluded_data_categories,
                "health_agreement": agreements.health_standing(session, row) if system else None,
                "terms": row.terms,
                "trains_on_inputs": (row.data_handling or {}).get("trains_on_inputs")
                if system
                else None,
                "uses": uses.get((kind, row.id), 0),
                "usable": row.catalog_status in USABLE,
            }
        )
    return out


def fits(
    session: Session, system: AISystem | Model, data_class: str | None, categories: list[str]
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
    if (
        agreements.HEALTH_DATA in categories
        and isinstance(system, AISystem)
        and agreements.rule_on(session)
    ):
        standing = agreements.health_standing(session, system)
        if standing not in agreements.HEALTH_OK:
            return f"{agreements.HEALTH_WORDS[standing]}, and this use involves health information."
    return None


def register(
    session: Session, principal: Principal, system: AISystem | Model, values: Mapping[str, Any]
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
            "systems": [system.ref] if isinstance(system, AISystem) else None,
            "other_tool": None if isinstance(system, AISystem) else f"{system.name} ({system.ref})",
            "data_class": data_class,
            "data_categories": categories,
        }
        for section in version.schema["sections"]:
            for question in section["questions"]:
                if question.get("maps_to") in targets and targets[question["maps_to"]]:
                    answers[question["key"]] = targets[question["maps_to"]]
                elif question["key"] == "other_tool" and targets["other_tool"]:
                    answers["other_tool"] = targets["other_tool"]
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
        if isinstance(system, AISystem):
            records.set_systems(session, principal, use_case, [system.ref])
        else:
            from govwren.inventory import links

            links.add(session, principal, use_case.ref, records.USES, system.ref)
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


def find_system(session: Session, ref: str) -> AISystem | Model:
    """The tool or model in the catalog with this reference."""
    record_type, record = find_any(session, ref)
    if record_type not in (SYSTEM, MODEL):
        raise NotFound(f"There is nothing in the catalog called {ref}.")
    return record  # type: ignore[return-value]


# --- Asking for a tool to be evaluated ----------------------------------------------------

DECIDED = ("approved", "approved_with_restrictions", "not_approved")


def ask(session: Session, principal: Principal, values: Mapping[str, Any]) -> dict[str, Any]:
    """Ask for a tool that is not in the catalog to be looked at. If someone has already
    asked about it, this adds a voice to theirs."""
    from govwren.review import service as review

    name = str(values.get("name") or "").strip()
    reason = str(values.get("reason") or "").strip()
    errors = {}
    if not name or len(name) > 200:
        errors["name"] = "Say which tool, in up to 200 characters."
    if len(reason) < 10:
        errors["reason"] = "Say what you want to use it for, so that it can be judged."
    if errors or principal.account_id is None:
        raise Invalid("The request was not sent.", errors or {"name": "Sign in first."})
    system = session.scalars(
        select(AISystem)
        .where(func.lower(AISystem.name) == name.lower(), AISystem.restricted.is_(False))
        .order_by(AISystem.id)
    ).first()
    if system is not None and system.catalog_status in DECIDED:
        raise Conflict(f"{system.name} has already been evaluated. Look it up in the catalog.")
    with audit.operation(session, "catalog.ask"):
        if system is None:
            system = records.create(
                session,
                principal,
                SYSTEM,
                {
                    "name": name,
                    "kind": "vendor_product",
                    "url": values.get("url") or None,
                    "summary": str(values.get("summary") or "").strip() or None,
                },
            )
        already = session.scalars(
            select(EvaluationRequest).where(
                EvaluationRequest.system_id == system.id,
                EvaluationRequest.requested_by == principal.account_id,
                EvaluationRequest.status == "open",
            )
        ).first()
        if already is None:
            session.add(
                EvaluationRequest(
                    system_id=system.id,
                    requested_by=principal.account_id,
                    reason=reason,
                    status="open",
                    created_at=utc_now(),
                )
            )
            review.notify(
                session,
                review.holders(session, "governance"),
                "evaluation",
                f"{principal.name} asked for {system.name} to be evaluated",
                f"/systems/{system.ref}",
                skip=principal.account_id,
            )
        session.flush()
    return {"ref": system.ref, "name": system.name}


def asked(session: Session, principal: Principal) -> list[dict[str, Any]]:
    """Open requests for evaluation: all of them for those who keep the catalog, and
    otherwise the person's own."""
    statement = (
        select(EvaluationRequest, AISystem, Account)
        .join(AISystem, AISystem.id == EvaluationRequest.system_id)
        .join(Account, Account.id == EvaluationRequest.requested_by)
        .where(EvaluationRequest.status == "open")
        .order_by(EvaluationRequest.created_at)
    )
    if not principal.reads_all:
        statement = statement.where(EvaluationRequest.requested_by == principal.account_id)
    grouped: dict[int, dict[str, Any]] = {}
    for request, system, account in session.execute(statement):
        entry = grouped.setdefault(
            system.id,
            {
                "ref": system.ref,
                "name": system.name,
                "catalog_status": system.catalog_status,
                "first_asked": request.created_at,
                "requests": [],
            },
        )
        entry["requests"].append(
            {"by": account.display_name, "reason": request.reason, "at": request.created_at}
        )
    return sorted(grouped.values(), key=lambda e: (-len(e["requests"]), e["first_asked"]))


def answer_requests(session: Session, system: AISystem) -> None:
    """A tool that has been evaluated answers everyone who asked about it."""
    from govwren.review import service as review

    if system.catalog_status not in DECIDED:
        return
    waiting = session.scalars(
        select(EvaluationRequest).where(
            EvaluationRequest.system_id == system.id, EvaluationRequest.status == "open"
        )
    ).all()
    if not waiting:
        return
    words = (
        "is not approved for use" if system.catalog_status == "not_approved" else "is now approved"
    )
    for request in waiting:
        request.status, request.closed_at = "answered", utc_now()
    review.notify(
        session,
        {request.requested_by for request in waiting},
        "evaluation",
        f"{system.name} {words}. See the catalog for what it may be used with.",
        f"/systems/{system.ref}",
    )
    session.flush()
