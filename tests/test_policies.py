"""Policies: versions, an owner, a review date, the controls that carry them out, and a
record of who has acknowledged the version in force."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from govwren.assurance import policies
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.review import views
from tests.people import People
from tests.test_review import MONDAY, notices, who
from tests.test_schedule import at, watch

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
TEXT = "Use only tools from the catalog for work data. Check what a tool produces before use."
DUE = date(2026, 12, 1)


def in_force(db: Database, people: People) -> str:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        policy = policies.create(
            session,
            governance,
            {
                "title": "Acceptable use of AI",
                "summary": "What everyone must do.",
                "body": TEXT,
                "review_on": "2027-11-01",
                "control_keys": ["easy-front-door", "human-checks-output"],
            },
        )
        policies.publish(session, governance, policy)
        return policy.ref


def test_a_policy_is_drafted_published_and_revised_with_its_versions_kept(
    db: Database, people: People
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        with pytest.raises(PermissionDenied):
            policies.create(session, member, {"title": "Mine"})
        with pytest.raises(Invalid) as bad:
            policies.create(session, governance, {"title": "x", "control_keys": ["not-a-control"]})
        assert set(bad.value.errors) == {"title", "control_keys"}
        policy = policies.create(session, governance, {"title": "Acceptable use of AI"})
        assert (policy.ref, policy.status, policy.owner_id) == (
            "POL-0001",
            "draft",
            governance.account_id,
        )
        with pytest.raises(NotFound):  # a draft is not shown to everyone
            policies.view(session, member, policy)
        with pytest.raises(Invalid):  # nothing written yet
            policies.publish(session, governance, policy)
        policies.save_draft(session, governance, policy, body=TEXT)
        policies.publish(session, governance, policy)
        with pytest.raises(Conflict):
            policies.publish(session, governance, policy)
        seen = policies.view(session, member, policy)
        assert (seen["status"], seen["version"], seen["body"]) == ("in_force", 1, TEXT)
        assert seen["draft"] is None and seen["coverage"] is None and not seen["can"]["edit"]
        policies.save_draft(
            session, governance, policy, body=TEXT + " Report anything that goes wrong."
        )
        assert policies.view(session, member, policy)["body"] == TEXT  # still version 1
        with pytest.raises(Invalid) as note:
            policies.publish(session, governance, policy)
        assert "change_note" in note.value.errors
        policies.save_draft(
            session,
            governance,
            policy,
            body=TEXT + " Report anything that goes wrong.",
            change_note="Added the duty to report.",
        )
        policies.publish(session, governance, policy)
        seen = policies.view(session, governance, policy)
        assert seen["version"] == 2 and seen["body"].endswith("goes wrong.")
        assert [(v["version"], v["change_note"]) for v in seen["versions"]] == [
            (2, "Added the duty to report."),
            (1, None),
        ]
        policies.retire(session, governance, policy)
        assert policies.listing(session, member) == []
        assert [p["status"] for p in policies.listing(session, governance)] == ["retired"]


def test_people_are_asked_to_acknowledge_the_version_in_force(db: Database, people: People) -> None:
    ref = in_force(db, people)
    governance, member, steward = (who(db, people, r) for r in ("governance", "member", "steward"))
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        policy = policies.find(session, ref)
        with pytest.raises(Invalid):
            policies.ask(session, governance, policy, unit_id=None, due_on=MONDAY.date())
        with pytest.raises(PermissionDenied):
            policies.ask(session, member, policy, unit_id=None, due_on=DUE)
        asked = policies.ask(session, governance, policy, unit_id=people.units["NEURO"], due_on=DUE)
        assert asked >= 1  # everyone who works in Neuroscience or beneath it
        with pytest.raises(Conflict):
            policies.ask(session, governance, policy, unit_id=people.units["NEURO"], due_on=DUE)
        everyone = policies.ask(session, governance, policy, unit_id=None, due_on=DUE)
        assert everyone >= 1  # the rest, once each
        coverage = policies.view(session, governance, policy)["coverage"]
        assert coverage["asked"] == asked + everyone and coverage["acknowledged"] == 0
    assert "Please read and acknowledge by Dec 1: Acceptable use of AI" in notices(
        db, people, "member"
    )
    with frozen_at(MONDAY), db.write(member.actor) as session:
        policy = policies.find(session, ref)
        work = views.my_work(session, member)
        assert ("policy", "Read and acknowledge: Acceptable use of AI") in [
            (i["kind"], i["title"]) for i in work
        ]
        assert policies.view(session, member, policy)["mine"]["acknowledged_at"] is None
        policies.acknowledge(session, member, policy)
        with pytest.raises(Conflict):
            policies.acknowledge(session, member, policy)
        assert policies.view(session, member, policy)["mine"]["acknowledged_at"] is not None
        assert policies.waiting_on(session, member) == []
    with frozen_at(at(DUE - timedelta(days=3))):
        watch(db)
        watch(db)
    soon = [
        t for t in notices(db, people, "steward") if t.startswith("Due Dec 1: read and acknowledge")
    ]
    assert len(soon) == 1 and not any(
        "read and acknowledge" in t and t.startswith("Due")
        for t in notices(db, people, "member")[1:]
    )
    with frozen_at(at(DUE + timedelta(days=1))):
        watch(db)
    assert any(
        t.startswith("Overdue: read and acknowledge") for t in notices(db, people, "steward")
    )
    assert steward.account_id


def test_a_new_version_asks_afresh_and_the_owner_is_reminded_to_review(
    db: Database, people: People
) -> None:
    ref = in_force(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        policy = policies.find(session, ref)
        policies.ask(session, governance, policy, unit_id=None, due_on=DUE)
    with frozen_at(MONDAY), db.write(member.actor) as session:
        policies.acknowledge(session, member, policies.find(session, ref))
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        policy = policies.find(session, ref)
        policies.save_draft(
            session, governance, policy, body=TEXT + " More.", change_note="A new duty."
        )
        policies.publish(session, governance, policy)
        assert (
            policies.view(session, member, policy)["mine"] is None
        )  # not asked about version 2 yet
        assert policies.ask(session, governance, policy, unit_id=None, due_on=DUE) >= 2
        assert policies.view(session, member, policy)["mine"]["acknowledged_at"] is None
        seen = policies.view(session, governance, policy)
        assert [c["key"] for c in seen["controls"]] == ["easy-front-door", "human-checks-output"]
    with frozen_at(at(date(2027, 11, 1))):
        watch(db)
        watch(db)
    due = [
        t
        for t in notices(db, people, "governance")
        if t.startswith("This policy is due for review")
    ]
    assert due == ["This policy is due for review: Acceptable use of AI"]


def test_policies_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    governance, member = as_role("governance"), as_role("member")
    assert member.post("/api/v1/policies", json={"title": "Mine"}).status_code == 403
    made = governance.post("/api/v1/policies", json={"title": "Acceptable use of AI", "body": TEXT})
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    assert member.get(f"/api/v1/policies/{ref}").status_code == 404
    assert governance.post(f"/api/v1/policies/{ref}/publish").json()["data"]["status"] == "in_force"
    assert [p["ref"] for p in member.get("/api/v1/policies").json()["data"]] == [ref]
    assert member.post(f"/api/v1/policies/{ref}/acknowledge").status_code == 409  # not asked
    due = (date.today() + timedelta(days=20)).isoformat()
    asked = governance.post(f"/api/v1/policies/{ref}/ask", json={"due_on": due})
    assert asked.json()["data"]["coverage"]["asked"] >= 5
    done = member.post(f"/api/v1/policies/{ref}/acknowledge")
    assert done.json()["data"]["mine"]["acknowledged_at"]
    patched = governance.patch(
        f"/api/v1/policies/{ref}", json={"control_keys": ["named-owner"], "review_on": due}
    )
    assert [c["key"] for c in patched.json()["data"]["controls"]] == ["named-owner"]
    drafted = governance.put(
        f"/api/v1/policies/{ref}/draft", json={"body": TEXT + " And more.", "change_note": "More."}
    )
    assert (
        drafted.json()["data"]["draft"]["version"] == 2 and drafted.json()["data"]["version"] == 1
    )
    assert governance.post(f"/api/v1/policies/{ref}/retire").json()["data"]["status"] == "retired"
