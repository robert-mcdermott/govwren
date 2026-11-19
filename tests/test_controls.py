"""Controls: defined once in a library, applying to the program or to records by rule, each
with a status, an owner, and a date it is next checked."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.assurance import controls, risks
from govwren.core.clock import frozen_at
from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Control, ControlImplementation
from govwren.inventory import history
from govwren.inventory.registry import MODEL, SYSTEM, USE_CASE, find
from tests.people import ME, People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, notices, request, who
from tests.test_schedule import at, use_case_of, watch

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def test_the_library_is_loaded_and_checked(db: Database) -> None:
    pack = controls.builtin()
    assert controls.problems(pack) == []
    assert controls.problems({"pack": {"kind": "risk_library"}}) == [
        "This is not a control library pack."
    ]
    bad = {
        **pack,
        "controls": [
            {"key": "a", "title": "A", "statement": "B", "category": "know", "scope": "record"},
            {"key": "b", "title": "B", "statement": "C", "category": "nope", "scope": "everywhere"},
        ],
    }
    assert len(controls.problems(bad)) == 3
    with db.read() as session:
        rows = session.scalars(select(Control)).all()
        assert len(rows) >= 30 and {row.scope for row in rows} == {"program", "record"}
        assert len({row.category for row in rows}) == 8
    with db.write(ME.actor) as session:
        controls.load(session, {**pack, "controls": pack["controls"][1:]})
        assert session.scalars(select(Control.key).where(Control.retired.is_(True))).all() == [
            pack["controls"][0]["key"]
        ]


def test_controls_apply_to_a_record_by_rule_and_nothing_is_copied(
    db: Database, people: People
) -> None:
    use_ref, system_ref, model_ref = linked(db, people)  # a minimal-tier use
    with frozen_at(MONDAY):
        high = request(db, people, HIGH)
    governance = who(db, people, "governance")
    with db.read() as session:
        low = {
            c["key"]
            for c in controls.for_record(
                session, governance, USE_CASE, find(session, USE_CASE, use_ref)
            )
        }
        more = {
            c["key"]
            for c in controls.for_record(session, governance, USE_CASE, use_case_of(session, high))
        }
        assert (
            "named-owner" in low and "human-checks-output" not in low
        )  # that one is for tier 2 up
        assert {"human-checks-output", "performance-by-group", "stop-tested"} <= more
        assert low < more
        on_model = {
            c["key"]
            for c in controls.for_record(
                session, governance, MODEL, find(session, MODEL, model_ref)
            )
        }
        assert {
            "version-pinned",
            "model-source-known",
        } <= on_model and "named-owner" not in on_model
        on_system = controls.for_record(
            session, governance, SYSTEM, find(session, SYSTEM, system_ref)
        )
        assert all(c["status"] == "not_started" for c in on_system)
        assert (
            session.scalars(select(ControlImplementation)).all() == []
        )  # nothing until someone says


def test_saying_how_a_control_stands(db: Database, people: People) -> None:
    use_ref, _, _ = linked(db, people)
    governance, member, reviewer = (
        who(db, people, r) for r in ("governance", "member", "reviewer")
    )
    with frozen_at(MONDAY), db.write(member.actor) as session:
        use_case = find(session, USE_CASE, use_ref)
        owner = controls.find(session, "named-owner")
        with pytest.raises(PermissionDenied):
            controls.set_standing(
                session, reviewer, owner, {"status": "implemented"}, record=(USE_CASE, use_case)
            )
        with pytest.raises(Invalid):  # it does not apply to a minimal-tier use
            controls.set_standing(
                session,
                member,
                controls.find(session, "stop-tested"),
                {"status": "implemented"},
                record=(USE_CASE, use_case),
            )
        with pytest.raises(
            Invalid
        ) as bad:  # saying it does not apply is governance's, with a reason
            controls.set_standing(
                session, member, owner, {"status": "not_applicable"}, record=(USE_CASE, use_case)
            )
        assert set(bad.value.errors) == {"status", "note"}
        row = controls.set_standing(
            session,
            member,
            owner,
            {"status": "implemented", "note": "Tomas, with Ana as deputy."},
            record=(USE_CASE, use_case),
        )
        assert row.owner_id == member.account_id and row.next_check_on == MONDAY.date().replace(
            year=2027
        )
        with pytest.raises(PermissionDenied):  # a program control is governance's
            controls.set_standing(
                session, member, controls.find(session, "inventory-kept"), {"status": "implemented"}
            )
        seen = {c["key"]: c for c in controls.for_record(session, member, USE_CASE, use_case)}
        assert (
            seen["named-owner"]["status_label"] == "In place"
            and seen["named-owner"]["owner"] == "Member Person"
        )
        titles = [e["title"] for e in history.for_record(session, USE_CASE, use_case)]
        assert "Control in place: The use has a named, accountable owner" in titles
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        controls.set_standing(
            session,
            governance,
            controls.find(session, "inventory-kept"),
            {"status": "in_progress", "note": "Two divisions still to load."},
        )
        listed = {c["key"]: c for c in controls.library(session, governance)}
        assert (
            listed["inventory-kept"]["status"] == "in_progress"
            and listed["inventory-kept"]["can_set"]
        )
        assert (listed["named-owner"]["applicable"], listed["named-owner"]["in_place"]) == (1, 1)
        detail = controls.detail(session, governance, controls.find(session, "named-owner"))
        assert [r["ref"] for r in detail["records"]] == [use_ref]
        assert {r["key"] for r in detail["risks"]} == {"nobody-owns-it", "knowledge-leaves"}


def test_a_control_in_place_is_checked_again_when_due(db: Database, people: People) -> None:
    use_ref, _, _ = linked(db, people)
    member = who(db, people, "member")
    with frozen_at(MONDAY), db.write(member.actor) as session:
        row = controls.set_standing(
            session,
            member,
            controls.find(session, "data-within-class"),
            {"status": "implemented"},
            record=(USE_CASE, find(session, USE_CASE, use_ref)),
        )
        due = row.next_check_on
    assert due == MONDAY.date() + timedelta(days=181)  # six months on
    with frozen_at(at(due - timedelta(days=1))):
        watch(db)
        assert not any("still in place" in title for title in notices(db, people, "member"))
    with frozen_at(at(due)):
        watch(db)
        watch(db)
        assert [t for t in notices(db, people, "member") if "still in place" in t] == [
            "Check that this is still in place: Only permitted classes of data are used"
        ]
        with db.write(member.actor) as session:
            use_case = find(session, USE_CASE, use_ref)
            assert {c["key"]: c for c in controls.for_record(session, member, USE_CASE, use_case)}[
                "data-within-class"
            ]["check_due"]
            row = controls.set_standing(
                session,
                member,
                controls.find(session, "data-within-class"),
                {"status": "implemented", "checked": True},
                record=(USE_CASE, use_case),
            )
            assert row.next_check_on > due


def test_a_risk_shows_the_controls_that_answer_it(db: Database, people: People) -> None:
    use_ref, _, _ = linked(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        use_case = find(session, USE_CASE, use_ref)
        risk = risks.add(
            session,
            governance,
            {"library_key": "nobody-owns-it", "inherent_likelihood": 3, "inherent_impact": 3},
            record=(USE_CASE, use_case),
        )
        seen = {c["key"]: c["status"] for c in risks.view(session, governance, risk)["controls"]}
        assert seen == {"roles-assigned": "not_started", "named-owner": "not_started"}
        controls.set_standing(
            session,
            governance,
            controls.find(session, "named-owner"),
            {"status": "implemented"},
            record=(USE_CASE, use_case),
        )
        seen = {c["key"]: c["status"] for c in risks.view(session, governance, risk)["controls"]}
        assert seen["named-owner"] == "implemented"


def test_controls_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    use_ref, _, _ = linked(db, people)
    governance, member = as_role("governance"), as_role("member")
    listed = member.get("/api/v1/controls").json()["data"]
    assert len(listed) >= 30 and not any(c.get("can_set") for c in listed)
    mine = member.get("/api/v1/controls", params={"record": use_ref}).json()
    assert mine["meta"]["record"]["ref"] == use_ref and all(c["can_set"] for c in mine["data"])
    put = member.put(
        "/api/v1/controls/owner-confirms/standing",
        json={"record": use_ref, "status": "in_progress"},
    )
    assert put.status_code == 200
    assert {c["key"]: c["status"] for c in put.json()["data"]}["owner-confirms"] == "in_progress"
    assert (
        member.put(
            "/api/v1/controls/inventory-kept/standing", json={"status": "implemented"}
        ).status_code
        == 403
    )
    done = governance.put(
        "/api/v1/controls/inventory-kept/standing", json={"status": "implemented"}
    )
    assert done.json()["data"]["status"] == "implemented" and done.json()["data"]["next_check_on"]
    off = governance.put(
        "/api/v1/controls/owner-confirms/standing",
        json={
            "record": use_ref,
            "status": "not_applicable",
            "note": "Covered by the annual campaign.",
        },
    )
    assert {c["key"]: c["status"] for c in off.json()["data"]}["owner-confirms"] == "not_applicable"
    assert member.get("/api/v1/controls/nothing").status_code == 404
    detail = governance.get("/api/v1/controls/owner-confirms").json()["data"]
    assert detail["records"][0]["status"] == "not_applicable"
