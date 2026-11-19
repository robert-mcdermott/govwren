"""The portfolio grouped one way at a time, and one unit on a page."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from govwren import jobs
from govwren.core.clock import frozen_at
from govwren.core.errors import Invalid, NotFound
from govwren.db.engine import Database
from govwren.insight import portfolio
from govwren.oversight import schedule
from tests.people import People
from tests.test_changes import linked
from tests.test_intake import SIMPLE
from tests.test_review import HIGH, MONDAY, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def test_the_portfolio_groups_uses_and_counts_what_was_decided(
    db: Database, people: People
) -> None:
    linked(db, people)  # one minimal use, approved by rule
    with frozen_at(MONDAY):
        request(db, people, HIGH)  # one high-tier use, still in review
    with frozen_at(MONDAY + timedelta(days=3)), db.read() as session:
        by_tier = portfolio.portfolio(session, "tier")
        assert [(g["label"], g["in_use"], g["in_review"]) for g in by_tier["groups"]] == [
            ("Minimal", 1, 0),
            ("High", 0, 1),
        ]
        assert by_tier["groups"][0]["href"] == "/use-cases?tier=1" and by_tier["total_in_use"] == 1
        assert (by_tier["groups"][0]["decided"], by_tier["groups"][0]["approved_in_period"]) == (
            1,
            1,
        )
        by_unit = portfolio.portfolio(session, "unit")
        assert [(g["label"], g["in_use"], g["href"]) for g in by_unit["groups"]] == [
            ("Hale Lab", 1, f"/use-cases?unit={people.units['HALE']}")
        ]
        assert [g["label"] for g in portfolio.portfolio(session, "data_class")["groups"]] == [
            "Internal"
        ]
        assert portfolio.portfolio(session, "vendor")["groups"][0]["label"].startswith(
            "No supplier"
        )
        with pytest.raises(Invalid):
            portfolio.portfolio(session, "colour")
        earlier = portfolio.portfolio(
            session, "tier", MONDAY.date() - timedelta(days=30), MONDAY.date() - timedelta(days=1)
        )
        assert (
            earlier["groups"][0]["decided"] == 0 and earlier["groups"][0]["in_use"] == 1
        )  # standing is now


def test_a_unit_report_is_for_its_stewards(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        request(db, people, SIMPLE)
    steward, member, auditor = (who(db, people, r) for r in ("steward", "member", "auditor"))
    with frozen_at(MONDAY.replace(year=2029, month=12)):  # after the approval has run out
        with db.write(jobs.SCHEDULER) as session:
            schedule.run_all(session)
        with db.read() as session:
            seen = portfolio.unit_report(session, steward, people.units["NEURO"])
            assert seen["unit"] == {
                "id": people.units["NEURO"],
                "name": "Neuroscience",
                "kind": "division",
                "units": 2,
            }
            assert (
                seen["counts"]["in_use"],
                seen["counts"]["lapsed"],
                seen["attention"]["to_confirm"],
            ) == (1, 1, 1)
            assert [(u["unit"], u["status"], u["to_confirm"]) for u in seen["uses"]] == [
                ("Hale Lab", "lapsed", True)
            ]
            assert (
                portfolio.unit_report(session, auditor, people.units["HALE"])["counts"]["in_use"]
                == 1
            )
            for nobody in (member,):
                with pytest.raises(NotFound):
                    portfolio.unit_report(session, nobody, people.units["HALE"])
            with pytest.raises(NotFound):  # a steward of Neuroscience, not of Cancer Biology
                portfolio.unit_report(session, steward, people.units["CANCER"])


def test_portfolio_and_unit_report_over_the_api(
    db: Database, people: People, as_role: Clients
) -> None:
    with frozen_at(MONDAY):
        request(db, people, SIMPLE)
    auditor, steward, member = as_role("auditor"), as_role("steward"), as_role("member")
    assert member.get("/api/v1/portfolio").status_code == 403
    assert auditor.get("/api/v1/portfolio", params={"by": "colour"}).status_code == 422
    found = auditor.get(
        "/api/v1/portfolio", params={"by": "domain", "from": "2026-01-01", "to": "2026-12-31"}
    )
    assert [g["label"] for g in found.json()["data"]["groups"]] == ["Research"]
    report = steward.get(f"/api/v1/units/{people.units['HALE']}/report")
    assert report.status_code == 200 and report.json()["data"]["counts"]["in_use"] == 1
    assert member.get(f"/api/v1/units/{people.units['HALE']}/report").status_code == 404
