"""Incidents and actions: anyone reports, governance triages and links records, may suspend
an approval or open a review, and everything someone must do as a result is one list."""

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
from govwren.inventory.registry import MODEL, USE_CASE, find
from govwren.oversight import actions, findings, incidents
from govwren.review import service, views
from tests.people import People
from tests.test_changes import linked
from tests.test_review import MONDAY, notices, who
from tests.test_schedule import at, watch

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
WHAT = {
    "title": "A summary named the wrong participant",
    "description": "A generated summary attributed a quote to the wrong person in the notes.",
}


def reported(
    db: Database, people: People, by: str = "reviewer", **more: Any
) -> tuple[str, str, str]:
    """An incident reported against the model that a system and a use rely on. Returns the
    incident's reference, the use's, and the model's."""
    use_ref, _, model_ref = linked(db, people)
    reporter = who(db, people, by)
    with frozen_at(MONDAY), db.write(reporter.actor) as session:
        incident = incidents.report(session, reporter, **{**WHAT, "records": [model_ref], **more})
        return incident.ref, use_ref, model_ref


def triaged(db: Database, people: People, **more: Any) -> tuple[str, str, str]:
    ref, use_ref, model_ref = reported(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incidents.triage(
            session,
            governance,
            incidents.find(session, ref),
            **{
                "category": "wrong_output",
                "severity": "high",
                "records": [model_ref, use_ref],
                **more,
            },
        )
    return ref, use_ref, model_ref


def test_anyone_reports_and_governance_is_told(db: Database, people: People) -> None:
    ref, _, model_ref = reported(db, people)
    assert any("Incident reported" in title for title in notices(db, people, "governance"))
    with db.read() as session:
        incident = incidents.find(session, ref)
        seen = incidents.view(session, who(db, people, "reviewer"), incident)
        assert (seen["status"], seen["severity"]) == ("reported", None)
        assert [record["ref"] for record in seen["records"]] == [model_ref]
        assert seen["can"] == {"triage": False, "progress": False, "act": False}
        with pytest.raises(NotFound):  # not theirs, and not about anything of theirs
            incidents.view(session, who(db, people, "member"), incident)
        work = views.my_work(session, who(db, people, "governance"))
        assert "Triage an incident: A summary named the wrong participant" in [
            i["title"] for i in work
        ]
    reviewer = who(db, people, "reviewer")
    with db.write(reviewer.actor) as session, pytest.raises(Invalid) as bad:
        incidents.report(session, reviewer, title="x", description="short", records=["UC-9999"])
    assert set(bad.value.errors) == {"title", "description"}


def test_triage_sets_category_severity_and_the_records_involved(
    db: Database, people: People
) -> None:
    ref, use_ref, model_ref = reported(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incident = incidents.find(session, ref)
        with pytest.raises(PermissionDenied):
            incidents.triage(session, member, incident, category="misuse", severity="low")
        with pytest.raises(Invalid) as bad:
            incidents.triage(session, governance, incident, category="odd", severity="huge")
        assert set(bad.value.errors) == {"category", "severity"}
        incidents.triage(
            session,
            governance,
            incident,
            category="wrong_output",
            severity="high",
            records=[model_ref, use_ref],
        )
        assert (incident.status, incident.lead_id) == ("open", governance.account_id)
    assert any("involves a record of yours" in title for title in notices(db, people, "member"))
    with db.read() as session:
        seen = incidents.view(
            session, member, incidents.find(session, ref)
        )  # now it is about theirs
        assert seen["category_label"] == "Wrong or harmful output"
        titles = [
            e["title"]
            for e in history.for_record(session, USE_CASE, find(session, USE_CASE, use_ref))
        ]
        assert f"Linked to incident {ref}" in titles


def test_an_open_incident_is_a_finding_on_everything_that_relies_on_the_record(
    db: Database, people: People
) -> None:
    ref, use_ref, model_ref = reported(db, people)
    governance = who(db, people, "governance")
    with db.read() as session:  # a report is not yet a finding
        assert findings.for_record(
            session, governance, USE_CASE, find(session, USE_CASE, use_ref)
        ) == {
            "own": [],
            "inherited": [],
        }
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incidents.triage(
            session,
            governance,
            incidents.find(session, ref),
            category="wrong_output",
            severity="high",
        )
    with db.read() as session:
        own = findings.for_record(session, governance, MODEL, find(session, MODEL, model_ref))[
            "own"
        ]
        assert [(f["kind"], f["tone"], f["ref"]) for f in own] == [("incident", "danger", ref)]
        [inherited] = findings.for_record(
            session, governance, USE_CASE, find(session, USE_CASE, use_ref)
        )["inherited"]
        assert inherited["from"]["ref"] == model_ref and inherited["distance"] == 2
        assert inherited["inherited"] is True and ref in inherited["text"]


def test_suspending_an_approval_and_lifting_it(db: Database, people: People) -> None:
    ref, use_ref, model_ref = triaged(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incident = incidents.find(session, ref)
        with pytest.raises(Invalid):  # a model has no approval to suspend
            incidents.suspend(session, governance, incident, model_ref, "Stop using it for now.")
        with pytest.raises(Invalid):
            incidents.suspend(session, governance, incident, use_ref, "no")
        use_case = incidents.suspend(
            session, governance, incident, use_ref, "Until the cause is known."
        )
        assert use_case.status == "suspended"
        with pytest.raises(Conflict):
            incidents.suspend(session, governance, incident, use_ref, "Until the cause is known.")
        with pytest.raises(Invalid) as held:  # it cannot be closed with an approval suspended
            incidents.progress(
                session,
                governance,
                incident,
                status="closed",
                containment="The summaries were recalled.",
                cause="The transcript had two speakers merged.",
                lessons="Check speaker labels before summarizing.",
            )
        assert "still suspended" in held.value.errors["status"]
    assert any("Approval suspended" in title for title in notices(db, people, "member"))
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        use_case = incidents.lift(
            session,
            governance,
            incidents.find(session, ref),
            use_ref,
            "The cause was found and fixed.",
        )
        assert use_case.status == "approved_with_conditions"  # back where it was
        entries = history.for_record(session, USE_CASE, use_case)
        titles = [entry["title"] for entry in entries]
        assert "Approval suspended" in titles and "Suspension lifted" in titles


def test_an_incident_review_decides_what_becomes_of_a_suspended_approval(
    db: Database, people: People
) -> None:
    ref, use_ref, _ = triaged(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incident = incidents.find(session, ref)
        incidents.suspend(session, governance, incident, use_ref, "Until it has been looked at.")
        review = incidents.open_review(
            session, governance, incident, use_ref, "Is the oversight described still enough?"
        )
        assert (review.kind, review.status, review.routing["incident"]["ref"]) == (
            "incident",
            "triage",
            ref,
        )
        with pytest.raises(Conflict):
            incidents.open_review(session, governance, incident, use_ref, "A second look as well.")
        use_case = find(session, USE_CASE, use_ref)
        until = use_case.approved_until  # type: ignore[attr-defined]
        service.triage(session, governance, review)
        service.decide(
            session,
            governance,
            review,
            outcome="approved",
            rationale="The cause is fixed and the oversight is enough.",
        )
        assert (use_case.status, use_case.approved_until) == ("approved", until)  # type: ignore[attr-defined]
        seen = incidents.view(session, governance, incident)
        assert not any(record["suspended"] for record in seen["records"])
        incidents.progress(
            session,
            governance,
            incident,
            status="closed",
            containment="The summaries were recalled.",
            cause="The transcript had two speakers merged.",
            lessons="Check speaker labels before summarizing.",
        )
        assert incident.status == "closed"
    assert any("you reported is closed" in title for title in notices(db, people, "reviewer"))
    with db.read() as session:  # closed incidents are no longer findings
        found = findings.for_record(session, governance, USE_CASE, find(session, USE_CASE, use_ref))
        assert found == {"own": [], "inherited": []}


def test_actions_and_conditions_are_one_list(db: Database, people: People) -> None:
    ref, use_ref, _ = triaged(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    due = MONDAY.date() + timedelta(days=14)
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        incident = incidents.find(session, ref)
        with pytest.raises(Invalid) as bad:
            incidents.add_action(
                session, governance, incident, title="", owner_id=None, due_on=None
            )
        assert set(bad.value.errors) == {"title", "owner_id", "due_on"}
        action = incidents.add_action(
            session,
            governance,
            incident,
            title="Re-run the affected summaries",
            owner_id=member.account_id,
            due_on=due,
            record=use_ref,
        )
        assert action.ref == "ACT-0001"
        use_case = find(session, USE_CASE, use_ref)
        review = service.latest_review(session, use_case)  # type: ignore[arg-type]
        assert review is not None
    assert "An action for you: Re-run the affected summaries" in notices(db, people, "member")
    with frozen_at(MONDAY), db.read() as session:
        mine = actions.listing(session, member)
        assert [(row["kind"], row["id"]) for row in mine] == [("action", "ACT-0001")]
        assert mine[0]["source"] == {"label": f"Incident {ref}", "href": f"/incidents/{ref}"}
        assert (
            mine[0]["about"]["ref"] == use_ref
            and mine[0]["can_close"]
            and not mine[0]["can_cancel"]
        )
        assert actions.listing(session, member, scope="all") == mine  # "all" is not theirs to ask
        assert [row["id"] for row in actions.listing(session, governance, scope="all")] == [
            "ACT-0001"
        ]
        work = views.my_work(session, member)
        assert ("action", "Re-run the affected summaries") in [
            (i["kind"], i["title"]) for i in work
        ]
        seen = incidents.view(session, member, incidents.find(session, ref))
        assert [a["id"] for a in seen["actions"]] == ["ACT-0001"]
    with frozen_at(at(due - timedelta(days=2))):
        assert watch(db)["reminders"] == 1
    with frozen_at(at(due + timedelta(days=1))):
        assert watch(db)["reminders"] == 2  # the owner, and governance
        with db.read() as session:
            assert actions.listing(session, member)[0]["overdue"]
    reviewer = who(db, people, "reviewer")
    with db.write(member.actor) as session:
        action = actions.find(session, "ACT-0001")
        with pytest.raises(PermissionDenied):
            actions.close(session, reviewer, action, status="done", note="I did it for them.")
        with pytest.raises(PermissionDenied):
            actions.close(session, member, action, status="cancelled", note="Not needed any more.")
        with pytest.raises(Invalid):
            actions.close(session, member, action, status="done", note="")
        actions.close(
            session, member, action, status="done", note="All twelve were re-run and checked."
        )
        with pytest.raises(Conflict):
            actions.close(session, member, action, status="done", note="Done a second time.")
    with db.read() as session:
        assert actions.listing(session, member) == []
        assert [row["status"] for row in actions.listing(session, member, status="all")] == ["done"]
    assert any(title.startswith("Action done") for title in notices(db, people, "governance"))


def test_a_report_that_is_not_an_incident_is_dismissed_with_a_reason(
    db: Database, people: People
) -> None:
    ref, _, _ = reported(db, people)
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        incident = incidents.find(session, ref)
        with pytest.raises(Invalid):
            incidents.triage(session, governance, incident, category="", severity="", dismiss="no")
        incidents.triage(
            session,
            governance,
            incident,
            category="",
            severity="",
            dismiss="The summary was right; the notes were wrong.",
        )
        assert incident.status == "dismissed"
        with pytest.raises(Conflict):
            incidents.triage(session, governance, incident, category="other", severity="low")
    assert any("looked at and closed" in title for title in notices(db, people, "reviewer"))
    with db.read() as session:
        assert incidents.register(session, governance, status="open") == []
        assert [row["status"] for row in incidents.register(session, governance)] == ["dismissed"]


def test_incidents_and_actions_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    use_ref, _, _ = linked(db, people)
    member, governance = as_role("member"), as_role("governance")
    made = member.post("/api/v1/incidents", json={**WHAT, "records": [use_ref]})
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    assert ref == "INC-0001"
    assert as_role("reviewer").get(f"/api/v1/incidents/{ref}").status_code == 404
    assert (
        member.post(
            f"/api/v1/incidents/{ref}/triage", json={"category": "misuse", "severity": "low"}
        ).status_code
        == 403
    )
    triage = governance.post(
        f"/api/v1/incidents/{ref}/triage", json={"category": "wrong_output", "severity": "moderate"}
    )
    assert triage.json()["data"]["status"] == "open"
    held = governance.post(
        f"/api/v1/incidents/{ref}/suspend",
        json={"record": use_ref, "reason": "Until we know more."},
    )
    assert held.json()["data"]["records"][0]["suspended"] is True
    assert member.get(f"/api/v1/use-cases/{use_ref}").json()["data"]["status"] == "suspended"
    opened = governance.post(
        f"/api/v1/incidents/{ref}/review",
        json={"record": use_ref, "reason": "Look at the oversight again."},
    )
    assert opened.json()["data"]["records"][0]["review"].startswith("RV-")
    me = member.get("/api/v1/session").json()["data"]["account"]["id"]
    acted = governance.post(
        f"/api/v1/incidents/{ref}/actions",
        json={
            "title": "Tell the participants affected",
            "owner_id": me,
            "due_on": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert acted.status_code == 201
    listed = member.get("/api/v1/actions").json()["data"]
    assert [row["title"] for row in listed] == ["Tell the participants affected"]
    done = member.post(f"/api/v1/actions/{listed[0]['id']}/close", json={"note": "All were told."})
    assert done.json()["data"]["status"] == "done"
    assert [
        row["ref"] for row in governance.get("/api/v1/incidents?status=open").json()["data"]
    ] == [ref]
