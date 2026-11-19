"""Leadership reports: worked out once, frozen, and reopened unchanged."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from govwren.core.clock import frozen_at
from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Event, Report
from govwren.insight import reports
from tests.people import People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
PERIOD = {"from": "2026-01-01", "to": MONDAY.date().isoformat()}


def test_a_report_is_frozen_and_reopens_unchanged(db: Database, people: People) -> None:
    linked(db, people)  # one minimal use, approved by rule
    governance = who(db, people, "governance")
    with frozen_at(MONDAY + timedelta(hours=1)):
        with db.write(governance.actor) as session:
            made = reports.create(
                session, governance, {**PERIOD, "title": "First quarter", "commentary": " Calm. "}
            )
            ref, first = made.ref, reports.view(session, made)
        assert ref == "RPT-0001" and first["commentary"] == "Calm." and first["intact"]
        content = first["content"]
        assert content["totals"]["in_use"] == 1 and content["totals"]["approved_in_period"] == 1
        assert [m["key"] for m in content["measures"]][:2] == ["turnaround", "throughput"]
        assert content["by_tier"][0]["label"] == "Minimal" and content["units"] == 1
        assert content["attention"] == {
            "lapsed": 0, "suspended": 0, "conditions_overdue": 0, "ending_soon": 0,
        }  # fmt: skip
        request(db, people, HIGH)  # the program moves on
        linked(db, people)
    with db.read() as session:
        again = reports.view(session, reports.find(session, "rpt-0001"))
        assert again["content"] == content and again["sha256"] == first["sha256"]
        assert again["intact"] and len(again["sha256"]) == 64
        assert (
            reports.compose(session, MONDAY.date() - timedelta(days=30), MONDAY.date())["totals"][
                "in_use"
            ]
            == 2
        )  # worked out afresh, it would say something else
        listed = reports.listing(session, who(db, people, "auditor"))
        assert [r["ref"] for r in listed["reports"]] == ["RPT-0001"] and not listed["can_create"]
        event = session.scalars(
            select(Event).where(Event.subject_type == "report", Event.action == "created")
        ).one()
        assert "content" not in event.changes and event.changes["sha256"][1] == first["sha256"]
    with db.engine.begin() as conn:  # what is stored no longer matches its hash
        conn.execute(update(Report).values(content={"totals": {"in_use": 9}}))
    with db.read() as session:
        assert not reports.view(session, reports.find(session, ref))["intact"]


def test_what_a_report_needs(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        for values, field in (
            ({**PERIOD, "title": ""}, "title"),
            ({**PERIOD, "title": "x" * 201}, "title"),
            ({"title": "Q", "from": "soon", "to": PERIOD["to"]}, "from"),
            ({"title": "Q", "from": PERIOD["to"], "to": PERIOD["from"]}, "to"),
            ({"title": "Q", "from": PERIOD["from"], "to": "2030-01-01"}, "to"),
        ):
            with pytest.raises(Invalid) as refused:
                reports.create(session, governance, values)
            assert field in refused.value.errors
        with pytest.raises(PermissionDenied):
            reports.create(session, who(db, people, "auditor"), {**PERIOD, "title": "Q"})


def test_over_the_api(as_role: Clients) -> None:
    governance, auditor = as_role("governance"), as_role("auditor")
    with frozen_at(MONDAY):
        made = governance.post("/api/v1/reports", json={**PERIOD, "title": "Year so far"})
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    shown = auditor.get(f"/api/v1/reports/{ref}")
    assert shown.status_code == 200 and shown.json()["data"]["content"]["to"] == PERIOD["to"]
    assert auditor.get("/api/v1/reports").json()["data"]["reports"][0]["title"] == "Year so far"
    assert auditor.post("/api/v1/reports", json={**PERIOD, "title": "No"}).status_code == 403
    assert governance.post("/api/v1/reports", json={"title": "No dates"}).status_code == 422
    assert auditor.get("/api/v1/reports/RPT-0404").status_code == 404
    assert as_role("member").get("/api/v1/reports").status_code == 403
