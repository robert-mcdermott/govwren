"""Keeping watch: the scheduler, periodic reviews, lapsed approvals, and reminders. Every
scheduled behavior is tested by moving the clock, never by waiting."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import jobs
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict
from govwren.db.engine import Database
from govwren.db.models import Decision, IntakeDraft, Job, JobRun, ReviewTask, UseCase
from govwren.events import chain
from govwren.intake import service as intake
from govwren.inventory import history
from govwren.inventory.registry import USE_CASE
from govwren.oversight import schedule
from govwren.review import service, views
from tests.conftest import Instance
from tests.people import People
from tests.test_intake import SIMPLE
from tests.test_review import HIGH, MONDAY, get, notices, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
ENDS = date(2029, 11, 2)  # a minimal approval made on MONDAY runs for three years


def at(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


def watch(db: Database) -> dict[str, int]:
    with db.write(jobs.SCHEDULER) as session:
        return schedule.run_all(session)


def use_case_of(session, ref: str) -> UseCase:  # type: ignore[no-untyped-def]
    return service.subject_of(session, get(session, ref))


def test_nothing_is_due_while_an_approval_has_long_to_run(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        request(db, people, SIMPLE)
    with frozen_at(at(ENDS - timedelta(days=schedule.LEAD_DAYS + 1))):
        assert watch(db) == {"expired": 0, "lapsed": 0, "periodic_reviews": 0, "reminders": 0}


def test_a_periodic_review_opens_ahead_with_the_earlier_answers(
    db: Database, people: People
) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS - timedelta(days=schedule.LEAD_DAYS))):
        assert watch(db)["periodic_reviews"] == 1
        assert watch(db)["periodic_reviews"] == 0  # and only once
        with db.read() as session:
            use_case = use_case_of(session, first)
            review = service.open_review(session, use_case)
            assert review is not None and review.ref != first
            assert (review.kind, review.status, review.due_on) == (
                "periodic",
                "with_requester",
                ENDS,
            )
            assert use_case.status == "approved_with_conditions"  # the standing holds meanwhile
            draft = session.get(IntakeDraft, use_case.id)
            assert draft is not None and draft.answers["name"] == SIMPLE["name"]
            view = intake.view(session, who(db, people, "member"), use_case)
            assert view["state"] == "draft" and view["can_edit"]
            assert view["confirming"]["review"] == review.ref
            work = views.my_work(session, who(db, people, "member"))
            assert [item["kind"] for item in work][:1] == ["periodic"]
    assert any("Periodic review: confirm" in title for title in notices(db, people, "member"))


def test_confirming_unchanged_answers_renews_the_approval_by_rule(
    db: Database, people: People
) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    confirm_on = at(ENDS - timedelta(days=30))
    with frozen_at(at(ENDS - timedelta(days=schedule.LEAD_DAYS))):
        watch(db)
    with frozen_at(confirm_on):
        member = who(db, people, "member")
        with db.write(member.actor) as session:
            use_case = use_case_of(session, first)
            intake.submit(session, member, use_case)
        with db.read() as session:
            use_case = use_case_of(session, first)
            review = service.latest_review(session, use_case)
            assert review is not None and (review.kind, review.status) == ("periodic", "decided")
            assert use_case.status == "approved_with_conditions"
            assert use_case.approved_until == date(2032, 10, 3) == use_case.next_review_on
            assert service.open_review(session, use_case) is None
            assert session.get(IntakeDraft, use_case.id) is None
            # the standard conditions still stand; the renewal does not set them again
            assert len(service.conditions_of(session, use_case)) == 5
            titles = [entry["title"] for entry in history.for_record(session, USE_CASE, use_case)]
            assert "Submitted the answers again for a review" in titles
            assert f"Periodic review {review.ref} opened" in titles
        assert watch(db) == {"expired": 0, "lapsed": 0, "periodic_reviews": 0, "reminders": 0}


def test_changed_answers_send_a_periodic_review_to_reviewers(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS - timedelta(days=schedule.LEAD_DAYS))):
        watch(db)
        member, governance = who(db, people, "member"), who(db, people, "governance")
        with db.write(member.actor) as session:
            use_case = use_case_of(session, first)
            assert (
                intake.save(session, member, use_case, {**HIGH, "unit": people.units["HALE"]}) == {}
            )
            intake.submit(session, member, use_case)
        with db.read() as session:
            use_case = use_case_of(session, first)
            review = service.open_review(session, use_case)
            assert review is not None and (review.kind, review.status) == ("periodic", "triage")
            assert use_case.status == "approved_with_conditions" and use_case.tier == 3
            functions = {task.review_function for task in service.tasks_of(session, review)}
            assert "privacy" in functions
            ref = review.ref
        assert any("Periodic review to triage" in t for t in notices(db, people, "governance"))
        with db.write(governance.actor) as session:
            review = get(session, ref)
            required = [task.review_function for task in service.tasks_of(session, review)]
            service.triage(
                session, governance, review, remove=required, reason="Nothing new to check here"
            )
            with pytest.raises(Conflict):  # a later review is not the requester's to withdraw
                service.withdraw(session, member, review)
            service.decide(session, governance, review, outcome="approved",
                           rationale="Reviewed again; still acceptable.")  # fmt: skip
        with db.read() as session:
            use_case = use_case_of(session, first)
            assert use_case.status == "approved" and use_case.approved_until > ENDS


def test_an_approval_that_runs_out_lapses_and_a_periodic_review_brings_it_back(
    db: Database, people: People
) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS)):
        assert watch(db)["lapsed"] == 0  # it runs through its last day
    with frozen_at(at(ENDS + timedelta(days=1))):
        done = watch(db)
        assert (done["lapsed"], done["periodic_reviews"]) == (1, 0)
        assert watch(db)["lapsed"] == 0
        member = who(db, people, "member")
        with db.read() as session:
            use_case = use_case_of(session, first)
            assert use_case.status == "lapsed"
            entry = next(e for e in history.for_record(session, USE_CASE, use_case)
                         if e["title"] == "Approval lapsed")  # fmt: skip
            assert "ended on 2029-11-02" in entry["lines"][0]["after"]
            assert entry["actor"] == "Scheduler"
        assert any("Approval lapsed" in title for title in notices(db, people, "member"))
        assert any("Approval lapsed" in title for title in notices(db, people, "steward"))
        with db.write(member.actor) as session:
            intake.submit(session, member, use_case_of(session, first))
        with db.read() as session:
            use_case = use_case_of(session, first)
            assert use_case.status == "approved_with_conditions"
            assert use_case.approved_until == date(2032, 11, 3)
    with db.read() as session:
        assert chain.verify(session.connection()).ok


def test_declining_a_periodic_review_ends_the_approval(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS - timedelta(days=10))):
        watch(db)
        governance = who(db, people, "governance")
        with db.write(governance.actor) as session:
            use_case = use_case_of(session, first)
            review = service.open_review(session, use_case)
            assert review is not None
            service.decide(session, governance, review, outcome="declined",
                           rationale="The tool it relied on has been withdrawn.")  # fmt: skip
        with db.read() as session:
            use_case = use_case_of(session, first)
            assert use_case.status == "declined" and use_case.next_review_on is None
            assert session.get(IntakeDraft, use_case.id) is None
    with frozen_at(at(ENDS + timedelta(days=5))):
        assert watch(db) == {"expired": 0, "lapsed": 0, "periodic_reviews": 0, "reminders": 0}


def test_reminders_go_once_to_the_owner_and_then_to_the_steward(
    db: Database, people: People
) -> None:
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS - timedelta(days=schedule.LEAD_DAYS))):
        assert watch(db)["reminders"] == 0
    with frozen_at(at(ENDS - timedelta(days=schedule.SOON_DAYS))):
        assert watch(db)["reminders"] == 1
        assert watch(db)["reminders"] == 0
    assert any("Approval ends Nov 2" in title for title in notices(db, people, "member"))
    assert not any("Overdue" in title for title in notices(db, people, "steward"))
    with frozen_at(at(ENDS + timedelta(days=1))):
        assert watch(db)["reminders"] == 2  # the owner and the unit's steward
        assert watch(db)["reminders"] == 0
    assert any("Overdue: periodic review" in title for title in notices(db, people, "steward"))
    assert first


def test_late_review_tasks_are_escalated_to_governance(db: Database, people: People) -> None:
    with frozen_at(MONDAY):
        ref = request(db, people, HIGH)
        governance = who(db, people, "governance")
        with db.write(governance.actor) as session:
            review = get(session, ref)
            service.triage(session, governance, review)
            due = session.scalars(
                select(ReviewTask.due_on).where(ReviewTask.status == "pending")
            ).first()
    assert due is not None
    with frozen_at(at(due - timedelta(days=1))):
        assert watch(db)["reminders"] == 1
    assert any(
        "privacy review" in t.lower() and t.startswith("Due")
        for t in notices(db, people, "reviewer")
    )
    with frozen_at(at(due + timedelta(days=1))):
        assert (
            watch(db)["reminders"] == 3
        )  # privacy: its reviewer and governance; security: governance
        assert watch(db)["reminders"] == 0
    assert any(t.startswith("Overdue: Privacy review") for t in notices(db, people, "governance"))


# --- The scheduler ------------------------------------------------------------------------


def test_jobs_run_when_due_and_not_before(instance: Instance, people: People) -> None:
    db, config = instance.db, instance.config
    start = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    with frozen_at(start):
        ran = {result["key"] for result in jobs.run_due(db, config)}
        assert ran == set(jobs.JOBS)
        assert jobs.run_due(db, config) == []  # nothing is due again yet
    with frozen_at(start + timedelta(minutes=2)):
        assert [result["key"] for result in jobs.run_due(db, config)] == ["mail", "webhooks"]
    with frozen_at(start + timedelta(hours=1, minutes=1)):
        ran = {result["key"] for result in jobs.run_due(db, config)}
        assert ran == {
            "mail",
            "webhooks",
            "lapse",
            "periodic-reviews",
            "exceptions",
            "reminders",
        }  # not the daily ones


def test_a_claimed_job_is_not_run_again_until_the_claim_runs_out(
    instance: Instance, people: People
) -> None:
    db, config = instance.db, instance.config
    start = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    with frozen_at(start):
        jobs.ensure(db)
        assert jobs._claim(db, "lapse", force=False)  # another process has it
        assert jobs.run_job(db, config, "lapse") is None
        assert jobs.run_job(db, config, "lapse", force=True) is None
    with frozen_at(start + jobs.LEASE + timedelta(seconds=1)):
        result = jobs.run_job(db, config, "lapse")  # that process died; the job is taken up
        assert result is not None and result["status"] == "ok"


def test_a_failing_job_is_recorded_and_tried_again(
    instance: Instance, people: People, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, config = instance.db, instance.config

    def broken(_db: Database, _config: object) -> dict[str, int]:
        raise RuntimeError("the disk is full")

    spec = jobs.JOBS["tidy"]
    monkeypatch.setitem(
        jobs.JOBS, "tidy", jobs.JobSpec(spec.key, spec.label, spec.describes, spec.every, broken)
    )
    start = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
    with frozen_at(start):
        jobs.ensure(db)
        result = jobs.run_job(db, config, "tidy")
        assert result is not None and result["status"] == "failed"
        with db.read() as session:
            row = session.get(Job, "tidy")
            assert row is not None and row.last_status == "failed" and row.claimed_until is None
            assert "the disk is full" in (row.last_summary or "")
            [run] = session.scalars(select(JobRun)).all()
            assert run.status == "failed"
    monkeypatch.setitem(jobs.JOBS, "tidy", spec)
    with frozen_at(start + timedelta(days=1, seconds=1)):
        result = jobs.run_job(db, config, "tidy")
        assert result is not None and result["status"] == "ok"


def test_the_scheduler_does_the_days_work_end_to_end(instance: Instance, people: People) -> None:
    db, config = instance.db, instance.config
    with frozen_at(MONDAY):
        first = request(db, people, SIMPLE)
    with frozen_at(at(ENDS + timedelta(days=1))):
        results = {result["key"]: result for result in jobs.run_due(db, config)}
        assert results["lapse"]["counts"] == {"lapsed": 1}
        assert results["periodic-reviews"]["counts"] == {"periodic_reviews": 1}
        with db.read() as session:
            assert use_case_of(session, first).status == "lapsed"
            kept = {run.job_key for run in session.scalars(select(JobRun))}
            assert {"lapse", "periodic-reviews"} <= kept and "tidy" not in kept
            decisions = session.scalars(select(Decision)).all()
            assert len(decisions) == 1  # lapsing is not a decision


def test_an_administrator_sees_and_runs_jobs(as_role: Clients, people: People) -> None:
    admin = as_role("admin")
    listed = admin.get("/api/v1/jobs").json()["data"]
    assert [job["key"] for job in listed] == list(jobs.JOBS)
    assert all(job["enabled"] for job in listed)
    done = admin.post("/api/v1/jobs/reminders/run").json()["data"]
    assert (done["status"], done["summary"]) == ("ok", "Nothing to do")
    paused = admin.put("/api/v1/jobs/reminders", json={"enabled": False}).json()["data"]
    assert paused["enabled"] is False and paused["last_status"] == "ok"
    assert admin.post("/api/v1/jobs/nothing/run").status_code == 404
    assert as_role("governance").get("/api/v1/jobs").status_code == 403


def test_a_paused_job_is_skipped_unless_asked_for(instance: Instance, people: People) -> None:
    db, config = instance.db, instance.config
    jobs.set_enabled(db, "reminders", False)
    assert "reminders" not in {result["key"] for result in jobs.run_due(db, config)}
    assert jobs.run_job(db, config, "reminders", force=True) is not None
