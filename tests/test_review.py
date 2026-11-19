"""Review and decisions: routing by rule, triage, findings, discussion, decisions, conditions,
and the two rules that hold throughout: nobody judges their own request, and what reviewers
say among themselves stays among them."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.access.principal import Grant, Principal
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Condition, Decision, Notification, Review
from govwren.intake import service as intake
from govwren.inventory import history
from govwren.inventory.registry import USE_CASE, find
from govwren.people import accounts
from govwren.review import service, views
from tests.people import ME, PASSWORD, People
from tests.test_intake import SIMPLE

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
MONDAY = datetime(2026, 11, 2, 15, 0, tzinfo=UTC)
HIGH = {**SIMPLE, "impact": "serious"}  # a floor makes it High: privacy and security must review
MODERATE = {**SIMPLE, "data_class": "protected", "reach": "one_unit", "decision_role": "informs"}
REASON = "It also touches a contract we have not seen."


def who(db: Database, people: People, role: str) -> Principal:
    with db.read() as session:
        return accounts.principal_for(session, accounts.get(session, people.accounts[role]))


def request(db: Database, people: People, answers: dict[str, Any], by: str = "member") -> str:
    principal = who(db, people, by)
    with db.write(principal.actor) as session:
        use_case = intake.start(session, principal, {**answers, "unit": people.units["HALE"]})
        intake.submit(session, principal, use_case)
        return service.latest_review(session, use_case).ref  # type: ignore[union-attr]


def get(session: Any, ref: str) -> Review:
    return session.scalars(select(Review).where(Review.ref == ref)).one()


@pytest.fixture
def security(db: Database, people: People) -> Principal:
    """A second reviewer, for information security."""
    with db.write(ME.actor) as session:
        account = accounts.create(
            session,
            ME,
            email="security@alderpoint.example",
            display_name="Security Person",
            password=PASSWORD,
            grants=[Grant("reviewer", review_function="security")],
        )
        people.accounts["security"] = account.id
        return accounts.principal_for(session, account)


def notices(db: Database, people: People, role: str) -> list[str]:
    with db.read() as session:
        return list(
            session.scalars(
                select(Notification.title)
                .where(Notification.account_id == people.accounts[role])
                .order_by(Notification.id)
            )
        )


def test_working_days_skip_weekends_and_months_keep_the_day() -> None:
    assert service.working_days_from(date(2026, 11, 2), 5) == date(2026, 11, 9)  # Monday to Monday
    assert service.working_days_from(date(2026, 11, 6), 1) == date(2026, 11, 9)  # Friday to Monday
    assert service.working_days_from(date(2026, 11, 7), 1) == date(2026, 11, 9)  # from a weekend
    assert service.add_months(date(2026, 11, 30), 3) == date(2027, 2, 28)
    assert service.add_months(date(2026, 1, 15), 36) == date(2029, 1, 15)


def test_a_minimal_request_is_approved_by_rule_on_the_spot(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        ref = request(db, people, SIMPLE)
    with db.read() as session:
        review = get(session, ref)
        use_case = service.subject_of(session, review)
        [decision] = session.scalars(select(Decision).where(Decision.review_id == review.id)).all()
        conditions = service.conditions_of(session, use_case)
        assert (review.status, use_case.status) == ("decided", "approved_with_conditions")
        assert (decision.by_rule, decision.decided_by, decision.authority) == (
            "Minimal tier: approved by rule",
            None,
            "rule",
        )
        assert "Approved by rule" in decision.rationale
        assert use_case.approved_until == date(2029, 11, 2) == use_case.next_review_on
        assert [c.template_key for c in conditions] == [
            "check_outputs",
            "stay_within_data",
            "declare_changes",
            "report_incidents",
            "no_restricted_data",
        ]
        assert {c.owner_id for c in conditions} == {
            people.accounts["member"]
        } and service.in_effect(session, use_case)
        assert service.tasks_of(session, review) == []
    assert notices(db, people, "governance") == []  # nothing for anyone to do


def test_a_rule_that_requires_a_review_stops_approval_by_rule(db: Database, people: People) -> None:
    answers = {
        **SIMPLE,
        "data_categories": ["health"],
        "deidentified": True,
        "minimum_necessary": True,
    }
    ref = request(db, people, answers)
    with db.read() as session:
        review = get(session, ref)
        assert review.tier_at_open == 1 and review.status == "triage"
        assert [t.review_function for t in service.tasks_of(session, review)] == ["privacy"]
        assert service.subject_of(session, review).status == "in_review"


def test_a_prohibited_use_is_never_approved(db: Database, people: People) -> None:
    answers = {
        **SIMPLE,
        "outputs_used_for": ["peer_review"],
        "disclosure": True,
        "verification": "By hand.",
    }
    ref = request(db, people, answers)
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        review = get(session, ref)
        assert (
            review.tier_at_open == 1 and review.status == "triage"
        )  # minimal, yet not approved by rule
        service.triage(session, governance, review)
        with pytest.raises(Conflict, match="prohibited use and cannot be approved"):
            service.decide(
                session,
                governance,
                review,
                outcome="approved",
                rationale="It seems harmless enough.",
            )
        declined = service.decide(
            session,
            governance,
            review,
            outcome="declined",
            rationale="Peer review is confidential.",
        )
        assert (
            declined.outcome == "declined"
            and service.subject_of(session, review).status == "declined"
        )


def test_a_high_tier_request_from_triage_to_decision(
    db: Database, people: People, security: Principal
) -> None:
    member, governance, reviewer = (
        who(db, people, role) for role in ("member", "governance", "reviewer")
    )
    with frozen_at(MONDAY):
        ref = request(db, people, HIGH)
    assert notices(db, people, "governance") == [
        "New request to triage: Summarize lab meeting notes"
    ]
    with frozen_at(MONDAY + timedelta(hours=2)), db.write(governance.actor) as session:
        review = get(session, ref)
        use_case = service.subject_of(session, review)
        assert (review.status, review.authority, review.due_on) == (
            "triage",
            "committee",
            date(2026, 11, 23),
        )
        assert [(t.review_function, t.required_by) for t in service.tasks_of(session, review)] == [
            ("privacy", "High tier: full review"),
            ("security", "High tier: full review"),
        ]
        privacy, _security = service.tasks_of(session, review)
        with pytest.raises(Conflict, match="not been triaged"):
            service.complete_task(session, reviewer, review, privacy.id, finding="no_concerns")
        with pytest.raises(Conflict, match="Triage this request"):
            service.decide(
                session,
                governance,
                review,
                outcome="approved",
                rationale="Looks fine to me overall.",
            )
        with pytest.raises(Invalid) as caught:
            service.triage(
                session, governance, review, add=["legal", "astrology"], remove=["ethics"]
            )
        assert set(caught.value.errors) == {"add", "remove", "reason"}
        service.triage(
            session, governance, review, add=["legal"], remove=["security"], reason=REASON
        )
        assert review.status == "in_review"
        with pytest.raises(Conflict, match="already been triaged"):
            service.triage(session, governance, review)
        tasks = {t.review_function: t for t in service.tasks_of(session, review)}
        assert (tasks["security"].status, tasks["legal"].status) == ("waived", "pending")
        assert tasks["legal"].required_by == f"Added at triage: {REASON}"

        with pytest.raises(PermissionDenied, match="do not review for this function"):
            service.complete_task(
                session, reviewer, review, tasks["legal"].id, finding="no_concerns"
            )
        with pytest.raises(PermissionDenied):
            service.complete_task(session, member, review, privacy.id, finding="no_concerns")
        service.claim(session, reviewer, review, privacy.id)
        with pytest.raises(Invalid) as caught:
            service.complete_task(session, reviewer, review, privacy.id, finding="conditions")
        assert set(caught.value.errors) == {"conditions", "notes"}
        with pytest.raises(Invalid):
            service.complete_task(session, reviewer, review, privacy.id, finding="looks good")
        service.complete_task(
            session,
            reviewer,
            review,
            privacy.id,
            finding="conditions",
            notes="The notes can name people, so identifiers must be removed first.",
            conditions=[
                {"template_key": "deidentify_first"},
                {"text": "Keep summaries on the lab's own drive.", "kind": "ongoing"},
            ],
        )
        assert review.status == "in_review"  # legal has yet to look
        with pytest.raises(Conflict, match="1 review task is not finished"):
            service.decide(
                session,
                governance,
                review,
                outcome="approved",
                rationale="Privacy is content with it.",
            )
        service.complete_task(session, governance, review, tasks["legal"].id, finding="no_concerns")
        assert review.status == "ready"
        with pytest.raises(Conflict, match="already finished"):
            service.complete_task(session, reviewer, review, privacy.id, finding="no_concerns")

        packet = views.packet(session, governance, review)
        assert [c["text"] for c in packet["proposed_conditions"]][-2:] == [
            "Remove identifiers from data about people before the AI sees it.",
            "Keep summaries on the lab's own drive.",
        ]
        assert packet["proposed_conditions"][0]["from"] == "The rules" and packet["can"]["decide"]
        with pytest.raises(Invalid) as caught:
            service.decide(session, governance, review, outcome="approve it", rationale="ok")
        assert set(caught.value.errors) == {"outcome", "rationale"}
        chosen = [
            {k: c[k] for k in ("template_key", "text", "kind") if c.get(k)}
            for c in packet["proposed_conditions"]
        ]
        decision = service.decide(
            session,
            governance,
            review,
            outcome="approved",
            rationale="Low stakes once identifiers are removed. Privacy's conditions are adopted.",
            conditions=chosen,
        )
        assert (decision.outcome, decision.authority, decision.over_objection) == (
            "approved_with_conditions",
            "committee",
            False,
        )
        assert (review.status, use_case.status, use_case.approved_until) == (
            "decided",
            "approved_with_conditions",
            date(2027, 11, 2),
        )
        with pytest.raises(Conflict, match="already been decided"):
            service.decide(
                session,
                governance,
                review,
                outcome="declined",
                rationale="Changed my mind about it.",
            )
        assert not service.in_effect(session, use_case)  # a before-use condition is still open
        before_use = next(
            c for c in service.conditions_of(session, use_case) if c.kind == "before_use"
        )
        with pytest.raises(Invalid):
            service.close_condition(session, member, before_use.id, status="met", note="done")
        with pytest.raises(PermissionDenied, match="Only governance can waive"):
            service.close_condition(
                session, member, before_use.id, status="waived", note="We would rather not do this."
            )
        service.close_condition(
            session,
            member,
            before_use.id,
            status="met",
            note="Names are replaced by initials by script.",
        )
        assert service.in_effect(session, use_case)
        with pytest.raises(Conflict):
            service.close_condition(
                session, governance, before_use.id, status="waived", note="No longer needed at all."
            )
    assert notices(db, people, "reviewer") == ["Privacy review needed: Summarize lab meeting notes"]
    assert notices(db, people, "security") == []  # waived at triage before anyone was asked
    assert notices(db, people, "member") == [
        "Your request was approved, with conditions: Summarize lab meeting notes"
    ]
    assert (
        notices(db, people, "governance")[-1] == "Ready for a decision: Summarize lab meeting notes"
    )


def test_nobody_judges_their_own_request(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    ref = request(db, people, HIGH, by="governance")
    with db.write(governance.actor) as session:
        review = get(session, ref)
        for attempt in (
            lambda: service.triage(session, governance, review),
            lambda: service.claim(
                session, governance, review, service.tasks_of(session, review)[0].id
            ),
            lambda: service.decide(
                session, governance, review, outcome="approved", rationale="I know it is fine."
            ),
        ):
            with pytest.raises(PermissionDenied, match="your own"):
                attempt()
        packet = views.packet(session, governance, review)
        assert (
            not packet["can"]["decide"] and not packet["can"]["triage"] and not packet["internal"]
        )
        assert (
            service.withdraw(session, governance, review, "No longer needed.").outcome
            == "withdrawn"
        )
        assert service.subject_of(session, review).status == "withdrawn"


def test_a_decision_made_over_an_objection_says_so(
    db: Database, people: People, security: Principal
) -> None:
    governance, reviewer = who(db, people, "governance"), who(db, people, "reviewer")
    ref = request(db, people, HIGH)
    with db.write(governance.actor) as session:
        review = get(session, ref)
        service.triage(session, governance, review)
        privacy, sec = service.tasks_of(session, review)
        service.complete_task(
            session,
            reviewer,
            review,
            privacy.id,
            finding="objection",
            notes="Summaries of meetings will include unpublished results.",
        )
        service.complete_task(session, security, review, sec.id, finding="no_concerns")
        decision = service.decide(
            session,
            governance,
            review,
            outcome="approved",
            rationale="The objection is met by keeping summaries inside the lab.",
        )
        assert decision.over_objection and decision.outcome == "approved"
        entries = history.for_record(session, USE_CASE, service.subject_of(session, review))
        assert entries[0]["title"] == "Standing changed" or "Approved, over an objection" in [
            e["title"] for e in entries
        ]
        assert "Approved, over an objection" in [e["title"] for e in entries]


def test_a_question_to_the_requester_stops_the_clock(db: Database, people: People) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with frozen_at(MONDAY):
        ref = request(db, people, MODERATE)
    with frozen_at(MONDAY + timedelta(days=1)), db.write(governance.actor) as session:
        review = get(session, ref)
        service.triage(session, governance, review)
        assert review.status == "ready" and review.due_on == date(
            2026, 11, 9
        )  # nothing to review: straight to decision
        service.comment(
            session, governance, review, "Which drive will the summaries be kept on?", question=True
        )
        assert (review.status, review.resume_status) == ("with_requester", "ready")
        assert service.subject_of(session, review).status == "returned"
        with pytest.raises(Conflict, match="back with the requester"):
            service.decide(
                session, governance, review, outcome="approved", rationale="Never mind, it is fine."
            )
    assert notices(db, people, "member") == [
        "A question about your request: Summarize lab meeting notes"
    ]
    with frozen_at(MONDAY + timedelta(days=4)), db.write(member.actor) as session:
        review = get(session, ref)
        # Whatever the requester asks for, their words are for everyone on the review to see.
        reply = service.comment(
            session, member, review, "The lab's shared drive.", visibility="internal", question=True
        )
        assert (reply.visibility, reply.is_question) == ("requester", False)
        assert (review.status, review.paused_at) == ("ready", None)
        assert (
            review.paused_seconds == 3 * 86400
            and service.subject_of(session, review).status == "in_review"
        )
    with frozen_at(MONDAY + timedelta(days=5)), db.write(governance.actor) as session:
        review = get(session, ref)
        service.decide(
            session,
            governance,
            review,
            outcome="approved",
            rationale="Kept inside the lab, with checks.",
        )
        packet = views.packet(session, governance, review)
    assert packet["time"] == {"with_reviewers_days": 2.0, "with_requester_days": 3.0}
    assert (
        notices(db, people, "governance")[-1]
        == "The requester replied about Summarize lab meeting notes"
    )


def test_returning_a_request_lets_the_requester_change_their_answers(
    db: Database, people: People
) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    ref = request(db, people, MODERATE)
    with db.write(governance.actor) as session:
        review = get(session, ref)
        service.triage(session, governance, review)
        returned = service.decide(
            session,
            governance,
            review,
            outcome="returned",
            rationale="Say who is affected, please.",
        )
        assert returned.outcome == "returned" and review.status == "with_requester"
        use_case_ref = service.subject_of(session, review).ref
    with db.write(member.actor) as session:
        use_case = find(session, USE_CASE, use_case_ref)
        assert intake.view(session, member, use_case)["can_edit"]
        intake.save(
            session,
            member,
            use_case,
            {
                **MODERATE,
                "unit": people.units["HALE"],
                "affected_groups": ["staff"],
                "impact": "serious",
            },
        )
        assessment = intake.submit(session, member, use_case)
        review = get(session, ref)
        assert assessment.final_tier == 3 and use_case.tier == 3 and use_case.status == "in_review"
        assert (
            review.status == "ready" and service.open_review(session, use_case) is review
        )  # the same review goes on
        last = views.packet(session, member, review)["comments"][-1]
        assert last["body"] == "Updated the answers to the request. The tier is now High."


def test_what_reviewers_say_among_themselves_stays_among_them(
    db: Database, people: People, security: Principal
) -> None:
    member, governance, reviewer, auditor = (
        who(db, people, r) for r in ("member", "governance", "reviewer", "auditor")
    )
    ref = request(db, people, HIGH)
    with db.write(governance.actor) as session:
        review = get(session, ref)
        service.triage(session, governance, review)
        privacy, _ = service.tasks_of(session, review)
        service.comment(
            session,
            reviewer,
            review,
            "I doubt the lab manager checks every one.",
            visibility="internal",
        )
        service.comment(
            session,
            reviewer,
            review,
            "Thank you for the clear description.",
            visibility="requester",
        )
        service.complete_task(
            session,
            reviewer,
            review,
            privacy.id,
            finding="objection",
            notes="Too much rides on one person.",
        )

        theirs = views.packet(session, member, review)
        assert (
            not theirs["internal"]
            and theirs["routing"] is None
            and theirs["proposed_conditions"] == []
        )
        assert [c["body"] for c in theirs["comments"]] == ["Thank you for the clear description."]
        assert all(
            set(task) == {"id", "function", "label", "status", "due_on", "overdue", "completed_at"}
            for task in theirs["tasks"]
        )
        assert theirs["can"] == {
            "triage": False,
            "decide": False,
            "comment_internal": False,
            "ask": False,
            "reply": True,
            "withdraw": True,
            "assign": False,
        }
        inside = views.packet(session, reviewer, review)
        assert (
            inside["internal"]
            and len(inside["comments"]) == 2
            and inside["tasks"][0]["finding"] == "objection"
        )
        assert inside["subject"]["purpose"]  # a reviewer reads the whole request, whatever its unit
        assert views.packet(session, security, review)["tasks"][1]["can_complete"]
        seen = views.packet(session, auditor, review)
        assert seen["internal"] and not any(seen["can"][k] for k in ("triage", "decide", "ask"))
        with pytest.raises(PermissionDenied):
            service.comment(
                session, who(db, people, "steward"), review, "May I add something here?"
            )
        with pytest.raises(PermissionDenied, match="not part of this review"):
            service.comment(session, auditor, review, "An auditor reads, and says nothing.")

        use_case = service.subject_of(session, review)
        mine = [e["title"] for e in history.for_record(session, USE_CASE, use_case, internal=False)]
        all_ = [e["title"] for e in history.for_record(session, USE_CASE, use_case, internal=True)]
        assert "Privacy review completed" in mine and "Privacy review: objection" in all_
        assert "Note among reviewers" in all_ and "Note among reviewers" not in mine
        assert (
            "Message between the requester and reviewers" in mine and f"Review {ref} opened" in mine
        )
    # A reviewer with no part in this review cannot open it.
    with db.read() as session:
        outsider = Principal(
            account_id=9999, name="Elsewhere", grants=(Grant("reviewer", review_function="legal"),)
        )
        with pytest.raises(NotFound):
            service.find(session, outsider, ref)


def test_the_queue_and_each_persons_own_list(
    db: Database, people: People, security: Principal
) -> None:
    member, governance, reviewer = (
        who(db, people, role) for role in ("member", "governance", "reviewer")
    )
    with frozen_at(MONDAY):
        high, moderate = (
            request(db, people, HIGH),
            request(db, people, {**MODERATE, "name": "Screen abstracts"}),
        )
        request(db, people, SIMPLE)  # approved by rule: in nobody's queue
        with db.write(member.actor) as session:
            intake.start(session, member, {"name": "Half-written", "unit": people.units["HALE"]})
        with db.read() as session:
            assert [c["ref"] for c in views.queue(session, governance)] == [
                moderate,
                high,
            ]  # soonest due first
            assert len(views.queue(session, governance, scope="all")) == 3
            assert views.queue(session, reviewer) == [] or all(
                not c["my_tasks"] for c in views.queue(session, reviewer)
            )
            assert [w["title"] for w in views.my_work(session, governance)] == [
                "Triage: Screen abstracts",
                "Triage: Summarize lab meeting notes",
            ]
            assert [w["kind"] for w in views.my_work(session, member)] == ["draft"]
        with db.write(governance.actor) as session:
            service.triage(session, governance, get(session, high))
            service.triage(session, governance, get(session, moderate))
            service.comment(
                session,
                governance,
                get(session, moderate),
                "Who else will see the output?",
                question=True,
            )
        with db.read() as session:
            [card] = views.queue(session, reviewer)
            assert (card["ref"], card["my_tasks"], card["tasks_done"], card["tasks_total"]) == (
                high,
                ["Privacy"],
                0,
                2,
            )
            assert [w["title"] for w in views.my_work(session, reviewer)] == [
                "Privacy review: Summarize lab meeting notes"
            ]
            assert [w["title"] for w in views.my_work(session, security)] == [
                "Information security review: Summarize lab meeting notes"
            ]
            assert {w["kind"] for w in views.my_work(session, member)} == {"question", "draft"}
            assert [c["ref"] for c in views.queue(session, member)] == [
                moderate,
                high,
            ]  # their own requests
    with frozen_at(MONDAY + timedelta(days=40)), db.read() as session:
        assert all(w["overdue"] for w in views.my_work(session, reviewer))
        assert views.queue(session, governance)[0]["overdue"]


def test_review_through_the_api(as_role: Clients, people: People, db: Database) -> None:
    member, governance, reviewer, auditor = (
        as_role("member"),
        as_role("governance"),
        as_role("reviewer"),
        as_role("auditor"),
    )
    started = member.post(
        "/api/v1/intake",
        json={
            "answers": {
                **MODERATE,
                "unit": people.units["HALE"],
                "data_categories": ["health"],
                "deidentified": True,
                "minimum_necessary": True,
            }
        },
    )
    use_case = started.json()["data"]["ref"]
    assert (
        member.post(f"/api/v1/use-cases/{use_case}/submit").json()["data"]["record"]["status"]
        == "in_review"
    )
    [card] = governance.get("/api/v1/reviews").json()["data"]
    ref = card["ref"]
    url = f"/api/v1/reviews/{ref}"
    assert governance.get("/api/v1/me/work").json()["data"][0]["kind"] == "triage"
    unread = governance.get("/api/v1/notifications").json()["data"]
    assert unread["unread"] == 1 and unread["items"][0]["href"] == f"/reviews?open={ref}"
    assert governance.post("/api/v1/notifications/read", json={}).status_code == 200
    assert governance.get("/api/v1/notifications").json()["data"]["unread"] == 0

    assert member.post(f"{url}/triage", json={}).status_code == 403
    assert (
        auditor.post(
            f"{url}/decision", json={"outcome": "approved", "rationale": "An auditor's view."}
        ).status_code
        == 403
    )
    triaged = governance.post(f"{url}/triage", json={})
    assert triaged.status_code == 200 and triaged.json()["data"]["status"] == "in_review"
    task = triaged.json()["data"]["tasks"][0]
    assert task["label"] == "Privacy" and task["required_by"] == "Health information"
    assert (
        reviewer.post(f"{url}/tasks/{task['id']}/claim").json()["data"]["tasks"][0]["assignee"]
        == "Reviewer Person"
    )
    assert (
        governance.post(
            f"{url}/tasks/{task['id']}/assign", json={"account_id": people.accounts["member"]}
        ).status_code
        == 422
    )
    assert (
        reviewer.post(
            f"{url}/tasks/{task['id']}/complete", json={"finding": "objection"}
        ).status_code
        == 422
    )
    done = reviewer.post(
        f"{url}/tasks/{task['id']}/complete", json={"finding": "no_concerns", "notes": ""}
    )
    assert done.json()["data"]["status"] == "ready"
    assert (
        reviewer.post(f"{url}/tasks/999/complete", json={"finding": "no_concerns"}).status_code
        == 404
    )

    asked = reviewer.post(f"{url}/comments", json={"body": "Is the data coded?", "question": True})
    assert asked.json()["data"]["status"] == "with_requester"
    mine = member.get(f"/api/v1/use-cases/{use_case}/review").json()["data"]
    assert (
        mine["status"] == "with_requester"
        and mine["comments"][0]["body"] == "Is the data coded?"
        and not mine["internal"]
    )
    assert member.get(url).json()["data"]["tasks"][0].get("finding") is None
    assert (
        member.post(f"{url}/comments", json={"body": "Yes, by study number."}).json()["data"][
            "status"
        ]
        == "ready"
    )

    assert (
        governance.post(
            f"{url}/decision", json={"outcome": "approved", "rationale": "ok"}
        ).status_code
        == 422
    )
    decided = governance.post(
        f"{url}/decision",
        json={
            "outcome": "approved",
            "rationale": "Coded data, checked by a person, inside one unit.",
            "conditions": [
                {"template_key": "check_outputs"},
                {"text": "Report use quarterly.", "kind": "by_date", "due_on": "2027-03-01"},
            ],
        },
    )
    assert (
        decided.status_code == 200
        and decided.json()["data"]["decisions"][0]["outcome"] == "approved_with_conditions"
    )
    assert (
        governance.post(
            f"{url}/decision", json={"outcome": "declined", "rationale": "On reflection, no."}
        ).status_code
        == 409
    )
    record = member.get(f"/api/v1/use-cases/{use_case}").json()["data"]
    assert record["status"] == "approved_with_conditions" and record["approved_until"]
    summary = member.get(f"/api/v1/use-cases/{use_case}/review").json()["data"]
    assert (
        summary["in_effect"]
        and len(summary["all_conditions"]) == 2
        and summary["can_close_conditions"]
    )
    dated = next(c for c in summary["all_conditions"] if c["kind"] == "by_date")
    assert (
        member.post(
            f"/api/v1/conditions/{dated['id']}/close",
            json={"status": "met", "note": "The first report was sent."},
        ).status_code
        == 200
    )
    assert (
        member.post(
            "/api/v1/conditions/9999/close",
            json={"status": "met", "note": "No such condition here."},
        ).status_code
        == 404
    )
    assert member.get("/api/v1/me/work").json()["data"] == []
    titles = [
        e["title"] for e in member.get(f"/api/v1/use-cases/{use_case}/history").json()["data"]
    ]
    assert (
        "Approved with conditions" in titles
        and "Condition met" in titles
        and "Privacy review completed" in titles
    )
    with db.read() as session:
        assert session.scalars(select(Condition.status).order_by(Condition.id)).all() == [
            "open",
            "met",
        ]
