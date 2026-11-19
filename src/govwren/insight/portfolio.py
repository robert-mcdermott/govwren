"""The portfolio: the inventory of uses grouped one way at a time, over a period, with every
figure leading to the records it counts; and one unit's records and obligations on a page."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.core.clock import today
from govwren.core.errors import Invalid, NotFound
from govwren.db.models import (
    AISystem,
    Condition,
    Decision,
    ExceptionRecord,
    Incident,
    IncidentRecord,
    OrgUnit,
    RecordLink,
    Review,
    Risk,
    UseCase,
    Vendor,
)
from govwren.insight.measures import IN_USE, PERIOD_DAYS, _between
from govwren.people import units
from govwren.program import vocab
from govwren.review import service as review

DIMENSIONS = ("unit", "tier", "domain", "data_class", "vendor")
TIER_NAMES = {1: "Minimal", 2: "Moderate", 3: "High", 4: "Critical"}
LIVE = ("approved", "approved_with_conditions")


def _period(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or today()
    start = start or end - timedelta(days=PERIOD_DAYS)
    return (start, end) if start <= end else (end, start)


def _vendors_of(session: Session) -> dict[int, set[tuple[int, str, str]]]:
    """For each use case, the vendors of the systems it uses."""
    found: dict[int, set[tuple[int, str, str]]] = defaultdict(set)
    rows = session.execute(
        select(RecordLink.from_id, Vendor.id, Vendor.name, Vendor.ref)
        .join(AISystem, AISystem.id == RecordLink.to_id)
        .join(Vendor, Vendor.id == AISystem.vendor_id)
        .where(
            RecordLink.from_type == "use_case",
            RecordLink.to_type == "system",
            RecordLink.relation == "uses",
        )
    )
    for use_id, vendor_id, name, ref in rows:
        found[use_id].add((vendor_id, name, ref))
    return found


def portfolio(
    session: Session, by: str, start: date | None = None, end: date | None = None
) -> dict[str, Any]:
    """Uses in the inventory grouped by one dimension. For each group: how many are in use
    and how they stand now, and what was decided for the group in the period."""
    if by not in DIMENSIONS:
        raise Invalid("That is not a way to group the portfolio.", {"by": "Choose a dimension."})
    start, end = _period(start, end)
    low, high = _between(start, end)
    uses = list(
        session.scalars(
            select(UseCase).where(
                UseCase.status.in_((*IN_USE, "in_review", "returned", "submitted"))
            )
        )
    )
    decided: dict[int, list[str]] = defaultdict(list)
    for use_id, outcome in session.execute(
        select(Review.subject_id, Decision.outcome)
        .join(Decision, Decision.review_id == Review.id)
        .where(
            Decision.outcome != "returned", Decision.decided_at >= low, Decision.decided_at < high
        )
    ):
        decided[use_id].append(outcome)
    risky = defaultdict(int)
    from govwren.assurance import risks as risk_register

    for risk in session.scalars(
        select(Risk).where(Risk.subject_type == "use_case", Risk.status != "closed")
    ):
        if risk_register.current_level(risk) in ("high", "critical"):
            risky[risk.subject_id or 0] += 1
    unit_names = {unit.id: unit.name for unit in units.all_units(session)}
    domains = dict(vocab.labels(session, "domains"))
    classes = dict(vocab.labels(session, "data_classes"))
    vendors = _vendors_of(session) if by == "vendor" else {}

    def keys(use: UseCase) -> list[tuple[Any, str, str | None]]:
        if by == "unit":
            return [
                (
                    use.org_unit_id,
                    unit_names.get(use.org_unit_id, "No unit"),
                    f"/use-cases?unit={use.org_unit_id}",
                )
            ]
        if by == "tier":
            if not use.tier:
                return [(0, "Not tiered yet", None)]
            return [
                (
                    use.tier,
                    TIER_NAMES.get(use.tier, f"Tier {use.tier}"),
                    f"/use-cases?tier={use.tier}",
                )
            ]
        if by == "domain":
            if not use.domain:
                return [("", "No area given", None)]
            return [
                (use.domain, domains.get(use.domain, use.domain), f"/use-cases?domain={use.domain}")
            ]
        if by == "data_class":
            if not use.data_class:
                return [("", "No data class given", None)]
            return [
                (
                    use.data_class,
                    classes.get(use.data_class, use.data_class),
                    f"/use-cases?data_class={use.data_class}",
                )
            ]
        found = vendors.get(use.id)
        if not found:
            return [(0, "No supplier: run in-house, or not linked to a tool", None)]
        return [(vendor_id, name, f"/vendors/{ref}") for vendor_id, name, ref in sorted(found)]

    groups: dict[Any, dict[str, Any]] = {}
    for use in uses:
        for key, label, href in keys(use):
            group = groups.setdefault(
                key,
                {
                    "key": key,
                    "label": label,
                    "href": href,
                    "in_use": 0,
                    "approved": 0,
                    "lapsed": 0,
                    "suspended": 0,
                    "in_review": 0,
                    "high_tier": 0,
                    "serious_risks": 0,
                    "decided": 0,
                    "approved_in_period": 0,
                    "declined_in_period": 0,
                },
            )
            if use.status in IN_USE:
                group["in_use"] += 1
                group["high_tier"] += (use.tier or 0) >= 3
            group["approved"] += use.status in LIVE
            group["lapsed"] += use.status == "lapsed"
            group["suspended"] += use.status == "suspended"
            group["in_review"] += use.status in ("in_review", "returned", "submitted")
            group["serious_risks"] += risky.get(use.id, 0)
            outcomes = decided.get(use.id, [])
            group["decided"] += len(outcomes)
            group["approved_in_period"] += sum(
                1 for outcome in outcomes if outcome.startswith("approved")
            )
            group["declined_in_period"] += outcomes.count("declined")
    order = (lambda g: g["key"]) if by == "tier" else (lambda g: (-g["in_use"], g["label"]))
    rows = sorted(groups.values(), key=order)  # type: ignore[arg-type]
    return {
        "by": by,
        "from": start,
        "to": end,
        "groups": rows,
        "total_in_use": sum(1 for use in uses if use.status in IN_USE),
        "largest": max((row["in_use"] for row in rows), default=0),
    }


def unit_report(session: Session, principal: Principal, unit_id: int) -> dict[str, Any]:
    """One unit, with the units beneath it: its uses and how they stand, and everything that
    is waiting on someone there. For its stewards and for those who see everything."""
    unit = session.get(OrgUnit, unit_id)
    if unit is None:
        raise NotFound("There is no such unit.")
    if not (principal.reads_all or principal.stewards_unit(unit_id)):
        raise NotFound("There is no report for you on that unit.")
    scope = units.with_descendants(session, [unit_id])
    uses = list(
        session.scalars(
            select(UseCase)
            .where(UseCase.org_unit_id.in_(scope), UseCase.status != "draft")
            .order_by(UseCase.name)
        )
    )
    ids = [use.id for use in uses] or [0]
    by_id = {use.id: use for use in uses}
    now = today()
    standing: dict[str, int] = defaultdict(int)
    for use in uses:
        standing[use.status] += 1
    waiting = {
        r.subject_id: r
        for r in session.scalars(
            select(Review).where(
                Review.subject_id.in_(ids),
                Review.status == "with_requester",
                Review.kind != "initial",
            )
        )
    }
    conditions = [
        c
        for c in session.scalars(
            select(Condition).where(
                Condition.subject_id.in_(ids),
                Condition.status == "open",
                Condition.kind != "ongoing",
            )
        )
        if by_id[c.subject_id].status in LIVE
    ]
    exceptions = list(
        session.scalars(
            select(ExceptionRecord).where(
                ExceptionRecord.subject_type == "use_case",
                ExceptionRecord.subject_id.in_(ids),
                ExceptionRecord.status.in_(("requested", "approved")),
            )
        )
    )
    incidents = list(
        session.scalars(
            select(Incident)
            .join(IncidentRecord, IncidentRecord.incident_id == Incident.id)
            .where(
                IncidentRecord.subject_type == "use_case",
                IncidentRecord.subject_id.in_(ids),
                Incident.status.in_(("reported", "open", "contained")),
            )
            .distinct()
        )
    )
    names = {u.id: u.name for u in units.all_units(session)}
    soon = now + timedelta(days=60)
    return {
        "unit": {"id": unit.id, "name": unit.name, "kind": unit.kind, "units": len(scope)},
        "counts": {
            "in_use": sum(standing[s] for s in IN_USE),
            "approved": sum(standing[s] for s in LIVE),
            "lapsed": standing["lapsed"],
            "suspended": standing["suspended"],
            "in_review": standing["in_review"] + standing["returned"] + standing["submitted"],
            "retired": standing["retired"],
        },
        "attention": {
            "to_confirm": len(waiting),
            "conditions_overdue": sum(1 for c in conditions if c.due_on and c.due_on < now),
            "conditions_open": len(conditions),
            "ending_soon": sum(
                1
                for u in uses
                if u.status in LIVE and u.approved_until and u.approved_until <= soon
            ),
            "exceptions": len(exceptions),
            "incidents": len(incidents),
        },
        "uses": [
            {
                "ref": use.ref,
                "name": use.name,
                "unit": names.get(use.org_unit_id),
                "tier": use.tier,
                "status": use.status,
                "approved_until": use.approved_until,
                "to_confirm": use.id in waiting,
                "ending_soon": use.status in LIVE
                and bool(use.approved_until and use.approved_until <= soon),
            }
            for use in uses
            if use.status in (*IN_USE, "in_review", "returned", "submitted")
        ],
        "exceptions": [
            {"ref": e.ref, "title": e.title, "status": e.status, "ends_on": e.ends_on}
            for e in exceptions
        ],
        "incidents": [
            {"ref": i.ref, "title": i.title, "status": i.status, "severity": i.severity}
            for i in incidents
        ],
        "attests": bool(review.stewards_of(session, unit_id)),
    }
