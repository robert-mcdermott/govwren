"""Insight: measures, the portfolio, the unit report, and the dossier."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field

from govwren.access.policy import current
from govwren.api.common import envelope, reading, writing
from govwren.core.errors import Invalid
from govwren.insight import asof, dossier, measures, portfolio, reports
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


class ReportBody(BaseModel):
    title: str = ""
    start: str = Field("", alias="from")
    end: str = Field("", alias="to")
    commentary: str | None = None


@router.get("/reports", summary="The leadership reports made so far")
def list_reports(request: Request) -> dict[str, Any]:
    principal = current(request)
    with reading(request) as session:
        return envelope(reports.listing(session, principal))


@router.post("/reports", status_code=201, summary="Make a leadership report and freeze it")
def create_report(request: Request, body: ReportBody) -> dict[str, Any]:
    """Works the report out for the period and stores it whole. It never changes afterwards:
    opening it reads what was stored, with the SHA-256 it was stored under."""
    principal = current(request)
    values = {
        "title": body.title,
        "from": body.start,
        "to": body.end,
        "commentary": body.commentary,
    }
    with writing(request, principal.actor) as session:
        return envelope(reports.view(session, reports.create(session, principal, values)))


@router.get("/reports/{ref}", summary="One leadership report, as it was frozen")
def show_report(request: Request, ref: str) -> dict[str, Any]:
    with reading(request) as session:
        return envelope(reports.view(session, reports.find(session, ref)))


ON = Query(None, description="The day, as year-month-day")


@router.get("/records/{ref}/as-of", summary="A record as it stood on a date")
def record_as_of(request: Request, ref: str, on: str | None = ON) -> dict[str, Any]:
    """The record at the end of that day, beside how it stands now: each field then and now,
    its owners, what it relied on, and its conditions. Worked out from the history. For
    those who see the whole record."""
    principal = current(request)
    with reading(request) as session:
        return envelope(asof.record(session, principal, *find_any(session, ref), asof.parse(on)))


@router.get("/inventory/as-of", summary="The use cases on the record on a date")
def inventory_as_of(request: Request, on: str | None = ON) -> dict[str, Any]:
    """Every use that had been submitted by the end of that day, with its standing, tier,
    and unit as they were then, and how many have changed standing since."""
    with reading(request) as session:
        return envelope(asof.inventory(session, asof.parse(on)))
