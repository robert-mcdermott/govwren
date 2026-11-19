"""Health and what the web app needs before anyone signs in."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from govwren import PRODUCT_NAME, TAGLINE, __version__
from govwren.api.common import database, envelope
from govwren.db import migrate

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/health/live", summary="Is the server process running?")
def live() -> dict[str, Any]:
    return envelope({"status": "ok"})


@router.get("/health/ready", summary="Can the server do its work?")
def ready(request: Request) -> JSONResponse:
    """The database answers and its schema is the one this version expects."""
    engine = database(request).engine
    state = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        if not migrate.is_current(engine):
            state = "outdated"
    except Exception:
        state = "unreachable"
    status = "ok" if state == "ok" else "degraded"
    body = envelope({"status": status, "database": state, "version": __version__})
    return JSONResponse(body, status_code=200 if status == "ok" else 503)


@router.get("/meta", summary="The product's name and version")
def meta() -> dict[str, Any]:
    return envelope({"product": {"name": PRODUCT_NAME, "tagline": TAGLINE}, "version": __version__})
