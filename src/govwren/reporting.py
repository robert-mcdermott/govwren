"""The program dashboard: where things stand, with every figure leading to its records."""

from __future__ import annotations

from datetime import timedelta
from statistics import median
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.core.clock import today, utc_now
from govwren.db.models import AISystem, Condition, Decision, OrgUnit, Review, UseCase, Vendor
from govwren.people import units
from govwren.program import packs, vocab

LIVE = ("approved", "approved_with_conditions")
PIPELINE = ("submitted", "in_review", "returned")
AGES = (
    (0, 5, "5 days or less"),
    (6, 15, "6 to 15 days"),
    (16, 30, "16 to 30 days"),
    (31, None, "Over 30 days"),
)


def _group(session: Session, column: Any, *conditions: Any) -> dict[Any, int]:
    rows = session.execute(select(column, func.count()).where(*conditions).group_by(column)).all()
    return {row[0]: row[1] for row in rows}


def dashboard(session: Session) -> dict[str, Any]:
    """Counts across the whole program. For those who may read everything."""
    not_draft = UseCase.status != "draft"
    by_status = _group(session, UseCase.status, not_draft)
    by_tier = _group(session, UseCase.tier, UseCase.status.in_(LIVE))
    by_stage = _group(session, UseCase.stage, UseCase.status.in_(LIVE))
    by_domain = _group(session, UseCase.domain, UseCase.status.in_(LIVE))
    by_unit = _group(session, UseCase.org_unit_id, UseCase.status.in_(LIVE))

    model = packs.published_scoring(session)
    tiers = {t["level"]: t["label"] for t in model.definition["tiers"]} if model else {}
    all_units = units.all_units(session)
    by_id = {unit.id: unit for unit in all_units}
    root = next((unit for unit in all_units if unit.parent_id is None), None)

    def top(unit: OrgUnit) -> OrgUnit:
        """The unit one step below the organization that this unit sits within."""
        current = unit
        while current.parent_id is not None and (root is None or current.parent_id != root.id):
            current = by_id.get(current.parent_id, current)
            if current.parent_id is None:
                break
        return current

    rolled: dict[int, int] = {}
    for unit_id, number in by_unit.items():
        unit = by_id.get(unit_id)
        if unit is not None:
            rolled[top(unit).id] = rolled.get(top(unit).id, 0) + number

    now, day = utc_now(), today()
    open_reviews = list(
        session.scalars(
            select(Review).where(
                Review.status.in_(("triage", "in_review", "with_requester", "ready"))
            )
        )
    )
    ages = []
    for low, high, label in AGES:
        number = sum(
            1
            for r in open_reviews
            if (now - r.opened_at).days >= low
            and (high is None or (now - r.opened_at).days <= high)
        )
        ages.append({"label": label, "count": number})
    decided = session.execute(
        select(
            Review.opened_at,
            Review.closed_at,
            Review.paused_seconds,
            Decision.outcome,
            Decision.by_rule,
        )
        .join(Decision, Decision.review_id == Review.id)
        .where(
            Review.status == "decided",
            Review.closed_at >= now - timedelta(days=90),
            Decision.outcome != "returned",
        )
    ).all()
    by_people = [
        ((closed - opened).total_seconds() - paused) / 86400
        for opened, closed, paused, _outcome, rule in decided
        if not rule
    ]
    soon = day + timedelta(days=60)
    stage_labels, domain_labels = vocab.labels(session, "stages"), vocab.labels(session, "domains")
    review_words = {
        "triage": "Waiting for triage",
        "in_review": "With reviewers",
        "with_requester": "With the requester",
        "ready": "Ready for a decision",
    }
    status_words = {
        "submitted": "Submitted",
        "in_review": "In review",
        "returned": "With requester",
        "approved": "Approved",
        "approved_with_conditions": "Approved with conditions",
        "declined": "Declined",
        "withdrawn": "Withdrawn",
        "suspended": "Suspended",
        "lapsed": "Lapsed",
        "retired": "Retired",
    }

    def rows(
        counts: dict[Any, int], labels: dict[Any, str], param: str, extra: str = ""
    ) -> list[dict[str, Any]]:
        return [
            {
                "key": key,
                "label": labels.get(key, "Not said" if key is None else str(key)),
                "count": number,
                "href": f"/use-cases?{param}={key}{extra}" if key is not None else None,
            }
            for key, number in sorted(counts.items(), key=lambda item: -item[1])
        ]

    in_use = sum(by_status.get(status, 0) for status in LIVE)
    return {
        "totals": [
            {"label": "Approved uses of AI", "count": in_use, "href": "/use-cases?status=live"},
            {
                "label": "Requests in progress",
                "count": sum(by_status.get(s, 0) for s in PIPELINE),
                "href": "/reviews",
            },
            {
                "label": "Systems in the catalog",
                "href": "/catalog",
                "count": session.execute(
                    select(func.count())
                    .select_from(AISystem)
                    .where(
                        AISystem.catalog_status.in_(("approved", "approved_with_restrictions")),
                        AISystem.status == "active",
                    )
                ).scalar_one(),
            },
            {
                "label": "Vendors",
                "count": session.execute(select(func.count()).select_from(Vendor)).scalar_one(),
                "href": "/vendors",
            },
        ],
        "by_tier": [
            {
                "key": level,
                "label": label,
                "count": by_tier.get(level, 0),
                "href": f"/use-cases?tier={level}&status=live",
            }
            for level, label in tiers.items()
        ],
        "by_status": rows(by_status, status_words, "status"),
        "by_stage": rows(by_stage, stage_labels, "stage", "&status=live"),
        "by_domain": rows(by_domain, domain_labels, "domain", "&status=live"),
        "by_unit": [
            {
                "key": unit_id,
                "label": by_id[unit_id].name,
                "count": number,
                "href": f"/use-cases?unit={unit_id}&status=live",
            }
            for unit_id, number in sorted(rolled.items(), key=lambda item: -item[1])[:10]
        ],
        "reviews": {
            "open": len(open_reviews),
            "by_status": [
                {
                    "key": status,
                    "label": words,
                    "count": sum(1 for r in open_reviews if r.status == status),
                }
                for status, words in review_words.items()
            ],
            "by_age": ages,
            "overdue": sum(1 for r in open_reviews if r.due_on and r.due_on < day),
        },
        "attention": [
            {
                "label": "Reviews past their target date",
                "count": sum(1 for r in open_reviews if r.due_on and r.due_on < day),
                "href": "/reviews",
            },
            {
                "label": "Conditions past their due date",
                "count": session.execute(
                    select(func.count())
                    .select_from(Condition)
                    .where(Condition.status == "open", Condition.due_on < day)
                ).scalar_one(),
                "href": None,
            },
            {
                "label": "Approvals not yet in effect",
                "count": session.execute(
                    select(func.count(func.distinct(Condition.subject_id))).where(
                        Condition.status == "open", Condition.kind == "before_use"
                    )
                ).scalar_one(),
                "href": None,
            },
            {
                "label": "Approvals ending within 60 days",
                "count": session.execute(
                    select(func.count())
                    .select_from(UseCase)
                    .where(
                        UseCase.status.in_(LIVE),
                        UseCase.approved_until <= soon,
                        UseCase.approved_until >= day,
                    )
                ).scalar_one(),
                "href": None,
            },
        ],
        "decisions": {
            "period_days": 90,
            "total": len(decided),
            "by_rule": sum(1 for *_rest, rule in decided if rule),
            "by_people": len(by_people),
            "median_days": round(median(by_people), 1) if by_people else None,
            "definition": "Days from submission to decision for requests decided by "
            "people in the last 90 days, not counting time the request was back with its "
            "requester.",
        },
    }
