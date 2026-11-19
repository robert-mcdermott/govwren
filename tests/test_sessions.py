"""Committee sessions, named risk acceptance, and spot checks of automatic approvals."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import jobs
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Decision, SpotCheck
from govwren.inventory.registry import USE_CASE
from govwren.review import service, sessions, spotchecks, views
from tests.conftest import Instance
from tests.people import People
from tests.test_intake import CASES, SIMPLE
from tests.test_review import HIGH, MONDAY, get, notices, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
CRITICAL: dict[str, Any] = dict(CASES)["critical"]
MEETING = date(2026, 11, 5)


def ready(db: Database, people: People, answers: dict[str, Any]) -> str:
    """A request triaged with nothing left for reviewers, so it is ready for a decision."""
    with frozen_at(MONDAY):
        ref = request(db, people, answers)
        governance = who(db, people, "governance")
        with db.write(governance.actor) as session:
            review = get(session, ref)
            required = [task.review_function for task in service.tasks_of(session, review)]
            if review.authority == "committee_with_acceptance":  # the rules also want this
                impact_assessed(db, people, session, review)
            service.triage(
                session,
                governance,
                review,
                remove=required,
                reason="Reviewed by the committee itself.",
            )
    return ref


def impact_assessed(db: Database, people: People, session: Any, review: Any) -> None:
    """The owner submits the impact assessment that the rules require at the critical tier."""
    from govwren.assurance import assessments

    form = assessments.template(assessments.IMPACT)
    replies = {
        q["key"]: q["options"][0]["key"] if q["type"] == "choice" else "Described in full."
        for q in assessments.questions(form)
    }
    assessments.save(
        session,
        who(db, people, "member"),
        USE_CASE,
        service.subject_of(session, review),
        assessments.IMPACT,
        replies,
        submit=True,
    )


def planned(db: Database, people: People, *reviews: str) -> str:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        meeting = sessions.plan(
            session, governance, title="November committee", held_on=MEETING, reviews=reviews
        )
        return meeting.ref


# --- Sessions -----------------------------------------------------------------------------


def test_a_session_has_an_agenda_of_reviews_awaiting_the_committee(
    db: Database, people: People
) -> None:
    first, second = ready(db, people, HIGH), ready(db, people, {**HIGH, "name": "A second use"})
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.read() as session:
        waiting = [row["ref"] for row in sessions.candidates(session)]
        assert waiting == [first, second]
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        with pytest.raises(PermissionDenied):
            sessions.plan(session, member, title="Mine", held_on=MEETING)
        with pytest.raises(Invalid) as bad:
            sessions.plan(session, governance, title="", held_on=None)
        assert set(bad.value.errors) == {"title", "held_on"}
        with pytest.raises(Invalid):
            sessions.plan(
                session, governance, title="Bad agenda", held_on=MEETING, reviews=["RV-9999"]
            )
    ref = planned(db, people, second, first)
    with db.read() as session:
        seen = sessions.view(session, governance, sessions.find(session, ref))
        assert [item["review"] for item in seen["agenda"]] == [second, first]  # in the order given
        assert seen["agenda"][0]["use_case"]["name"] == "A second use"
        assert seen["candidates"] == [] and seen["can_edit"]
        packet = views.packet(session, governance, get(session, first))
        assert packet["session"]["ref"] == ref


def test_decisions_made_in_a_session_record_it_and_closing_fixes_the_minutes(
    db: Database, people: People
) -> None:
    first, second = ready(db, people, HIGH), ready(db, people, {**HIGH, "name": "A second use"})
    ref = planned(db, people, first)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        with pytest.raises(Conflict):  # not on the agenda
            service.decide(
                session,
                governance,
                get(session, second),
                outcome="approved",
                rationale="Approved by the committee.",
                at_session=ref,
            )
        service.decide(
            session,
            governance,
            get(session, first),
            outcome="approved",
            rationale="Approved by the committee.",
            at_session=ref,
        )
        meeting = sessions.find(session, ref)
        with pytest.raises(Invalid) as bad:
            sessions.record(session, governance, meeting, close=True)
        assert set(bad.value.errors) == {"attendees", "minutes"}
        sessions.record(
            session,
            governance,
            meeting,
            attendees="Governance Person, Auditor Person",
            minutes="One request considered and approved. No recusals.",
            close=True,
        )
        with pytest.raises(Conflict):
            sessions.record(session, governance, meeting, minutes="A different account.")
        with pytest.raises(Conflict):
            sessions.set_agenda(session, governance, meeting, [second])
        with pytest.raises(Conflict):  # nothing more is decided in a closed session
            service.decide(
                session,
                governance,
                get(session, second),
                outcome="approved",
                rationale="Approved after the meeting.",
                at_session=ref,
            )
    with db.read() as session:
        seen = sessions.view(session, who(db, people, "auditor"), sessions.find(session, ref))
        assert (seen["status"], seen["can_edit"]) == ("closed", False)
        [item] = seen["agenda"]
        assert (
            item["decision"]["words"] == "Approved"
            and item["decision"]["decided_by"] == "Governance Person"
        )
        [row] = sessions.listing(session)
        assert (row["items"], row["decided"]) == (1, 1)
        decision = session.scalars(select(Decision).where(Decision.session_id.is_not(None))).one()
        assert decision.review_id == get(session, first).id


# --- Risk acceptance ----------------------------------------------------------------------


def test_where_the_rules_require_it_a_named_person_must_accept_the_risk(
    db: Database, people: People
) -> None:
    ref = ready(db, people, CRITICAL)
    governance, auditor, member = (who(db, people, r) for r in ("governance", "auditor", "member"))
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        review = get(session, ref)
        assert review.authority == "committee_with_acceptance"
        assert views.packet(session, governance, review)["acceptance"]["status"] == "needed"
        with pytest.raises(Conflict) as blocked:
            service.decide(
                session,
                governance,
                review,
                outcome="approved",
                rationale="Approved by the committee.",
            )
        assert "accept the risk" in str(blocked.value)
        with pytest.raises(Invalid):  # not someone on the asking side
            service.request_acceptance(session, governance, review, member.account_id)
        with pytest.raises(PermissionDenied):
            service.request_acceptance(session, member, review, auditor.account_id)
        service.request_acceptance(session, governance, review, auditor.account_id)
        with pytest.raises(Conflict) as waiting:
            service.decide(
                session,
                governance,
                review,
                outcome="approved",
                rationale="Approved by the committee.",
            )
        assert "has not answered" in str(waiting.value)
    assert any("asked to accept the risk" in title for title in notices(db, people, "auditor"))
    with frozen_at(MONDAY), db.write(auditor.actor) as session:
        review = get(session, ref)
        packet = views.packet(session, auditor, review)
        assert packet["acceptance"]["can_answer"] and packet["internal"]  # they see the findings
        assert [i["kind"] for i in views.my_work(session, auditor)] == ["acceptance"]
        with pytest.raises(PermissionDenied):
            service.answer_acceptance(
                session, governance, review, accept=True, statement="I accept it on their behalf."
            )
        with pytest.raises(Invalid):
            service.answer_acceptance(session, auditor, review, accept=True, statement="ok")
        service.answer_acceptance(
            session,
            auditor,
            review,
            accept=True,
            statement="I accept the residual risk for one year.",
        )
        with pytest.raises(Conflict):
            service.answer_acceptance(
                session, auditor, review, accept=False, statement="On reflection I do not."
            )
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        review = get(session, ref)
        decision = service.decide(
            session,
            governance,
            review,
            outcome="approved",
            rationale="Approved by the committee, with the risk accepted.",
        )
        assert decision.outcome.startswith("approved")
        seen = views.packet(session, governance, review)["acceptance"]
        assert (seen["status"], seen["name"]) == ("accepted", "Auditor Person")
        assert seen["statement"] == "I accept the residual risk for one year."


def test_a_declined_acceptance_blocks_approval_until_someone_else_accepts(
    db: Database, people: People
) -> None:
    ref = ready(db, people, CRITICAL)
    governance, auditor, steward = (
        who(db, people, r) for r in ("governance", "auditor", "steward")
    )
    with frozen_at(MONDAY):
        with db.write(governance.actor) as session:
            service.request_acceptance(session, governance, get(session, ref), auditor.account_id)
        with db.write(auditor.actor) as session:
            service.answer_acceptance(
                session,
                auditor,
                get(session, ref),
                accept=False,
                statement="The stop mechanism has not been tested.",
            )
        with db.write(governance.actor) as session:
            review = get(session, ref)
            with pytest.raises(Conflict):
                service.decide(
                    session,
                    governance,
                    review,
                    outcome="approved",
                    rationale="Approved by the committee.",
                )
            service.request_acceptance(session, governance, review, steward.account_id)
            assert service.acceptance_of(session, review).account_id == steward.account_id  # type: ignore[union-attr]
            service.decide(
                session,
                governance,
                review,
                outcome="declined",
                rationale="Nobody will accept the risk as it stands.",
            )
    assert any("Risk not accepted" in title for title in notices(db, people, "governance"))


def test_requests_that_need_no_acceptance_are_unchanged(db: Database, people: People) -> None:
    ref = ready(db, people, HIGH)
    governance, auditor = who(db, people, "governance"), who(db, people, "auditor")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        review = get(session, ref)
        assert views.packet(session, governance, review)["acceptance"] is None
        with pytest.raises(Conflict):
            service.request_acceptance(session, governance, review, auditor.account_id)
        service.decide(
            session, governance, review, outcome="approved", rationale="Approved by the committee."
        )


# --- Spot checks --------------------------------------------------------------------------


def automatic(db: Database, people: People, count: int) -> list[str]:
    with frozen_at(MONDAY):
        return [
            request(db, people, {**SIMPLE, "name": f"Everyday use {n}"}, "steward")
            for n in range(count)
        ]


def test_governance_draws_a_sample_of_automatic_approvals_and_checks_them(
    db: Database, people: People
) -> None:
    automatic(db, people, 6)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        with pytest.raises(PermissionDenied):
            spotchecks.draw(session, member, 3)
        with pytest.raises(Invalid):
            spotchecks.draw(session, governance, 0)
        assert spotchecks.draw(session, governance, 4) == 4
        assert spotchecks.draw(session, governance, 5) == 2  # only what is left
        with pytest.raises(Conflict):
            spotchecks.draw(session, governance, 1)
        seen = spotchecks.listing(session, governance)
        assert (seen["pending"], seen["checked"], seen["agreement"], seen["available"]) == (
            6,
            0,
            None,
            0,
        )
        first, second = seen["checks"][0], seen["checks"][1]
        assert first["rule"] == "Minimal tier: approved by rule" and first["can_check"]
        assert views.my_work(session, governance)[0]["title"] == "Spot-check 6 automatic approvals"
        spotchecks.check(session, governance, first["id"], agree=True, note="")
        with pytest.raises(Conflict):
            spotchecks.check(session, governance, first["id"], agree=True, note="")
        with pytest.raises(Invalid):
            spotchecks.check(session, governance, second["id"], agree=False, note="no")
        with pytest.raises(NotFound):
            spotchecks.check(session, governance, 9999, agree=True, note="")
        spotchecks.check(
            session,
            governance,
            second["id"],
            agree=False,
            note="The summary says health data is involved.",
        )
        seen = spotchecks.listing(session, governance)
        assert (seen["pending"], seen["checked"], seen["agreed"], seen["agreement"]) == (
            4,
            2,
            1,
            50,
        )
        called = next(c for c in seen["checks"] if c["status"] == "disagreed")
        review = get(session, called["followup"])
        assert (review.kind, review.status) == ("periodic", "triage")
        assert review.routing["spot_check"]["decision_of"] == called["review"]
        assert (
            service.subject_of(session, review).status == "approved_with_conditions"
        )  # until decided
    assert (
        any("Review called in to triage" in title for title in notices(db, people, "governance"))
        is False
    )
    assert (
        any("Review called in to triage" in title for title in notices(db, people, "admin"))
        is False
    )


def test_the_scheduler_draws_its_share_once(instance: Instance, people: People) -> None:
    db = instance.db
    automatic(db, people, 40)
    with frozen_at(MONDAY):
        first = jobs.run_job(db, instance.config, "spot-checks", force=True)
        assert first is not None and first["status"] == "ok"
        drawn = first["counts"]["drawn_to_check"]
        assert 1 <= drawn <= 12  # about one in ten of forty
        again = jobs.run_job(db, instance.config, "spot-checks", force=True)
        assert again is not None and again["counts"]["drawn_to_check"] == 0
        with db.read() as session:
            checks = session.scalars(select(SpotCheck)).all()
            assert len(checks) == drawn and all(c.sampled_by is None for c in checks)
    assert any("to spot-check" in title for title in notices(db, people, "governance"))


def test_sessions_acceptance_and_spot_checks_over_the_api(
    db: Database, people: People, as_role: Clients
) -> None:
    ref = ready(db, people, CRITICAL)
    automatic(db, people, 3)
    governance, auditor, member = as_role("governance"), as_role("auditor"), as_role("member")
    assert member.get("/api/v1/sessions").status_code == 403
    made = governance.post(
        "/api/v1/sessions", json={"title": "Committee", "held_on": "2026-11-05", "reviews": [ref]}
    )
    assert made.status_code == 201
    meeting = made.json()["data"]["ref"]
    assert meeting == "SES-0001"
    assert (
        auditor.get(f"/api/v1/sessions/{meeting}").json()["data"]["agenda"][0]["acceptance"]
        == "needed"
    )
    body = {"outcome": "approved", "rationale": "Approved by the committee.", "session": meeting}
    assert governance.post(f"/api/v1/reviews/{ref}/decision", json=body).status_code == 409
    me = auditor.get("/api/v1/session").json()["data"]["account"]["id"]
    asked = governance.post(f"/api/v1/reviews/{ref}/acceptance", json={"account_id": me})
    assert asked.json()["data"]["acceptance"]["status"] == "requested"
    answered = auditor.post(
        f"/api/v1/reviews/{ref}/acceptance/answer",
        json={"accept": True, "statement": "I accept the risk as described."},
    )
    assert answered.json()["data"]["acceptance"]["status"] == "accepted"
    assert governance.post(f"/api/v1/reviews/{ref}/decision", json=body).status_code == 200
    closed = governance.put(
        f"/api/v1/sessions/{meeting}",
        json={"attendees": "All members", "minutes": "One request approved.", "close": True},
    )
    assert closed.json()["data"]["status"] == "closed"
    assert closed.json()["data"]["agenda"][0]["decision"]["outcome"].startswith("approved")
    drawn = governance.post("/api/v1/spot-checks", json={"count": 2})
    assert drawn.status_code == 201 and drawn.json()["meta"]["drawn"] == 2
    check = drawn.json()["data"]["checks"][0]["id"]
    done = governance.post(f"/api/v1/spot-checks/{check}", json={"agree": True})
    assert done.json()["data"]["checked"] == 1
    assert auditor.get("/api/v1/spot-checks").json()["data"]["can_draw"] is False
