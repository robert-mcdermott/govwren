"""Attestation campaigns: owners confirm their records, stewards attest their unit's list,
and coverage is counted by unit."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Attestation, Campaign, UseCase
from govwren.inventory import history
from govwren.inventory.registry import USE_CASE
from govwren.oversight import campaigns
from govwren.review import views
from tests.people import People
from tests.test_intake import SIMPLE
from tests.test_review import MONDAY, notices, request, who
from tests.test_schedule import at, use_case_of, watch

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
DUE = date(2026, 12, 1)


def three_uses(db: Database, people: People) -> list[str]:
    """Three approved uses in the Hale Lab: two the member's, one the steward's."""
    refs = []
    with frozen_at(MONDAY):
        for name, by in (("Drafting", "member"), ("Coding", "member"), ("Summaries", "steward")):
            refs.append(request(db, people, {**SIMPLE, "name": f"{name} with an assistant"}, by))
    return refs


def start(db: Database, people: People, **values: Any) -> str:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        campaign = campaigns.open_campaign(
            session,
            governance,
            **{
                "kind": "owner_confirmation",
                "title": "Autumn confirmation",
                "due_on": DUE,
                **values,
            },
        )
        return campaign.ref


def look(db: Database, people: People, ref: str, role: str) -> dict[str, Any]:
    with db.read() as session:
        return campaigns.view(session, who(db, people, role), campaigns.find(session, ref))


def test_a_campaign_asks_the_owners_of_every_record_in_scope(db: Database, people: People) -> None:
    three_uses(db, people)
    ref = start(db, people)
    seen = look(db, people, ref, "governance")
    assert (seen["total"], seen["answered"], seen["status"]) == (3, 0, "open")
    assert [row["unit"] for row in seen["by_unit"]] == ["Hale Lab"]
    mine = look(db, people, ref, "member")
    assert [item["name"] for item in mine["items"] if item["mine"]] == [
        "Drafting with an assistant",
        "Coding with an assistant",
    ]
    assert mine["by_unit"] == [] and mine["mine_waiting"] == 2
    assert any("2 records to confirm by Dec 1" in title for title in notices(db, people, "member"))
    with db.read() as session:
        work = views.my_work(session, who(db, people, "member"))
        assert ("attestation", "2 records to confirm") in [(i["kind"], i["detail"]) for i in work]
        with pytest.raises(NotFound):  # it asks nothing of the reviewer
            campaigns.view(session, who(db, people, "reviewer"), campaigns.find(session, ref))


def test_starting_a_campaign_needs_governance_and_something_to_ask(
    db: Database, people: People
) -> None:
    three_uses(db, people)
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        with pytest.raises(PermissionDenied):
            campaigns.open_campaign(
                session, member, kind="owner_confirmation", title="Mine", due_on=DUE
            )
        with pytest.raises(Invalid) as bad:
            campaigns.open_campaign(
                session, governance, kind="census", title="x", due_on=MONDAY.date()
            )
        assert set(bad.value.errors) == {"kind", "title", "due_on"}
        with pytest.raises(Invalid) as empty:
            campaigns.open_campaign(
                session,
                governance,
                kind="owner_confirmation",
                title="Cancer Biology",
                due_on=DUE,
                scope_unit_id=people.units["CANCER"],
            )
        assert "scope_unit_id" in empty.value.errors


def test_owners_confirm_several_at_once_and_coverage_follows(db: Database, people: People) -> None:
    refs = three_uses(db, people)
    ref = start(db, people)
    member = who(db, people, "member")
    ids = [item["id"] for item in look(db, people, ref, "member")["items"] if item["mine"]]
    with db.write(member.actor) as session:
        campaign = campaigns.find(session, ref)
        done = campaigns.answer(
            session, member, campaign, [{"id": i, "response": "confirmed"} for i in ids]
        )
        assert done == 2
        with pytest.raises(Conflict):  # an answer is given once
            campaigns.answer(session, member, campaign, [{"id": ids[0], "response": "confirmed"}])
    seen = look(db, people, ref, "governance")
    assert (seen["answered"], seen["by_response"]) == (2, {"confirmed": 2})
    assert seen["by_unit"][0] == {
        "org_unit_id": people.units["HALE"],
        "unit": "Hale Lab",
        "total": 3,
        "answered": 2,
    }
    waiting = [item for item in seen["items"] if not item["response"]]
    assert [item["waiting_on"] for item in waiting] == [["Steward Person"]]
    with db.read() as session:
        use_case = use_case_of(session, refs[0])
        titles = [entry["title"] for entry in history.for_record(session, USE_CASE, use_case)]
        assert "Confirmed as still accurate" in titles
        assert views.my_work(session, member) == [] or all(
            item["kind"] != "attestation" for item in views.my_work(session, member)
        )


def test_an_owner_cannot_answer_for_someone_elses_record(db: Database, people: People) -> None:
    three_uses(db, people)
    ref = start(db, people)
    theirs = next(
        i for i in look(db, people, ref, "governance")["items"] if i["name"].startswith("Summ")
    )
    member = who(db, people, "member")
    with db.write(member.actor) as session, pytest.raises(PermissionDenied):
        campaigns.answer(
            session,
            member,
            campaigns.find(session, ref),
            [{"id": theirs["id"], "response": "confirmed"}],
        )


def test_changed_needs_a_note_and_tells_governance(db: Database, people: People) -> None:
    three_uses(db, people)
    ref = start(db, people)
    member = who(db, people, "member")
    first = next(i for i in look(db, people, ref, "member")["items"] if i["mine"])
    with db.write(member.actor) as session:
        campaign = campaigns.find(session, ref)
        with pytest.raises(Invalid) as bad:
            campaigns.answer(
                session, member, campaign, [{"id": first["id"], "response": "changed"}]
            )
        assert "note" in bad.value.errors
        campaigns.answer(
            session,
            member,
            campaign,
            [
                {
                    "id": first["id"],
                    "response": "changed",
                    "note": "We now use it on interview notes.",
                }
            ],
        )
    assert any("Reported as changed" in title for title in notices(db, people, "governance"))


def test_no_longer_in_use_retires_the_record(db: Database, people: People) -> None:
    refs = three_uses(db, people)
    ref = start(db, people)
    member = who(db, people, "member")
    first = next(i for i in look(db, people, ref, "member")["items"] if i["mine"])
    with db.write(member.actor) as session:
        campaigns.answer(
            session,
            member,
            campaigns.find(session, ref),
            [
                {
                    "id": first["id"],
                    "response": "retired",
                    "note": "The project ended in the spring.",
                }
            ],
        )
    with db.read() as session:
        use_case = use_case_of(session, refs[0])
        assert use_case.status == "retired" and use_case.next_review_on is None
        entries = history.for_record(session, USE_CASE, use_case)
        retired = next(entry for entry in entries if entry["title"] == "Retired")
        assert retired["lines"][0]["after"] == "The project ended in the spring."
    with frozen_at(at(date(2029, 12, 1))):  # and nothing falls due for it afterwards
        done = watch(db)
        assert (done["lapsed"], done["periodic_reviews"]) == (2, 2)  # only the other two


def test_a_steward_attests_that_the_units_list_is_complete(db: Database, people: People) -> None:
    three_uses(db, people)
    ref = start(db, people, kind="unit_completeness", title="Is your list complete?")
    seen = look(db, people, ref, "governance")
    assert {item["name"] for item in seen["items"]} == {"Neuroscience", "Hale Lab"}
    steward = who(db, people, "steward")
    mine = look(db, people, ref, "steward")
    assert mine["mine_waiting"] == 2
    hale = next(item for item in mine["items"] if item["name"] == "Hale Lab")
    assert hale["holds"]["use_case"] == 3 and hale["can_answer"]
    member = who(db, people, "member")
    with db.write(member.actor) as session, pytest.raises((PermissionDenied, NotFound)):
        campaigns.answer(
            session,
            member,
            campaigns.find(session, ref),
            [{"id": hale["id"], "response": "attested"}],
        )
    with db.write(steward.actor) as session:
        campaigns.answer(
            session,
            steward,
            campaigns.find(session, ref),
            [{"id": item["id"], "response": "attested"} for item in mine["items"]],
        )
    seen = look(db, people, ref, "governance")
    assert (seen["answered"], seen["total"], seen["by_response"]) == (2, 2, {"attested": 2})
    with db.read() as session:
        item = session.get(Attestation, hale["id"])
        assert item is not None and item.snapshot is not None and item.snapshot["use_case"] == 3


def test_a_closed_campaign_takes_no_more_answers(db: Database, people: People) -> None:
    three_uses(db, people)
    ref = start(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    first = next(i for i in look(db, people, ref, "member")["items"] if i["mine"])
    with db.write(governance.actor) as session:
        campaign = campaigns.find(session, ref)
        with pytest.raises(PermissionDenied):
            campaigns.close(session, member, campaign)
        campaigns.close(session, governance, campaign)
    with db.write(member.actor) as session, pytest.raises(Conflict):
        campaigns.answer(
            session,
            member,
            campaigns.find(session, ref),
            [{"id": first["id"], "response": "confirmed"}],
        )
    assert look(db, people, ref, "member")["mine_waiting"] == 0


def test_reminders_go_before_the_date_and_to_the_steward_after_it(
    db: Database, people: People
) -> None:
    three_uses(db, people)
    start(db, people)
    with frozen_at(at(DUE - timedelta(days=10))):
        assert watch(db)["reminders"] == 0
    with frozen_at(at(DUE - timedelta(days=5))):
        assert watch(db)["reminders"] == 2  # the member and the steward, as owners
        assert watch(db)["reminders"] == 0
    assert any("Due Dec 1: 2 answers wanted" in title for title in notices(db, people, "member"))
    with frozen_at(at(DUE + timedelta(days=1))):
        assert watch(db)["reminders"] == 2
    late = [title for title in notices(db, people, "steward") if title.startswith("Overdue")]
    assert late == ["Overdue: 3 answers still wanted for Autumn confirmation"]


def test_campaigns_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    three_uses(db, people)
    governance, member = as_role("governance"), as_role("member")
    body = {
        "kind": "owner_confirmation",
        "title": "Spring confirmation",
        "due_on": (date.today() + timedelta(days=30)).isoformat(),
    }
    assert member.post("/api/v1/campaigns", json=body).status_code == 403
    made = governance.post("/api/v1/campaigns", json=body)
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    assert ref == "ATT-0001"
    assert [c["ref"] for c in member.get("/api/v1/campaigns").json()["data"]] == [ref]
    assert as_role("reviewer").get("/api/v1/campaigns").json()["data"] == []
    assert as_role("reviewer").get(f"/api/v1/campaigns/{ref}").status_code == 404
    mine = [i for i in member.get(f"/api/v1/campaigns/{ref}").json()["data"]["items"] if i["mine"]]
    answered = member.post(
        f"/api/v1/campaigns/{ref}/answers",
        json={"items": [{"id": item["id"], "response": "confirmed"} for item in mine]},
    )
    assert answered.status_code == 200 and answered.json()["data"]["mine_waiting"] == 0
    assert governance.post(f"/api/v1/campaigns/{ref}/close").json()["data"]["status"] == "closed"
    with db.read() as session:
        assert session.scalars(select(Campaign.status)).all() == ["closed"]
        assert session.scalars(select(UseCase.status)).all() == ["approved_with_conditions"] * 3
