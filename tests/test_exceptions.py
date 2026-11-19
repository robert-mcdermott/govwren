"""Exceptions: asked for with a justification and what is done instead, decided by
governance, always ending, and shown on the record and on what relies on it."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.inventory import history
from govwren.inventory.registry import SYSTEM, USE_CASE, find
from govwren.oversight import exceptions, findings
from govwren.review import views
from tests.people import People
from tests.test_changes import linked
from tests.test_review import MONDAY, notices, who
from tests.test_schedule import at, watch

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
ENDS = date(2027, 3, 1)
ASK: dict[str, Any] = {
    "title": "Use before the security assessment is finished",
    "requirement": "A security assessment must be complete before a tool is used.",
    "justification": "The grant report is due before the assessment can be scheduled.",
    "measures": "Only public data is used until the assessment is done.",
    "ends_on": ENDS,
}


def asked(db: Database, people: People, **values: Any) -> tuple[str, str, str]:
    """An exception requested by the member on their use. Returns its reference, the use's,
    and the system's that the use relies on."""
    use_ref, system_ref, _ = linked(db, people)
    member = who(db, people, "member")
    with frozen_at(MONDAY), db.write(member.actor) as session:
        made = exceptions.request(
            session, member, USE_CASE, find(session, USE_CASE, use_ref), **{**ASK, **values}
        )
        return made.ref, use_ref, system_ref


def approve(db: Database, people: People, ref: str, **more: Any) -> None:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        exceptions.decide(
            session,
            governance,
            exceptions.find(session, ref),
            outcome="approved",
            note="Acceptable for a short time, given the measures.",
            **more,
        )


def test_an_exception_needs_all_its_parts_and_an_end_date(db: Database, people: People) -> None:
    use_ref, _, _ = linked(db, people)
    member, reviewer = who(db, people, "member"), who(db, people, "reviewer")
    with frozen_at(MONDAY), db.write(member.actor) as session:
        use_case = find(session, USE_CASE, use_ref)
        with pytest.raises(Invalid) as bad:
            exceptions.request(
                session,
                member,
                USE_CASE,
                use_case,
                title="x",
                requirement="",
                justification="",
                measures="",
                ends_on=None,
            )
        assert set(bad.value.errors) == {
            "title",
            "requirement",
            "justification",
            "measures",
            "ends_on",
        }
        with pytest.raises(Invalid) as long:
            exceptions.request(
                session,
                member,
                USE_CASE,
                use_case,
                **{**ASK, "ends_on": MONDAY.date() + timedelta(days=400)},
            )
        assert "a year at most" in long.value.errors["ends_on"]
        with pytest.raises(PermissionDenied):
            exceptions.request(session, reviewer, USE_CASE, use_case, **ASK)


def test_governance_is_told_and_decides_but_not_its_own(db: Database, people: People) -> None:
    ref, use_ref, _ = asked(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    assert any("Exception to decide" in title for title in notices(db, people, "governance"))
    with db.read() as session:
        work = views.my_work(session, governance)
        assert [item["title"] for item in work if item["kind"] == "exception"] == [
            "Decide an exception: Use before the security assessment is finished"
        ]
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        found = exceptions.find(session, ref)
        with pytest.raises(PermissionDenied):
            exceptions.decide(
                session, member, found, outcome="approved", note="Fine by me, thanks."
            )
        with pytest.raises(Invalid):
            exceptions.decide(session, governance, found, outcome="approved", note="ok")
        exceptions.decide(
            session,
            governance,
            found,
            outcome="approved",
            note="Acceptable for a short time.",
            ends_on=date(2027, 1, 15),
        )
        with pytest.raises(Conflict):
            exceptions.decide(
                session, governance, found, outcome="declined", note="Changed my mind."
            )
        own = exceptions.request(
            session, governance, USE_CASE, find(session, USE_CASE, use_ref), **ASK
        )
        with pytest.raises(PermissionDenied):
            exceptions.decide(
                session, governance, own, outcome="approved", note="I approve my own."
            )
    with db.read() as session:
        seen = exceptions.view(session, member, exceptions.find(session, ref))
        assert (seen["status"], seen["ends_on"]) == (
            "approved",
            date(2027, 1, 15),
        )  # brought forward
        assert seen["can"] == {"decide": False, "withdraw": False, "revoke": False, "renew": True}
    assert any("approved until Jan 15" in title for title in notices(db, people, "member"))


def test_an_exception_shows_on_the_record_and_on_what_relies_on_it(
    db: Database, people: People
) -> None:
    use_ref, system_ref, _ = linked(db, people)
    governance, steward = who(db, people, "governance"), who(db, people, "steward")
    with frozen_at(MONDAY), db.write(steward.actor) as session:
        system = find(session, SYSTEM, system_ref)
        system.org_unit_id = people.units["HALE"]  # type: ignore[attr-defined]
        made = exceptions.request(session, steward, SYSTEM, system, **ASK)
        ref = made.ref
    approve(db, people, ref)
    with frozen_at(MONDAY), db.read() as session:
        own = findings.for_record(session, governance, SYSTEM, find(session, SYSTEM, system_ref))
        assert own["own"][0]["kind"] == "exception" and "until Mar 1, 2027" in own["own"][0]["text"]
        use = findings.for_record(session, governance, USE_CASE, find(session, USE_CASE, use_ref))
        assert [f["from"]["ref"] for f in use["inherited"]] == [system_ref]
        titles = [
            e["title"]
            for e in history.for_record(session, SYSTEM, find(session, SYSTEM, system_ref))
        ]
        assert f"Exception {ref} requested" in titles and f"Exception {ref} approved" in titles


def test_an_exception_ends_by_itself_after_a_reminder(db: Database, people: People) -> None:
    ref, use_ref, _ = asked(db, people)
    approve(db, people, ref)
    governance = who(db, people, "governance")
    with frozen_at(at(ENDS - timedelta(days=30))):
        assert watch(db)["expired"] == 0
        assert not any("Exception ends" in title for title in notices(db, people, "member"))
    with frozen_at(at(ENDS - timedelta(days=10))):
        watch(db)
        watch(db)
        soon = [
            title for title in notices(db, people, "member") if title.startswith("Exception ends")
        ]
        assert len(soon) == 1 and "Mar 1" in soon[0]
        with db.read() as session:
            work = views.my_work(session, who(db, people, "member"))
            assert any(item["title"].startswith("An exception is ending") for item in work)
    with frozen_at(at(ENDS)):
        assert watch(db)["expired"] == 0  # it runs through its last day
    with frozen_at(at(ENDS + timedelta(days=1))):
        assert watch(db)["expired"] == 1
        assert watch(db)["expired"] == 0
        with db.read() as session:
            found = exceptions.find(session, ref)
            assert found.status == "expired"
            use = findings.for_record(
                session, governance, USE_CASE, find(session, USE_CASE, use_ref)
            )
            assert use["own"] == []
    assert any("Exception ended" in title for title in notices(db, people, "governance"))


def test_a_renewal_is_a_new_request_that_points_back(db: Database, people: People) -> None:
    ref, _, _ = asked(db, people)
    member = who(db, people, "member")
    with (
        frozen_at(MONDAY),
        db.write(member.actor) as session,
        pytest.raises(Conflict),  # not approved yet
    ):
        exceptions.renew(
            session,
            member,
            exceptions.find(session, ref),
            justification="We need longer than we thought.",
            ends_on=ENDS,
        )
    approve(db, people, ref)
    with frozen_at(at(ENDS - timedelta(days=5))), db.write(member.actor) as session:
        again = exceptions.renew(
            session,
            member,
            exceptions.find(session, ref),
            justification="The assessment slipped to the summer.",
            ends_on=date(2027, 8, 1),
        )
        assert (again.status, again.renews_id) == ("requested", exceptions.find(session, ref).id)
        assert again.measures == ASK["measures"]
        with pytest.raises(Conflict):  # one renewal at a time
            exceptions.renew(
                session,
                member,
                exceptions.find(session, ref),
                justification="The assessment slipped again.",
                ends_on=date(2027, 8, 1),
            )
        first = exceptions.view(session, member, exceptions.find(session, ref))
        assert first["renewed_by"] == again.ref and first["can"]["renew"] is False


def test_withdrawing_and_revoking(db: Database, people: People) -> None:
    ref, use_ref, _ = asked(db, people)
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with frozen_at(MONDAY), db.write(member.actor) as session:
        found = exceptions.find(session, ref)
        exceptions.end(session, member, found)
        assert found.status == "withdrawn"
        with pytest.raises(Conflict):
            exceptions.end(session, member, found)
        second = exceptions.request(
            session, member, USE_CASE, find(session, USE_CASE, use_ref), **ASK
        )
        second_ref = second.ref
    approve(db, people, second_ref)
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        found = exceptions.find(session, second_ref)
        with pytest.raises(PermissionDenied):
            exceptions.end(session, member, found, "I would like it gone now.")
        with pytest.raises(Invalid):
            exceptions.end(session, governance, found, "no")
        exceptions.end(session, governance, found, "Restricted data was used under it.")
        assert found.status == "revoked"
    assert any("was revoked" in title for title in notices(db, people, "member"))


def test_the_register_shows_each_person_what_they_may_see(db: Database, people: People) -> None:
    ref, use_ref, _ = asked(db, people)
    with db.read() as session:
        everything = exceptions.register(session, who(db, people, "auditor"))
        assert [row["ref"] for row in everything] == [ref]
        assert everything[0]["record"]["ref"] == use_ref
        assert exceptions.register(session, who(db, people, "reviewer")) == []
        with pytest.raises(NotFound):
            exceptions.view(session, who(db, people, "reviewer"), exceptions.find(session, ref))
        mine = exceptions.register(session, who(db, people, "member"), status="open")
        assert [row["ref"] for row in mine] == [ref] and mine[0]["can"]["withdraw"]
        assert exceptions.register(session, who(db, people, "member"), status="approved") == []


def test_exceptions_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    use_ref, _, _ = linked(db, people)
    member, governance = as_role("member"), as_role("governance")
    body = {**ASK, "record": use_ref, "ends_on": (date.today() + timedelta(days=90)).isoformat()}
    assert as_role("reviewer").post("/api/v1/exceptions", json=body).status_code in (403, 404)
    made = member.post("/api/v1/exceptions", json=body)
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    assert ref == "EXC-0001"
    assert (
        member.post(
            f"/api/v1/exceptions/{ref}/decision",
            json={"outcome": "approved", "note": "I approve this."},
        ).status_code
        == 403
    )
    decided = governance.post(
        f"/api/v1/exceptions/{ref}/decision",
        json={"outcome": "approved", "note": "Acceptable given the measures."},
    )
    assert decided.status_code == 200 and decided.json()["data"]["status"] == "approved"
    listed = member.get("/api/v1/exceptions", params={"record": use_ref}).json()["data"]
    assert [row["ref"] for row in listed] == [ref]
    found = member.get(f"/api/v1/records/{use_ref}/findings").json()["data"]
    assert found["own"][0]["ref"] == ref
    renewed = member.post(
        f"/api/v1/exceptions/{ref}/renewal",
        json={
            "justification": "It will take a little longer.",
            "ends_on": (date.today() + timedelta(days=200)).isoformat(),
        },
    )
    assert renewed.status_code == 201 and renewed.json()["data"]["renews"] == ref
    revoked = governance.post(
        f"/api/v1/exceptions/{ref}/end", json={"reason": "No longer needed here."}
    )
    assert revoked.json()["data"]["status"] == "revoked"
