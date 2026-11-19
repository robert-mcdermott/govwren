"""The risk register: risks on a record or on the organization, scored before and after
treatment, owned, drawn from a library, raised from a review, and shown as findings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.assurance import library, risks
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import RiskStatement
from govwren.inventory import history
from govwren.inventory.registry import SYSTEM, USE_CASE, find
from govwren.oversight import findings
from tests.people import ME, People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, notices, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
RISK: dict[str, Any] = {
    "library_key": "plausible-but-wrong",
    "inherent_likelihood": 4,
    "inherent_impact": 3,
}


def test_levels_come_from_likelihood_times_impact() -> None:
    assert [risks.level(a, b) for a, b in ((1, 4), (3, 3), (4, 4), (5, 4))] == [
        "low",
        "moderate",
        "high",
        "critical",
    ]
    assert risks.level(None, 3) is None


def test_the_library_is_loaded_with_the_program_and_checks_what_it_is_given(db: Database) -> None:
    with db.read() as session:
        listed = library.listing(session)
        assert len(listed) >= 40 and len({row["category"] for row in listed}) == 8
        assert all(row["title"] and row["description"] and row["treatment"] for row in listed)
    pack = library.builtin()
    assert library.problems(pack) == []
    assert library.problems({"pack": {"kind": "framework"}}) == ["This is not a risk library pack."]
    broken = {
        **pack,
        "risks": [{"key": "a", "title": "A", "description": "B", "category": "nope"}, {}],
    }
    assert len(library.problems(broken)) == 2
    with db.write(ME.actor) as session:
        library.load(session, {**pack, "risks": pack["risks"][:-1]})  # one fewer: it is retired
        gone = session.scalars(select(RiskStatement).where(RiskStatement.retired.is_(True))).all()
        assert [row.key for row in gone] == [pack["risks"][-1]["key"]]
        with pytest.raises(Invalid):
            library.load(session, broken)


def test_a_risk_is_drawn_from_the_library_scored_treated_and_closed(
    db: Database, people: People
) -> None:
    use_ref, _, _ = linked(db, people)
    member, governance, reviewer = (
        who(db, people, r) for r in ("member", "governance", "reviewer")
    )
    with frozen_at(MONDAY), db.write(member.actor) as session:
        use_case = find(session, USE_CASE, use_ref)
        with pytest.raises(PermissionDenied):
            risks.add(session, reviewer, RISK, record=(USE_CASE, use_case))
        with pytest.raises(PermissionDenied):  # a risk to the organization is governance's
            risks.add(session, member, RISK)
        with pytest.raises(Invalid) as bad:
            risks.add(
                session,
                member,
                {"title": "x", "inherent_likelihood": 9},
                record=(USE_CASE, use_case),
            )
        assert set(bad.value.errors) == {
            "title",
            "category",
            "inherent_likelihood",
            "inherent_impact",
        }
        risk = risks.add(session, member, RISK, record=(USE_CASE, use_case))
        assert (risk.ref, risk.status, risk.owner_id) == ("RSK-0001", "open", member.account_id)
        assert risk.title == "Output that reads well and is wrong is relied on"
        seen = risks.view(session, member, risk)
        assert (seen["level"], seen["category_label"]) == ("high", "Accuracy and reliability")
        with pytest.raises(PermissionDenied):  # accepting a risk as it stands is governance's
            risks.update(session, member, risk, {"treatment": "accept"})
        risks.update(
            session,
            member,
            risk,
            {
                "treatment": "mitigate",
                "treatment_note": "Every summary is checked against the notes.",
                "residual_likelihood": 2,
                "residual_impact": 3,
                "review_on": "2027-05-01",
            },
        )
        seen = risks.view(session, member, risk)
        assert (seen["status"], seen["level"], seen["inherent"]["level"]) == (
            "treated",
            "moderate",
            "high",
        )
        with pytest.raises(PermissionDenied):
            risks.close(session, member, risk, "It no longer applies to us.")
    with db.write(governance.actor) as session:
        risk = risks.find(session, "RSK-0001")
        with pytest.raises(Invalid):
            risks.close(session, governance, risk, "no")
        risks.close(
            session, governance, risk, "The tool was replaced by one that cites its sources."
        )
        with pytest.raises(Conflict):
            risks.update(session, governance, risk, {"inherent_impact": 5})
        titles = [
            e["title"]
            for e in history.for_record(session, USE_CASE, find(session, USE_CASE, use_ref))
        ]
        assert {"Risk RSK-0001 recorded", "Risk RSK-0001 treated", "Risk RSK-0001 closed"} <= set(
            titles
        )


def test_the_register_shows_each_person_what_they_may_see_and_counts_the_grid(
    db: Database, people: People
) -> None:
    use_ref, system_ref, _ = linked(db, people)
    governance, member, reviewer = (
        who(db, people, r) for r in ("governance", "member", "reviewer")
    )
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        risks.add(session, governance, RISK, record=(USE_CASE, find(session, USE_CASE, use_ref)))
        risks.add(
            session,
            governance,
            {
                "library_key": "single-supplier",
                "inherent_likelihood": 2,
                "inherent_impact": 5,
                "owner_id": member.account_id,
            },
        )
        risks.add(
            session,
            governance,
            {"library_key": "service-withdrawn", "inherent_likelihood": 1, "inherent_impact": 2},
            record=(SYSTEM, find(session, SYSTEM, system_ref)),
        )
    assert "A risk is yours to own: Critical work depends on one supplier" in notices(
        db, people, "member"
    )
    with db.read() as session:
        everything = risks.register(session, governance)
        assert [r["level"] for r in everything["risks"]] == ["high", "high", "low"]
        assert everything["by_level"] == {"low": 1, "moderate": 0, "high": 2, "critical": 0}
        assert (
            everything["grid"][2][3] == 1 and everything["grid"][4][1] == 1
        )  # [impact-1][likelihood-1]
        assert [r["organization"] for r in everything["risks"]].count(True) == 1
        mine = risks.register(session, member, mine=True)
        assert [r["title"] for r in mine["risks"]] == ["Critical work depends on one supplier"]
        # anyone sees the risk on a tool in the catalog, and no more than that
        assert [r["ref"] for r in risks.register(session, reviewer)["risks"]] == ["RSK-0003"]
        with pytest.raises(NotFound):
            risks.view(session, reviewer, risks.find(session, "RSK-0001"))
        on_record = risks.register(
            session, governance, record=(USE_CASE, find(session, USE_CASE, use_ref))
        )
        assert len(on_record["risks"]) == 1


def test_a_serious_risk_is_a_finding_and_is_inherited(db: Database, people: People) -> None:
    use_ref, system_ref, _ = linked(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        system = find(session, SYSTEM, system_ref)
        risk = risks.add(
            session,
            governance,
            {"library_key": "service-withdrawn", "inherent_likelihood": 4, "inherent_impact": 5},
            record=(SYSTEM, system),
        )
        own = findings.for_record(session, governance, SYSTEM, system)["own"]
        assert [(f["kind"], f["tone"], f["ref"]) for f in own] == [("risk", "danger", risk.ref)]
        inherited = findings.for_record(
            session, governance, USE_CASE, find(session, USE_CASE, use_ref)
        )
        assert [f["from"]["ref"] for f in inherited["inherited"]] == [system_ref]
        risks.update(
            session,
            governance,
            risk,
            {"treatment": "mitigate", "residual_likelihood": 1, "residual_impact": 5},
        )
        assert findings.for_record(session, governance, SYSTEM, system)["own"] == []  # moderate now


def test_risks_over_the_api_and_from_a_review(
    db: Database, people: People, as_role: Clients
) -> None:
    with frozen_at(MONDAY):
        review_ref = request(db, people, HIGH)
    governance, member, reviewer = as_role("governance"), as_role("member"), as_role("reviewer")
    assert len(member.get("/api/v1/risk-library").json()["data"]) >= 40
    assert governance.post(f"/api/v1/reviews/{review_ref}/triage", json={}).status_code == 200
    body = {
        "review": review_ref,
        "library_key": "review-in-name-only",
        "inherent_likelihood": 3,
        "inherent_impact": 4,
    }
    assert member.post("/api/v1/risks", json=body).status_code == 403  # not a reviewer of it
    made = reviewer.post("/api/v1/risks", json=body)
    assert made.status_code == 201, made.text
    risk = made.json()["data"]
    assert risk["source"] == f"Review {review_ref}" and risk["owner"] == "Member Person"
    assert risk["level"] == "high"
    seen = governance.get(f"/api/v1/risks/{risk['ref']}").json()["data"]
    assert seen["record"]["type"] == "use_case"
    listed = member.get("/api/v1/risks", params={"mine": "true"}).json()
    assert [row["ref"] for row in listed["data"]] == [risk["ref"]] and listed["meta"]["by_level"][
        "high"
    ] == 1
    treated = member.patch(
        f"/api/v1/risks/{risk['ref']}",
        json={
            "treatment": "mitigate",
            "treatment_note": "Reviewers are rotated weekly.",
            "residual_likelihood": 2,
            "residual_impact": 3,
        },
    )
    assert treated.json()["data"]["status"] == "treated"
    assert (
        member.post(
            f"/api/v1/risks/{risk['ref']}/close", json={"reason": "No longer applies."}
        ).status_code
        == 403
    )
    organization = governance.post(
        "/api/v1/risks",
        json={
            "library_key": "inventory-incomplete",
            "inherent_likelihood": 4,
            "inherent_impact": 3,
        },
    )
    assert organization.json()["data"]["organization"] is True
    closed = governance.post(
        f"/api/v1/risks/{risk['ref']}/close", json={"reason": "It no longer applies here."}
    )
    assert closed.json()["data"]["status"] == "closed"
