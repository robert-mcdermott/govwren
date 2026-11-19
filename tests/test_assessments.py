"""Assessments: an impact assessment that the rules can require before approval, and a
due-diligence questionnaire kept with a vendor."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from govwren.assurance import assessments
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.inventory import history, records
from govwren.inventory.registry import USE_CASE, VENDOR, find
from govwren.review import service, views
from tests.people import ME, People
from tests.test_intake import CASES
from tests.test_review import HIGH, MONDAY, get, notices, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
CRITICAL: dict[str, Any] = dict(CASES)["critical"]


def replies(key: str) -> dict[str, str]:
    return {
        q["key"]: q["options"][0]["key"] if q["type"] == "choice" else "Described in full."
        for q in assessments.questions(assessments.template(key))
    }


def test_the_templates_come_from_a_pack() -> None:
    found = assessments.templates()
    assert set(found) == {"impact_assessment", "vendor_due_diligence"}
    assert found["impact_assessment"]["subject"] == "use_case"
    assert len(assessments.questions(found["vendor_due_diligence"])) >= 12


def test_an_impact_assessment_is_required_by_rule_before_approval(
    db: Database, people: People
) -> None:
    with frozen_at(MONDAY):
        high, critical = (
            request(db, people, HIGH),
            request(db, people, {**CRITICAL, "name": "Triage"}),
        )
    governance, member, reviewer = (
        who(db, people, r) for r in ("governance", "member", "reviewer")
    )
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        assert views.packet(session, governance, get(session, high))["impact_assessment"] is None
        review = get(session, critical)
        use_case = service.subject_of(session, review)
        assert views.packet(session, governance, review)["impact_assessment"] == {
            "required": True,
            "status": "missing",
            "href": f"/assessments/{use_case.ref}/impact_assessment",
        }
        waived = [task.review_function for task in service.tasks_of(session, review)]
        service.triage(session, governance, review, remove=waived, reason="Seen by the committee.")
        with pytest.raises(Conflict) as blocked:
            service.decide(
                session, governance, review, outcome="approved", rationale="Approved by committee."
            )
        assert "impact assessment" in str(blocked.value)
    with frozen_at(MONDAY), db.write(member.actor) as session:
        use_case = service.subject_of(session, get(session, critical))
        with pytest.raises(PermissionDenied):
            assessments.save(session, reviewer, USE_CASE, use_case, "impact_assessment", {})
        with pytest.raises(Invalid):  # that template is for vendors
            assessments.save(session, member, USE_CASE, use_case, "vendor_due_diligence", {})
        draft = assessments.save(
            session, member, USE_CASE, use_case, "impact_assessment", {"who": "Patients."}
        )
        assert (draft.status, draft.review_id) == ("draft", get(session, critical).id)
        with pytest.raises(Invalid) as gaps:
            assessments.save(
                session, member, USE_CASE, use_case, "impact_assessment", {"who": "x"}, submit=True
            )
        assert (
            "worst_case" in gaps.value.errors and "vulnerable_how" not in gaps.value.errors
        )  # optional
        assessments.save(
            session,
            member,
            USE_CASE,
            use_case,
            "impact_assessment",
            replies("impact_assessment"),
            submit=True,
        )
    assert any(
        t.startswith("Impact assessment to review") for t in notices(db, people, "governance")
    )
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        review = get(session, critical)
        use_case = service.subject_of(session, review)
        seen = assessments.view(session, reviewer, USE_CASE, use_case, "impact_assessment")
        assert seen["status"] == "submitted" and not seen["can"]["answer"]  # reviewers read it
        found = assessments.latest(session, USE_CASE, use_case, "impact_assessment")
        assert found is not None
        with pytest.raises(PermissionDenied):
            assessments.mark_reviewed(
                session, who(db, people, "member"), found, "Looks fine to me."
            )
        assessments.mark_reviewed(
            session, governance, found, "The oversight described answers the main risk."
        )
        with pytest.raises(Conflict) as still:  # the assessment is in; the acceptance is not
            service.decide(
                session, governance, review, outcome="approved", rationale="Approved by committee."
            )
        assert "accept the risk" in str(still.value)
        titles = [e["title"] for e in history.for_record(session, USE_CASE, use_case)]
        assert {"Impact assessment submitted", "Impact assessment reviewed"} <= set(titles)


def test_vendor_due_diligence_is_answered_reviewed_and_completes(
    db: Database, people: People
) -> None:
    governance, admin = who(db, people, "governance"), who(db, people, "admin")
    with db.write(ME.actor) as session:
        vendor = records.create(session, governance, VENDOR, {"name": "Lumen Labs"})
        ref = vendor.ref
        assert vendor.due_diligence_status == "not_started"
    with db.write(governance.actor) as session:
        vendor = find(session, VENDOR, ref)
        made = assessments.save(
            session,
            governance,
            VENDOR,
            vendor,
            "vendor_due_diligence",
            replies("vendor_due_diligence"),
            submit=True,
        )
        assert vendor.due_diligence_status == "in_progress"  # type: ignore[attr-defined]
        with pytest.raises(PermissionDenied):  # nobody reviews what they submitted
            assessments.mark_reviewed(session, governance, made, "I have read my own answers.")
    with db.write(ME.actor) as session:
        vendor = find(session, VENDOR, ref)
        made = assessments.latest(session, VENDOR, vendor, "vendor_due_diligence")
        assert made is not None
        second = ME if ME.governs else admin
        assert second.governs
        assessments.mark_reviewed(
            session, second, made, "Satisfactory. Report attached as evidence."
        )
        assert vendor.due_diligence_status == "complete"  # type: ignore[attr-defined]
        again = assessments.save(
            session, second, VENDOR, vendor, "vendor_due_diligence", {"retention": "30 days"}
        )
        assert again.id != made.id and again.status == "draft"  # a reviewed one is not rewritten


def test_assessments_over_the_api(db: Database, people: People, as_role: Clients) -> None:
    with frozen_at(MONDAY):
        critical = request(db, people, CRITICAL)
    with db.read() as session:
        use_ref = service.subject_of(session, get(session, critical)).ref
    member, governance = as_role("member"), as_role("governance")
    at = f"/api/v1/assessments/{use_ref}/impact_assessment"
    shown = member.get(at).json()["data"]
    assert (
        shown["status"] == "missing"
        and shown["can"]["answer"]
        and len(shown["template"]["sections"]) == 3
    )
    assert (
        member.put(at, json={"answers": {"who": "Patients."}}).json()["data"]["status"] == "draft"
    )
    assert member.put(at, json={"answers": {"who": "Patients."}, "submit": True}).status_code == 422
    done = member.put(at, json={"answers": replies("impact_assessment"), "submit": True})
    assert done.json()["data"]["status"] == "submitted"
    assert member.post(f"{at}/review", json={"note": "Fine."}).status_code == 403
    reviewed = governance.post(f"{at}/review", json={"note": "Read and accepted."})
    assert reviewed.json()["data"]["status"] == "reviewed"
    assert member.get(f"/api/v1/assessments/{use_ref}/vendor_due_diligence").status_code == 404
    packet = governance.get(f"/api/v1/reviews/{critical}").json()["data"]
    assert packet["impact_assessment"]["status"] == "reviewed"
