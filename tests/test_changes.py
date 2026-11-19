"""A record changes in the open: change declarations judged by the rules, retirement with
dependents told, and findings inherited from what a record relies on."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Decision, IntakeDraft, Review
from govwren.intake import service as intake
from govwren.inventory import history, links, records
from govwren.inventory.registry import MODEL, SYSTEM, USE_CASE, find
from govwren.oversight import changes, findings, retirement
from govwren.review import service, views
from tests.people import ME, People
from tests.test_intake import SIMPLE
from tests.test_review import MONDAY, notices, request, who
from tests.test_schedule import use_case_of

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
LATER = MONDAY.replace(year=2027)


def declared(db: Database, people: People, summary: str = "We use it for more now.") -> str:
    """An approved use with a change declared by its owner. Returns the first review."""
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    member = who(db, people, "member")
    with frozen_at(LATER), db.write(member.actor) as session:
        changes.declare(session, member, use_case_of(session, first), summary)
    return first


def submit(db: Database, people: People, first: str, answers: dict[str, Any]) -> Review:
    member = who(db, people, "member")
    with frozen_at(LATER), db.write(member.actor) as session:
        use_case = use_case_of(session, first)
        errors = intake.save(session, member, use_case, {**answers, "unit": people.units["HALE"]})
        assert errors == {}
        intake.submit(session, member, use_case)
        return service.latest_review(session, use_case)  # type: ignore[return-value]


def test_declaring_a_change_puts_the_answers_back_and_changes_nothing_yet(
    db: Database, people: People
) -> None:
    first = declared(db, people)
    member = who(db, people, "member")
    with db.read() as session:
        use_case = use_case_of(session, first)
        review = service.open_review(session, use_case)
        assert review is not None and (review.kind, review.status) == ("change", "with_requester")
        assert review.routing["change"]["summary"] == "We use it for more now."
        assert use_case.status == "approved_with_conditions"
        draft = session.get(IntakeDraft, use_case.id)
        assert draft is not None and draft.answers["purpose"] == SIMPLE["purpose"]
        assert intake.view(session, member, use_case)["confirming"]["kind"] == "change"
        assert [i["kind"] for i in views.my_work(session, member)] == ["change"]


def test_only_an_owner_declares_and_only_on_an_approved_use_with_no_review_open(
    db: Database, people: People
) -> None:
    first = declared(db, people)
    member, reviewer = who(db, people, "member"), who(db, people, "reviewer")
    with db.write(member.actor) as session:
        use_case = use_case_of(session, first)
        with pytest.raises(PermissionDenied):
            changes.declare(session, reviewer, use_case, "I think it has changed.")
        with pytest.raises(Conflict):  # one is already open
            changes.declare(session, member, use_case, "Another change altogether.")
    with frozen_at(MONDAY):
        other = request(db, people, {**SIMPLE, "name": "A second use"})
    with db.write(member.actor) as session, pytest.raises(Invalid):
        changes.declare(session, member, use_case_of(session, other), "short")


def test_a_change_that_is_not_material_is_recorded_and_the_approval_stands(
    db: Database, people: People
) -> None:
    first = declared(db, people)
    with db.read() as session:
        until = use_case_of(session, first).approved_until
    review = submit(
        db, people, first, {**SIMPLE, "human_oversight": "Two people read each summary."}
    )
    with db.read() as session:
        use_case = use_case_of(session, first)
        found = session.get(Review, review.id)
        assert found is not None and found.status == "decided"
        change = found.routing["change"]
        assert change["material"] is False and change["reasons"] == []
        assert [item["key"] for item in change["changed"]] == ["human_oversight"]
        assert change["changed"][0]["after"] == "Two people read each summary."
        decision = session.scalars(select(Decision).where(Decision.review_id == found.id)).one()
        assert decision.by_rule == "Not a material change" and decision.decided_by is None
        assert (use_case.status, use_case.approved_until) == ("approved_with_conditions", until)
        assert use_case.human_oversight == "Two people read each summary."
        assert len(service.conditions_of(session, use_case)) == 5  # none set again
        titles = [entry["title"] for entry in history.for_record(session, USE_CASE, use_case)]
        assert f"Change review {found.ref} opened" in titles


def test_a_material_change_opens_a_review_limited_to_what_changed(
    db: Database, people: People
) -> None:
    first = declared(db, people)
    with db.read() as session:
        until = use_case_of(session, first).approved_until
    review = submit(db, people, first, {**SIMPLE, "impact": "serious"})
    governance = who(db, people, "governance")
    with db.read() as session:
        found = session.get(Review, review.id)
        use_case = use_case_of(session, first)
        assert found is not None and (found.kind, found.status) == ("change", "triage")
        change = found.routing["change"]
        assert change["material"] and change["tier_after"] > change["tier_before"]
        [impact] = change["changed"]
        assert impact["key"] == "impact" and impact["before"] != impact["after"]
        assert impact["after"] != "serious"  # shown as people read it, not as stored
        tasks = {task.review_function for task in service.tasks_of(session, found)}
        assert tasks == set(change["new_functions"]) and tasks  # only what is newly required
        assert use_case.status == "approved_with_conditions"  # it stands while reviewed
        packet = views.packet(session, governance, found)
        assert packet["change"]["summary"] == "We use it for more now."
    assert any("Change to triage" in title for title in notices(db, people, "governance"))
    with frozen_at(LATER), db.write(governance.actor) as session:
        found = session.get(Review, review.id)
        assert found is not None
        waived = [task.review_function for task in service.tasks_of(session, found)]
        service.triage(session, governance, found, remove=waived, reason="Seen by the committee.")
        service.decide(session, governance, found, outcome="approved",
                       rationale="The wider use is acceptable as described.")  # fmt: skip
    with db.read() as session:
        use_case = use_case_of(session, first)
        # a change does not restart the approval period
        assert (use_case.status, use_case.approved_until) == ("approved", until)


def test_a_change_never_submitted_can_be_dropped(db: Database, people: People) -> None:
    first = declared(db, people)
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        use_case = use_case_of(session, first)
        review = service.open_review(session, use_case)
        assert review is not None
        assert service.withdraw(session, member, review) is None
    with db.read() as session:
        use_case = use_case_of(session, first)
        assert use_case.status == "approved_with_conditions"
        assert service.open_review(session, use_case) is None
        assert session.get(IntakeDraft, use_case.id) is None


def linked(db: Database, people: People) -> tuple[str, str, str]:
    """A use that uses a system that is built on a model. Returns their references."""
    governance = who(db, people, "governance")
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
        with db.write(ME.actor) as session:
            model = records.create(
                session,
                governance,
                MODEL,
                {"name": "Lumen Large", "kind": "language", "origin": "open_weights"},
            )
            system = records.create(
                session, governance, SYSTEM,
                {"name": "Lumen Assistant", "kind": "open_source", "catalog_status": "approved",
                 "permitted_data_class": "protected"},
            )  # fmt: skip
            use_case = use_case_of(session, first)
            links.add(session, governance, system.ref, "built_on", model.ref)
            links.add(session, governance, use_case.ref, "uses", system.ref)
            return use_case.ref, system.ref, model.ref


def test_retiring_a_record_tells_the_owners_of_what_relies_on_it(
    db: Database, people: People
) -> None:
    use_ref, system_ref, _ = linked(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(governance.actor) as session:
        system = find(session, SYSTEM, system_ref)
        with pytest.raises(PermissionDenied):
            retirement.retire(session, member, SYSTEM, system, "I no longer like it.")
        with pytest.raises(Invalid):
            retirement.retire(session, governance, SYSTEM, system, "old")
        _, told = retirement.retire(
            session, governance, SYSTEM, system, "The supplier withdrew it."
        )
        assert told == 1
        with pytest.raises(Conflict):
            retirement.retire(session, governance, SYSTEM, system, "The supplier withdrew it.")
    assert "Lumen Assistant, which Summarize lab meeting notes relies on, has been retired" in (
        notices(db, people, "member")
    )
    with db.read() as session:
        system = find(session, SYSTEM, system_ref)
        assert (system.status, system.catalog_status) == ("retired", "retired")  # type: ignore[attr-defined]
        titles = [e["title"] for e in history.for_record(session, SYSTEM, system)]
        assert "Retired" in titles
        assert find(session, USE_CASE, use_ref).status == "approved_with_conditions"  # type: ignore[attr-defined]


def test_findings_are_inherited_from_everything_a_record_relies_on(
    db: Database, people: People
) -> None:
    use_ref, system_ref, model_ref = linked(db, people)
    governance = who(db, people, "governance")
    with db.read() as session:
        clean = findings.for_record(session, governance, USE_CASE, find(session, USE_CASE, use_ref))
        assert clean == {"own": [], "inherited": []}
    with db.write(governance.actor) as session:
        model = find(session, MODEL, model_ref)
        records.update(session, governance, MODEL, model, {"catalog_status": "not_approved"},
                       version=model.version)  # type: ignore[attr-defined]  # fmt: skip
    with db.read() as session:
        on_model = findings.for_record(session, governance, MODEL, find(session, MODEL, model_ref))
        assert [f["text"] for f in on_model["own"]] == ["It is not approved for use"]
        on_use = findings.for_record(
            session, governance, USE_CASE, find(session, USE_CASE, use_ref)
        )
        [inherited] = on_use["inherited"]
        assert inherited["inherited"] and inherited["from"]["ref"] == model_ref
        assert (inherited["distance"], inherited["tone"]) == (2, "danger")
        on_system = findings.for_record(
            session, governance, SYSTEM, find(session, SYSTEM, system_ref)
        )
        assert on_system["inherited"][0]["distance"] == 1 and on_system["own"] == []


def test_change_retire_and_findings_over_the_api(
    db: Database, people: People, as_role: Clients
) -> None:
    use_ref, system_ref, _ = linked(db, people)
    member, governance = as_role("member"), as_role("governance")
    assert as_role("reviewer").post(
        f"/api/v1/use-cases/{use_ref}/change", json={"summary": "It has changed a lot."}
    ).status_code in (403, 404)
    made = member.post(f"/api/v1/use-cases/{use_ref}/change", json={"summary": "More data now."})
    assert made.status_code == 201 and made.json()["data"]["review"].startswith("RV-")
    assert (
        member.get(f"/api/v1/use-cases/{use_ref}/intake").json()["data"]["confirming"]["kind"]
        == "change"
    )
    assert (
        member.post(
            f"/api/v1/records/{system_ref}/retire", json={"reason": "Not mine to end."}
        ).status_code
        == 403
    )
    retired = governance.post(
        f"/api/v1/records/{system_ref}/retire", json={"reason": "The supplier withdrew it."}
    )
    assert retired.status_code == 200 and retired.json()["meta"]["dependents"] == 1
    found = member.get(f"/api/v1/records/{use_ref}/findings").json()["data"]
    assert [f["text"] for f in found["inherited"]] == ["It has been retired"]
    assert found["inherited"][0]["from"]["name"] == "Lumen Assistant"
