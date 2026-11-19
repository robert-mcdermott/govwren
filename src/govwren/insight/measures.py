"""Measures: a few figures about the program, each with the words that define it, the
period it covers, and the cohort it counts. A daily snapshot gives each one a trend."""

from __future__ import annotations

import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from govwren.core.clock import today
from govwren.db.models import Attestation, Decision, MeasureSnapshot, Review, UseCase
from govwren.inventory import tidy
from govwren.inventory.registry import USE_CASE

PERIOD_DAYS = 90
IN_USE = ("approved", "approved_with_conditions", "lapsed", "suspended")


@dataclass(frozen=True)
class Measure:
    key: str
    title: str
    unit: str  # "days", "count", or "percent"
    definition: str
    cohort: str
    better: str  # "lower" or "higher"
    compute: Callable[[Session, date, date], tuple[float | None, int | None, int | None]]


def _between(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1),
    )


def _decided(session: Session, start: date, end: date) -> list[tuple[Review, Decision]]:
    low, high = _between(start, end)
    rows = session.execute(
        select(Review, Decision)
        .join(Decision, Decision.review_id == Review.id)
        .where(
            Review.kind == "initial",
            Decision.outcome != "returned",
            Decision.decided_at >= low,
            Decision.decided_at < high,
        )
    )
    return [(review, decision) for review, decision in rows]


def _turnaround(
    session: Session, start: date, end: date
) -> tuple[float | None, int | None, int | None]:
    days = []
    for review, decision in _decided(session, start, end):
        if decision.by_rule or decision.outcome == "withdrawn":
            continue
        waited = (decision.decided_at - review.opened_at).total_seconds() - (
            review.paused_seconds or 0
        )
        days.append(max(0.0, waited) / 86400)
    return (round(statistics.median(days), 1) if days else None, None, len(days))


def _throughput(
    session: Session, start: date, end: date
) -> tuple[float | None, int | None, int | None]:
    rows = _decided(session, start, end)
    by_rule = sum(1 for _, decision in rows if decision.by_rule)
    return (float(len(rows)), by_rule, len(rows))


def _in_use(session: Session) -> list[UseCase]:
    return list(session.scalars(select(UseCase).where(UseCase.status.in_(IN_USE))))


def _coverage(
    session: Session, start: date, end: date
) -> tuple[float | None, int | None, int | None]:
    low, high = _between(end - timedelta(days=365), end)
    confirmed = set(
        session.scalars(
            select(Attestation.subject_id).where(
                Attestation.subject_type == "use_case",
                Attestation.response.in_(("confirmed", "changed")),
                Attestation.answered_at >= low,
                Attestation.answered_at < high,
            )
        )
    )
    uses = _in_use(session)
    done = sum(1 for use in uses if use.id in confirmed)
    return (round(100 * done / len(uses), 1) if uses else None, done, len(uses))


def _currency(
    session: Session, start: date, end: date
) -> tuple[float | None, int | None, int | None]:
    uses = _in_use(session)
    current = sum(
        1
        for use in uses
        if use.status in ("approved", "approved_with_conditions")
        and (use.approved_until is None or use.approved_until >= end)
    )
    return (round(100 * current / len(uses), 1) if uses else None, current, len(uses))


def _completeness(
    session: Session, start: date, end: date
) -> tuple[float | None, int | None, int | None]:
    uses = _in_use(session)
    scores = [tidy.completeness(session, USE_CASE, use)["score"] for use in uses]
    return (round(statistics.fmean(scores), 1) if scores else None, None, len(scores))


MEASURES: dict[str, Measure] = {
    m.key: m
    for m in (
        Measure("turnaround", "Turnaround", "days",
                "The median number of days from a request being submitted to its decision, "
                "leaving out the time it spent back with the requester.",
                "First reviews decided by a person in the period. Approvals made by a rule and "
                "withdrawn requests are left out.", "lower", _turnaround),
        Measure("throughput", "Throughput", "count",
                "How many requests reached a decision in the period.",
                "First reviews decided in the period, whoever or whatever decided them.",
                "higher", _throughput),
        Measure("coverage", "Coverage", "percent",
                "The share of uses in the inventory that an owner has confirmed in the twelve "
                "months to the end of the period.",
                "Use cases that are approved, lapsed, or suspended. A use counts if an owner "
                "answered an attestation campaign about it as still accurate or as changed.",
                "higher", _coverage),
        Measure("currency", "Currency", "percent",
                "The share of uses in the inventory whose approval is in force at the end of "
                "the period.",
                "Use cases that are approved, lapsed, or suspended. A use counts if it is "
                "approved and its approval has not passed its end date.", "higher", _currency),
        Measure("completeness", "Completeness", "percent",
                "How complete the records of uses in the inventory are, on average.",
                "Use cases that are approved, lapsed, or suspended, each scored by the share of "
                "the fields expected of it that are filled in.", "higher", _completeness),
    )
}  # fmt: skip


def compute(session: Session, start: date, end: date) -> list[dict[str, Any]]:
    out = []
    for measure in MEASURES.values():
        value, numerator, denominator = measure.compute(session, start, end)
        out.append(
            {
                "key": measure.key,
                "title": measure.title,
                "unit": measure.unit,
                "definition": measure.definition,
                "cohort": measure.cohort,
                "better": measure.better,
                "value": value,
                "numerator": numerator,
                "denominator": denominator,
            }
        )
    return out


def report(session: Session, start: date | None = None, end: date | None = None) -> dict[str, Any]:
    """Every measure over a period, with its trend from the snapshots taken so far."""
    end = end or today()
    start = start or end - timedelta(days=PERIOD_DAYS)
    if start > end:
        start, end = end, start
    trends: dict[str, list[dict[str, Any]]] = {key: [] for key in MEASURES}
    for row in session.scalars(
        select(MeasureSnapshot)
        .where(MeasureSnapshot.taken_on <= end)
        .order_by(MeasureSnapshot.taken_on.desc())
        .limit(len(MEASURES) * 60)
    ):
        if row.key in trends and len(trends[row.key]) < 52:
            trends[row.key].append({"on": row.taken_on, "value": row.value})
    measures = compute(session, start, end)
    for measure in measures:
        measure["trend"] = list(reversed(trends[measure["key"]]))
    return {"from": start, "to": end, "days": (end - start).days, "measures": measures}


def snapshot(session: Session, on: date | None = None) -> int:
    """Store each measure as it stands today, over the standard period. Once a day at most."""
    on = on or today()
    taken = set(session.scalars(select(MeasureSnapshot.key).where(MeasureSnapshot.taken_on == on)))
    made = 0
    for measure in compute(session, on - timedelta(days=PERIOD_DAYS), on):
        if measure["key"] in taken:
            continue
        session.add(
            MeasureSnapshot(
                taken_on=on,
                key=measure["key"],
                value=measure["value"],
                numerator=measure["numerator"],
                denominator=measure["denominator"],
            )
        )
        made += 1
    session.flush()
    return made
