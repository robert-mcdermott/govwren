"""Measures: each with its definition and cohort, computed over a period, with a daily
snapshot that gives it a trend."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import jobs
from govwren.core.clock import frozen_at
from govwren.db.engine import Database
from govwren.db.models import MeasureSnapshot
from govwren.insight import measures
from govwren.oversight import campaigns
from govwren.review import service
from tests.conftest import Instance
from tests.people import People
from tests.test_intake import SIMPLE
from tests.test_review import HIGH, MONDAY, get, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
DAY = MONDAY.date()


def by_key(report: dict) -> dict[str, dict]:  # type: ignore[type-arg]
    return {measure["key"]: measure for measure in report["measures"]}


def test_every_measure_says_what_it_counts() -> None:
    assert list(measures.MEASURES) == [
        "turnaround",
        "throughput",
        "coverage",
        "currency",
        "completeness",
    ]
    for measure in measures.MEASURES.values():
        assert len(measure.definition) > 30 and len(measure.cohort) > 30
        assert measure.unit in ("days", "count", "percent") and measure.better in (
            "lower",
            "higher",
        )


def test_measures_over_a_period(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY):
        request(db, people, SIMPLE)  # approved by rule, on the spot
        slow = request(db, people, {**HIGH, "name": "A slower one"})
    with frozen_at(MONDAY + timedelta(days=4)), db.write(governance.actor) as session:
        review = get(session, slow)
        waived = [task.review_function for task in service.tasks_of(session, review)]
        service.triage(session, governance, review, remove=waived, reason="Seen by the committee.")
        service.decide(
            session, governance, review, outcome="approved", rationale="Approved by committee."
        )
    with frozen_at(MONDAY + timedelta(days=10)), db.read() as session:
        seen = by_key(measures.report(session))
        assert (seen["turnaround"]["value"], seen["turnaround"]["denominator"]) == (
            4.0,
            1,
        )  # not the rule's
        assert (seen["throughput"]["value"], seen["throughput"]["numerator"]) == (2.0, 1)
        assert (
            seen["currency"]["value"],
            seen["currency"]["numerator"],
            seen["currency"]["denominator"],
        ) == (100.0, 2, 2)
        assert (seen["coverage"]["value"], seen["coverage"]["numerator"]) == (0.0, 0)
        assert 40 <= seen["completeness"]["value"] <= 100
        earlier = by_key(
            measures.report(session, DAY - timedelta(days=60), DAY - timedelta(days=1))
        )
        assert earlier["throughput"]["value"] == 0 and earlier["turnaround"]["value"] is None
    member = who(db, people, "member")
    with frozen_at(MONDAY + timedelta(days=10)), db.write(governance.actor) as session:
        campaign = campaigns.open_campaign(
            session,
            governance,
            kind="owner_confirmation",
            title="Confirm",
            due_on=DAY + timedelta(days=40),
        )
        ref = campaign.ref
    with frozen_at(MONDAY + timedelta(days=11)), db.write(member.actor) as session:
        campaign = campaigns.find(session, ref)
        mine = [i for i in campaigns.view(session, member, campaign)["items"] if i["mine"]]
        campaigns.answer(
            session, member, campaign, [{"id": mine[0]["id"], "response": "confirmed"}]
        )
        seen = by_key(measures.report(session))
        assert (seen["coverage"]["value"], seen["coverage"]["numerator"]) == (50.0, 1)
    with frozen_at(MONDAY.replace(year=2030)), db.read() as session:  # both approvals have run out
        assert by_key(measures.report(session))["currency"]["value"] == 0.0


def test_a_snapshot_is_stored_once_a_day_and_gives_a_trend(
    instance: Instance, people: People
) -> None:
    db = instance.db
    with frozen_at(MONDAY):
        request(db, people, SIMPLE)
        first = jobs.run_job(db, instance.config, "measures", force=True)
        again = jobs.run_job(db, instance.config, "measures", force=True)
        assert first is not None and first["counts"] == {"measures_stored": 5}
        assert again is not None and again["counts"] == {"measures_stored": 0}
    with frozen_at(MONDAY + timedelta(days=1)):
        jobs.run_job(db, instance.config, "measures", force=True)
        with db.read() as session:
            assert len(session.scalars(select(MeasureSnapshot)).all()) == 10
            trend = by_key(measures.report(session))["throughput"]["trend"]
            assert [point["on"] for point in trend] == [DAY, DAY + timedelta(days=1)]
            assert [point["value"] for point in trend] == [1.0, 1.0]


def test_measures_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    assert as_role("member").get("/api/v1/measures").status_code == 403
    found = as_role("auditor").get(
        "/api/v1/measures", params={"from": "2026-01-01", "to": "2026-03-31"}
    )
    data = found.json()["data"]
    assert (data["from"], data["to"], data["days"]) == ("2026-01-01", "2026-03-31", 89)
    assert [m["key"] for m in data["measures"]] == list(measures.MEASURES)
    assert all(m["definition"] and m["cohort"] and m["trend"] == [] for m in data["measures"])
    assert date.fromisoformat(as_role("governance").get("/api/v1/measures").json()["data"]["to"])
