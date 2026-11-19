"""Insight: measures, the portfolio, the unit report, and the dossier."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request, Response

from govwren.access.policy import current
from govwren.api.common import envelope, reading
from govwren.core.errors import Invalid
from govwren.insight import dossier, measures, portfolio
from govwren.inventory.registry import find_any

router = APIRouter(prefix="/api/v1", tags=["insight"])
FROM = Query(None, alias="from", description="The first day of the period, as year-month-day")
TO = Query(None, alias="to", description="The last day of the period, as year-month-day")


def _period(start: str | None, end: str | None) -> tuple[date | None, date | None]:
    try:
        return (
            date.fromisoformat(start) if start else None,
            date.fromisoformat(end) if end else None,
        )
    except ValueError as exc:
        raise Invalid(
            "That period is not valid.", {"from": "Give dates as year-month-day."}
        ) from exc


@router.get("/measures", summary="The program's measures, each with its definition")
def show_measures(
    request: Request, start: str | None = FROM, end: str | None = TO
) -> dict[str, Any]:
    """Turnaround, throughput, coverage, currency, and completeness over a period, which is
    the last ninety days unless given. Each comes with the sentence that defines it, the
    cohort it counts, and its trend from the snapshots taken each day."""
    first, last = _period(start, end)
    with reading(request) as session:
        return envelope(measures.report(session, first, last))


@router.get("/portfolio", summary="The portfolio, grouped one way")
def show_portfolio(
    request: Request, by: str = "unit", start: str | None = FROM, end: str | None = TO
) -> dict[str, Any]:
    """Uses in the inventory grouped by ``unit``, ``tier``, ``domain``, ``data_class``, or
    ``vendor``. Each group says how many uses it holds and how they stand now, and what was
    decided for it in the period, with the address of the list that shows them."""
    first, last = _period(start, end)
    with reading(request) as session:
        return envelope(portfolio.portfolio(session, by, first, last))


@router.get("/units/{unit_id}/report", summary="One unit on a page")
def unit_report(request: Request, unit_id: int) -> dict[str, Any]:
    """The unit and the units beneath it: its uses and how they stand, and what is waiting
    on someone there. For the unit's stewards, and for those who see everything."""
    principal = current(request)
    with reading(request) as session:
        return envelope(portfolio.unit_report(session, principal, unit_id))


@router.get("/records/{ref}/dossier", summary="Everything about one record")
def show_dossier(request: Request, ref: str) -> dict[str, Any]:
    """The record with its answers, reviews, decisions, conditions, findings, risks,
    controls, exceptions, incidents, assessments, evidence, and history, cut to what you may
    see. For those who see the whole record."""
    principal = current(request)
    with reading(request) as session:
        return envelope(dossier.build(session, principal, *find_any(session, ref)))


@router.get(
    "/records/{ref}/dossier/package",
    summary="The dossier as a package with a manifest",
    response_class=Response,
)
def download_dossier(request: Request, ref: str) -> Response:
    """A zip holding the dossier as data and as a page to print, each evidence file, and
    ``manifest.json``, which lists every file with its SHA-256 and names the event the
    history ended at. ``govwren dossier verify`` checks a package against its manifest."""
    principal = current(request)
    with reading(request) as session:
        document = dossier.build(session, principal, *find_any(session, ref))
        data = dossier.package(session, request.app.state.home.files, document)
    name = f"{document['record']['ref']}-dossier.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={
            "content-disposition": f'attachment; filename="{name}"',
            "cache-control": "private, no-store",
        },
    )
