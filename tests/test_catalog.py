"""The catalog, the one-minute registration of a use that fits, and the program dashboard."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import reporting
from govwren.core.errors import Conflict, Invalid
from govwren.db.engine import Database
from govwren.db.models import Condition, Decision, IntakeDraft, Review
from govwren.inventory import catalog, records
from govwren.inventory.registry import SYSTEM, USE_CASE, VENDOR, find
from tests.people import ME, People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
TERMS = "Sign in with your work account. Do not paste credentials."


@pytest.fixture
def shelf(db: Database, people: People) -> dict[str, str]:
    """Three systems: one approved, one being evaluated, one a member added and nobody listed."""
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(ME.actor) as session:
        vendor = records.create(session, governance, VENDOR, {"name": "Lumen Labs"})
        assistant = records.create(
            session,
            governance,
            SYSTEM,
            {
                "name": "Lumen Assistant",
                "kind": "vendor_product",
                "vendor": vendor.ref,
                "edition": "Enterprise",
                "summary": "A general assistant for writing and analysis.",
                "catalog_status": "approved_with_restrictions",
                "permitted_data_class": "protected",
                "excluded_data_categories": ["genetic"],
                "terms": TERMS,
            },
        )
        coder = records.create(
            session,
            governance,
            SYSTEM,
            {"name": "Anvil Code", "kind": "vendor_product", "catalog_status": "under_evaluation"},
        )
        notebook = records.create(
            session, member, SYSTEM, {"name": "Scribe Notebook", "kind": "open_source"}
        )
        return {"assistant": assistant.ref, "coder": coder.ref, "notebook": notebook.ref}


def use(people: People, **more: Any) -> dict[str, Any]:
    return {
        "name": "Draft grant summaries",
        "org_unit_id": people.units["HALE"],
        "data_class": "internal",
        "data_categories": [],
        "everyday": True,
        **more,
    }


def test_the_catalog_lists_what_was_evaluated_usable_first(
    db: Database, shelf: dict[str, str]
) -> None:
    with db.read() as session:
        rows = catalog.listing(session)
        assert [r["name"] for r in rows] == ["Lumen Assistant", "Anvil Code"]
        first = rows[0]
        assert first["vendor"] == "Lumen Labs" and first["usable"] and first["terms"] == TERMS
        assert first["permitted_data_class"] == "protected"
        assert not rows[1]["usable"]
        assert [r["name"] for r in catalog.listing(session, query="lumen")] == ["Lumen Assistant"]
        assert [r["name"] for r in catalog.listing(session, query="ANVIL")] == ["Anvil Code"]
        assert catalog.listing(session, query="scribe") == []


def test_fit_is_judged_by_data_class_and_excluded_categories(
    db: Database, shelf: dict[str, str]
) -> None:
    with db.read() as session:
        assistant = find(session, SYSTEM, shelf["assistant"])
        assert catalog.fits(session, assistant, "protected", ["personal"]) is None
        assert "up to Protected" in (catalog.fits(session, assistant, "restricted", []) or "")
        assert "genetic data" in (catalog.fits(session, assistant, "internal", ["genetic"]) or "")
        coder = find(session, SYSTEM, shelf["coder"])
        assert "not approved" in (catalog.fits(session, coder, "public", []) or "")


def test_a_use_that_fits_is_approved_at_once_under_the_terms(
    db: Database, people: People, shelf: dict[str, str]
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        assistant = find(session, SYSTEM, shelf["assistant"])
        result = catalog.register(session, member, assistant, use(people))
        assert result["registered"] and result["approved_until"] is not None
    with db.read() as session:
        use_case = find(session, USE_CASE, result["ref"])
        assert use_case.status == "approved_with_conditions"
        assert (use_case.tier, use_case.tier_source) == (1, "catalog")
        review = session.scalars(select(Review).where(Review.subject_id == use_case.id)).one()
        decision = session.scalars(select(Decision).where(Decision.review_id == review.id)).one()
        assert review.status == "decided" and decision.by_rule
        assert "Lumen Assistant" in (decision.rationale or "")
        conditions = list(
            session.scalars(select(Condition).where(Condition.subject_id == use_case.id))
        )
        assert conditions, "the standard conditions of everyday use, and the system's terms"
        assert sum(1 for c in conditions if TERMS in c.text) == 1
        assert catalog.listing(session)[0]["uses"] == 1


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"data_class": "restricted"}, "up to Protected"),
        ({"data_categories": ["genetic"]}, "genetic data"),
        ({"everyday": False}, "closer look"),
    ],
)
def test_a_use_that_does_not_fit_becomes_a_request_with_answers_carried(
    db: Database, people: People, shelf: dict[str, str], change: dict[str, Any], reason: str
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        assistant = find(session, SYSTEM, shelf["assistant"])
        result = catalog.register(session, member, assistant, use(people, **change))
        assert not result["registered"] and reason in result["reason"]
    with db.read() as session:
        use_case = find(session, USE_CASE, result["ref"])
        assert use_case.status == "draft" and use_case.name == "Draft grant summaries"
        assert use_case.org_unit_id == people.units["HALE"]
        draft = session.scalars(
            select(IntakeDraft).where(IntakeDraft.use_case_id == use_case.id)
        ).one()
        given = use(people, **change)
        assert draft.answers["data_class"] == given["data_class"]
        assert draft.answers["systems"] == [shelf["assistant"]]
        assert draft.answers.get("data_categories", []) == given["data_categories"]


def test_registration_says_what_is_missing_and_refuses_unapproved_systems(
    db: Database, people: People, shelf: dict[str, str]
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        assistant = find(session, SYSTEM, shelf["assistant"])
        with pytest.raises(Invalid) as caught:
            catalog.register(session, member, assistant, {"name": " "})
        assert set(caught.value.errors) == {"name", "org_unit_id", "data_class"}
        with pytest.raises(Conflict):
            catalog.register(session, member, find(session, SYSTEM, shelf["coder"]), use(people))


def test_the_dashboard_counts_what_is_there(
    db: Database, people: People, shelf: dict[str, str]
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        assistant = find(session, SYSTEM, shelf["assistant"])
        catalog.register(session, member, assistant, use(people))
        catalog.register(session, member, assistant, use(people, name="Tidy notes"))
        catalog.register(session, member, assistant, use(people, everyday=False))  # a draft
    with db.read() as session:
        figures = reporting.dashboard(session)
    totals = {t["label"]: t["count"] for t in figures["totals"]}
    assert totals["Approved uses of AI"] == 2 and totals["Systems in the catalog"] == 1
    assert totals["Requests in progress"] == 0 and totals["Vendors"] == 1
    assert figures["by_tier"][0]["count"] == 2 and "tier=1" in figures["by_tier"][0]["href"]
    assert sum(row["count"] for row in figures["by_status"]) == 2  # drafts are nobody's business
    assert sum(row["count"] for row in figures["by_unit"]) == 2
    assert figures["decisions"] == {
        **figures["decisions"],
        "total": 2,
        "by_rule": 2,
        "by_people": 0,
    }
    assert figures["decisions"]["median_days"] is None
    assert figures["reviews"]["open"] == 0


def test_over_the_api(as_role: Clients, people: People, shelf: dict[str, str]) -> None:
    member = as_role("member")
    listed = member.get("/api/v1/catalog", params={"q": "assistant"}).json()["data"]
    assert [row["ref"] for row in listed] == [shelf["assistant"]]
    done = member.post(f"/api/v1/catalog/{shelf['assistant']}/register", json=use(people))
    assert done.status_code == 200 and done.json()["data"]["registered"]
    ref = done.json()["data"]["ref"]
    assert member.get(f"/api/v1/use-cases/{ref}").json()["data"]["status"].startswith("approved")
    missing = member.post(f"/api/v1/catalog/{shelf['assistant']}/register", json={"name": "x"})
    assert missing.status_code == 422
    live = member.get("/api/v1/use-cases", params={"status": "live"}).json()["data"]
    assert [row["ref"] for row in live] == [ref]
    assert member.get("/api/v1/dashboard").status_code == 403
    assert as_role("auditor").get("/api/v1/dashboard").json()["data"]["totals"][0]["count"] == 1
