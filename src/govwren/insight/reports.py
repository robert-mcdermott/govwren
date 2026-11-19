"""Leadership reports: the program over a period, frozen when made (RPT-06).

A report is worked out once and stored whole. Opening it later reads what was stored, never
the records as they are now, and its SHA-256 is shown so that anyone can see it is the same.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from govwren.access.principal import Principal
from govwren.assurance import risks
from govwren.core.clock import today, utc_now
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.models import (
    Account,
    Condition,
    ControlImplementation,
    Decision,
    ExceptionRecord,
    Incident,
    Report,
    Risk,
    UseCase,
)
from govwren.db.refs import next_ref
from govwren.events import audit
from govwren.events.chain import jsonable
from govwren.insight import measures, portfolio
from govwren.program import branding

SOON = 60


def _digest(content: Any) -> str:
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


def compose(session: Session, start: date, end: date) -> dict[str, Any]:
    """Everything a report shows, read from the records as they stand now."""
    low = datetime.combine(start, time.min, tzinfo=UTC)
    high = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    by_tier = portfolio.portfolio(session, "tier", start, end)
    by_unit = portfolio.portfolio(session, "unit", start, end)
    groups = by_tier["groups"]
    totals = {
        key: sum(group[key] for group in groups)
        for key in (
            "in_use",
            "approved",
            "lapsed",
            "suspended",
            "in_review",
            "decided",
            "approved_in_period",
            "declined_in_period",
        )
    }
    # A use that was declined is in no group of the portfolio, so decisions are counted here.
    outcomes = Counter(
        session.scalars(
            select(Decision.outcome).where(
                Decision.outcome != "returned",
                Decision.decided_at >= low,
                Decision.decided_at < high,
            )
        )
    )
    totals["decided"] = sum(outcomes.values())
    totals["declined_in_period"] = outcomes.get("declined", 0)
    totals["approved_in_period"] = totals["decided"] - totals["declined_in_period"]
    live = list(session.scalars(select(Risk).where(Risk.status.in_(risks.LIVE))))
    by_level = Counter(risks.current_level(risk) for risk in live)
    owners = dict(
        session.execute(
            select(Account.id, Account.display_name).where(
                Account.id.in_({risk.owner_id for risk in live} - {None} or {0})
            )
        ).all()  # type: ignore[arg-type]
    )
    serious = sorted(
        (risk for risk in live if risks.current_level(risk) in ("high", "critical")),
        key=lambda risk: (risks.current_level(risk) != "critical", risk.id),
    )
    incidents = session.scalars(
        select(Incident).where(Incident.reported_at >= low, Incident.reported_at < high)
    ).all()
    on = today()
    exceptions = session.scalars(
        select(ExceptionRecord).where(ExceptionRecord.status == "approved")
    ).all()
    controls = Counter(
        session.scalars(
            select(ControlImplementation.status).where(ControlImplementation.subject_type.is_(None))
        )
    )
    overdue = session.execute(
        select(func.count())
        .select_from(Condition)
        .where(Condition.status == "open", Condition.due_on < on)
    ).scalar_one()
    ending = session.execute(
        select(func.count())
        .select_from(UseCase)
        .where(
            UseCase.status.in_(("approved", "approved_with_conditions")),
            UseCase.approved_until <= on + timedelta(days=SOON),
        )
    ).scalar_one()
    brand = branding.load(session)
    return jsonable(
        {
            "organization": brand.organization_name,
            "product": brand.product_name,
            "from": start,
            "to": end,
            "totals": totals,
            "measures": measures.compute(session, start, end),
            "by_tier": groups,
            "by_unit": by_unit["groups"][:12],
            "units": len(by_unit["groups"]),
            "risks": {
                "by_level": {level: by_level.get(level, 0) for level in reversed(risks.LEVELS)},
                "serious": [
                    {
                        "ref": risk.ref,
                        "title": risk.title,
                        "level": risks.current_level(risk),
                        "status": risk.status,
                        "owner": owners.get(risk.owner_id or 0),
                    }
                    for risk in serious[:10]
                ],
            },
            "controls": dict(controls),
            "incidents": {
                "reported": len(incidents),
                "by_severity": dict(Counter(i.severity or "not_triaged" for i in incidents)),
                "still_open": sum(1 for i in incidents if i.status in ("open", "contained")),
            },
            "exceptions": {
                "in_force": len(exceptions),
                "granted": sum(
                    1 for e in exceptions if e.decided_at and low <= e.decided_at < high
                ),
            },
            "attention": {
                "lapsed": totals["lapsed"],
                "suspended": totals["suspended"],
                "conditions_overdue": overdue,
                "ending_soon": ending,
            },
        }
    )


def create(session: Session, principal: Principal, values: dict[str, Any]) -> Report:
    """Work a report out and freeze it."""
    if not principal.governs:
        raise PermissionDenied("Governance makes the leadership reports.")
    errors: dict[str, str] = {}
    period: dict[str, date] = {}
    for field in ("from", "to"):
        try:
            period[field] = date.fromisoformat(str(values.get(field) or ""))
        except ValueError:
            errors[field] = "Give a date as year-month-day."
    title = str(values.get("title") or "").strip()
    if not title:
        errors["title"] = "Give the report a title."
    elif len(title) > 200:
        errors["title"] = "Keep the title to 200 characters."
    if not errors and period["from"] > period["to"]:
        errors["to"] = "The period ends before it starts."
    if not errors and period["to"] > today():
        errors["to"] = "A report cannot cover days that have not happened."
    if errors:
        raise Invalid("The report was not made.", errors)
    content = compose(session, period["from"], period["to"])
    with audit.operation(session, "report.create"):
        report = Report(
            ref=next_ref(session, "RPT"),
            title=title,
            period_start=period["from"],
            period_end=period["to"],
            commentary=str(values.get("commentary") or "").strip() or None,
            content=content,
            sha256=_digest(content),
            created_by=principal.account_id,
            created_at=utc_now(),
        )
        session.add(report)
        session.flush()
    return report


def find(session: Session, ref: str) -> Report:
    report = session.scalars(select(Report).where(Report.ref == ref.strip().upper())).first()
    if report is None:
        raise NotFound(f"There is no report {ref}.")
    return report


def _names(session: Session, rows: list[Report]) -> dict[int, str]:
    ids = {row.created_by for row in rows} - {None}
    return dict(
        session.execute(
            select(Account.id, Account.display_name).where(Account.id.in_(ids or {0}))
        ).all()  # type: ignore[arg-type]
    )


def _card(report: Report, names: dict[int, str]) -> dict[str, Any]:
    return {
        "ref": report.ref,
        "title": report.title,
        "from": report.period_start,
        "to": report.period_end,
        "commentary": report.commentary,
        "created_by": names.get(report.created_by or 0),
        "created_at": report.created_at,
        "sha256": report.sha256,
    }


def listing(session: Session, principal: Principal) -> dict[str, Any]:
    rows = list(session.scalars(select(Report).order_by(Report.id.desc())))
    names = _names(session, rows)
    return {"reports": [_card(row, names) for row in rows], "can_create": principal.governs}


def view(session: Session, report: Report) -> dict[str, Any]:
    """The report as it was stored, and whether what is stored still matches its hash."""
    return {
        **_card(report, _names(session, [report])),
        "content": report.content,
        "intact": _digest(report.content) == report.sha256,
    }
