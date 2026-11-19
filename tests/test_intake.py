"""Intake and tiering: the form, the scoring model, a request's path, and the browser's twin."""

from __future__ import annotations

import copy
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from govwren.access.principal import Principal
from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import (
    Event,
    FormResponse,
    FormVersion,
    IntakeDraft,
    ScoringModel,
    TierAssessment,
)
from govwren.intake import forms, scoring, service
from govwren.inventory import history, records
from govwren.inventory.registry import SYSTEM, USE_CASE, find
from govwren.people import accounts
from govwren.program import packs
from govwren.review import routing
from tests.people import ME, People

Clients = Callable[[str | None], TestClient]
PARITY = Path(__file__).resolve().parent / "parity" / "scoring.json"
PACK = packs.default_pack()
FORM, MODEL = PACK["forms"][0], PACK["scoring_model"]

# A request with little that can go wrong.
SIMPLE: dict[str, Any] = {
    "name": "Summarize lab meeting notes",
    "unit": 0,
    "purpose": "Turn notes into a summary.",
    "stage": "in_use",
    "domain": "research",
    "affected_groups": ["team"],
    "impact": "none",
    "decision_role": "exploratory",
    "autonomy": "output_only",
    "human_oversight": "The lab manager reads each summary.",
    "data_class": "internal",
    "exposure": "vendor_agreement",
    "reach": "team",
    "trains_on_inputs": "no",
}
CASES: list[tuple[str, dict[str, Any]]] = [
    ("nothing answered yet", {}),
    ("only the basics", {"name": "x", "unit": 1, "purpose": "y"}),
    ("an everyday use", SIMPLE),
    (
        "moderate: protected data across a unit",
        {**SIMPLE, "data_class": "protected", "reach": "one_unit", "decision_role": "informs"},
    ),
    (
        "high by total",
        {
            **SIMPLE,
            "data_class": "restricted",
            "reach": "many_units",
            "decision_role": "recommends",
            "impact": "significant",
        },
    ),
    (
        "critical",
        {
            **SIMPLE,
            "data_class": "restricted",
            "exposure": "vendor_no_agreement",
            "reach": "org_wide",
            "decision_role": "decides",
            "impact": "serious",
            "autonomy": "acts_irreversibly",
            "affected_groups": ["patients"],
            "actions": "a",
            "stop_mechanism": "b",
        },
    ),
    (
        "a floor: serious impact, otherwise small",
        {**SIMPLE, "impact": "serious", "exposure": "own_equipment"},
    ),
    (
        "a floor: irreversible actions",
        {
            **SIMPLE,
            "autonomy": "acts_irreversibly",
            "exposure": "own_equipment",
            "actions": "a",
            "stop_mechanism": "b",
        },
    ),
    (
        "a floor: decides about people",
        {
            **SIMPLE,
            "decision_role": "decides",
            "affected_groups": ["staff"],
            "exposure": "own_equipment",
        },
    ),
    (
        "a stop: restricted data, supplier trains",
        {**SIMPLE, "data_class": "restricted", "trains_on_inputs": "yes"},
    ),
    (
        "a stop: peer review",
        {
            **SIMPLE,
            "outputs_used_for": ["peer_review"],
            "disclosure": True,
            "verification": "by hand",
        },
    ),
    (
        "a stop: automated decisions about people",
        {**SIMPLE, "decision_role": "decides", "outputs_used_for": ["decisions_about_people"]},
    ),
    (
        "a hidden answer does not count",
        {
            **SIMPLE,
            "exposure": "own_equipment",
            "trains_on_inputs": "yes",
            "data_class": "restricted",
        },
    ),
    (
        "data about people opens a section",
        {
            **SIMPLE,
            "data_categories": ["health", "human_subjects"],
            "deidentified": True,
            "ethics_protocol": "P-0000",
        },
    ),
    (
        "a question inside a section that is not showing",
        {**SIMPLE, "ethics_protocol": "P-0000", "agreement_reference": "A-1"},
    ),
    ("the public is affected", {**SIMPLE, "affected_groups": ["team", "public"]}),
]


def expected(answers: dict[str, Any]) -> dict[str, Any]:
    keys, kept = forms.showing(FORM, answers)
    result = scoring.assess(MODEL, kept)
    return {
        "showing": keys,
        "kept": kept,
        "assessment": result,
        "routing": routing.route(PACK["review"], result["final_tier"], kept, result["stops"]),
    }


def test_the_parity_file_is_current() -> None:
    """The browser's twin is tested against this file (tests/js/scoring.test.mjs), so it must
    say what the server would. Regenerate with UPDATE_PARITY=1."""
    fresh = [
        {"name": name, "answers": answers, "expect": expected(answers)} for name, answers in CASES
    ]
    text = json.dumps(fresh, indent=1) + "\n"
    if os.environ.get("UPDATE_PARITY") == "1":
        PARITY.write_text(text, encoding="utf-8")
    assert PARITY.is_file() and PARITY.read_text(encoding="utf-8") == text, (
        "run UPDATE_PARITY=1 uv run pytest tests/test_intake.py"
    )


def tier_of(answers: dict[str, Any]) -> dict[str, Any]:
    return scoring.assess(MODEL, forms.showing(FORM, answers)[1])


def test_the_default_program_is_valid_and_scores_as_the_spec_says() -> None:
    assert packs.problems(PACK) == []
    simple = tier_of(SIMPLE)
    assert (simple["total"], simple["final_tier"]) == (3, 1)
    assert simple["factors"]["sensitivity"] == {
        "level": 1,
        "reason": "The most sensitive data involved is Internal.",
    }
    assert simple["factors"]["impact"] == {"level": 0, "reason": None}
    by_name = {name: tier_of(answers) for name, answers in CASES}
    assert by_name["moderate: protected data across a unit"]["final_tier"] == 2
    assert by_name["high by total"]["final_tier"] == 3
    assert (by_name["critical"]["total"], by_name["critical"]["final_tier"]) == (18, 4)


def test_each_factor_takes_its_highest_level_never_an_average() -> None:
    result = tier_of({**SIMPLE, "exposure": "vendor_agreement", "trains_on_inputs": "yes"})
    assert result["factors"]["exposure"] == {
        "level": 3,
        "reason": "The supplier may use what is entered to train its models.",
    }
    result = tier_of({**SIMPLE, "reach": "one_unit", "affected_groups": ["staff", "public"]})
    assert result["factors"]["reach"]["level"] == 3


def test_floors_raise_a_tier_and_say_why() -> None:
    result = tier_of({**SIMPLE, "impact": "serious", "exposure": "own_equipment"})
    assert (result["total"], result["computed_tier"], result["final_tier"]) == (4, 1, 3)
    assert [floor["tier"] for floor in result["floors"]] == [3]
    assert "at least High" in result["floors"][0]["reason"]
    # A floor that does not raise the tier is not listed.
    assert tier_of(dict(CASES[5][1]))["floors"] == []


def test_stops_mark_a_prohibited_use() -> None:
    assert [s["key"] for s in tier_of(dict(CASES[9][1]))["stops"]] == ["restricted_data_trained_on"]
    assert [s["key"] for s in tier_of(dict(CASES[10][1]))["stops"]] == ["peer_review"]
    assert tier_of(SIMPLE)["stops"] == []


def test_answers_to_questions_that_are_not_showing_do_not_count() -> None:
    answers = {
        **SIMPLE,
        "exposure": "own_equipment",
        "trains_on_inputs": "yes",
        "data_class": "restricted",
    }
    keys, kept = forms.showing(FORM, answers)
    assert "trains_on_inputs" not in keys and "trains_on_inputs" not in kept
    assert (
        tier_of(answers)["stops"] == []
    )  # the supplier section is hidden, so its answer is ignored
    keys, _ = forms.showing(FORM, {**SIMPLE, "data_categories": ["health"]})
    assert "deidentified" in keys and "ethics_protocol" not in keys
    keys, _ = forms.showing(FORM, {**SIMPLE, "data_categories": ["human_subjects"]})
    assert "ethics_protocol" in keys


@pytest.mark.parametrize(
    ("change", "complaint"),
    [
        (
            lambda p: p["forms"][0]["sections"][0]["questions"].append(
                {"key": "name", "type": "text", "label": "Again"}
            ),
            "used twice",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][0].update(type="essay"),
            "type must be one of",
        ),
        (
            lambda p: p["forms"][0]["sections"][1].update(
                show_when={"field": "answers.exposure", "op": "eq", "value": "x"}
            ),
            "not an earlier question",
        ),
        (
            lambda p: p["forms"][0]["sections"][1].update(
                show_when={"field": "record.status", "op": "eq", "value": "x"}
            ),
            "may look only at answers",
        ),
        (
            lambda p: p["forms"][0]["sections"][1].update(
                show_when={"field": "answers.name", "op": "regex", "value": "."}
            ),
            "`op` must be one of",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][5].update(vocabulary="moods"),
            "no vocabulary called",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][5].pop("vocabulary"),
            "either options or a vocabulary",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][0].update(maps_to="status"),
            "cannot fill the field",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][0].pop("maps_to"),
            "needs a required question that fills name",
        ),
        (
            lambda p: p["forms"][0]["sections"][0]["questions"][6].update(vocabulary="stages"),
            "must use the domains vocabulary",
        ),
        (
            lambda p: p["scoring_model"]["contributions"][0].update(factor="luck"),
            "names a factor that is not defined",
        ),
        (
            lambda p: p["scoring_model"]["contributions"][0].update(level=7),
            "level must be between 1 and 3",
        ),
        (
            lambda p: p["scoring_model"]["contributions"][0].update(
                when={"field": "answers.mood", "op": "eq", "value": "x"}
            ),
            "not an earlier question",
        ),
        (
            lambda p: p["scoring_model"]["tiers"][1].update(min=0),
            "must start above the tier before it",
        ),
        (lambda p: p["scoring_model"]["tiers"][0].update(min=2), "the first tier starts at 0"),
        (
            lambda p: p["scoring_model"]["floors"][0].update(tier=9),
            "names a tier that is not defined",
        ),
        (
            lambda p: p["scoring_model"]["stops"].append(dict(p["scoring_model"]["stops"][0])),
            "used twice",
        ),
        (lambda p: p.update(vocabularies={"moods": []}), "no vocabulary called"),
        (lambda p: p["pack"].update(kind="framework"), "not a program pack"),
    ],
)
def test_a_pack_with_a_mistake_is_refused_whole(
    change: Callable[[dict], Any], complaint: str
) -> None:
    pack = copy.deepcopy(PACK)
    change(pack)
    found = packs.problems(pack)
    assert any(complaint in problem for problem in found), found


def who(db: Database, people: People, role: str) -> Principal:
    with db.read() as session:
        return accounts.principal_for(session, accounts.get(session, people.accounts[role]))


def count(db: Database, model: type) -> int:
    with db.read() as session:
        return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_loading_a_pack_versions_what_changed_and_leaves_the_rest(
    db: Database, program: None
) -> None:
    assert (count(db, FormVersion), count(db, ScoringModel)) == (1, 1)
    changed = copy.deepcopy(PACK)
    changed["scoring_model"]["tiers"][1]["min"] = 6
    with db.write(ME.actor) as session:
        assert packs.apply(session, ME, PACK) == {
            "forms": {"use_case_intake": "unchanged"},
            "scoring_model": "unchanged",
            "review": "unchanged",
            "vocabularies": [],
        }
        report = packs.apply(session, ME, changed)
        assert report["scoring_model"] == "version 2" and report["forms"] == {
            "use_case_intake": "unchanged"
        }
        assert packs.published_scoring(session).version == 2
        exported = packs.export(session)
        assert (
            exported["forms"] == PACK["forms"] and exported["scoring_model"]["tiers"][1]["min"] == 6
        )
        assert packs.problems(exported) == []  # what is exported can be loaded again
        broken = copy.deepcopy(PACK)
        broken["forms"][0]["sections"] = []
        with pytest.raises(Invalid, match="not loaded"):
            packs.apply(session, ME, broken)
    assert (count(db, FormVersion), count(db, ScoringModel)) == (1, 2)
    member = Principal(account_id=None, name="x")
    with db.write(ME.actor) as session, pytest.raises(PermissionDenied):
        packs.apply(session, member, PACK)


def test_a_request_from_first_answer_to_tier(db: Database, people: People, program: None) -> None:
    member = who(db, people, "member")
    hale = people.units["HALE"]
    with db.write(member.actor) as session:
        with pytest.raises(Invalid) as caught:
            service.start(session, member, {"purpose": "No name or unit yet"})
        assert set(caught.value.errors) == {"name", "unit"}
        with pytest.raises(Invalid) as caught:
            service.start(session, member, {"name": "Elsewhere", "unit": people.units["CANCER"]})
        assert "your own units" in caught.value.errors["unit"]
        use_case = service.start(session, member, {"name": "Summarize notes", "unit": hale})
        assert (use_case.ref, use_case.status, use_case.tier) == ("UC-0001", "draft", None)
        ref = use_case.ref
    events_before = count(db, Event)
    with db.write(member.actor) as session:
        use_case = find(session, USE_CASE, ref)
        errors = service.save(
            session,
            member,
            use_case,
            {**SIMPLE, "unit": hale, "impact": "catastrophic", "stage": "in_use"},
        )
        assert errors == {"impact": "Choose one of the options."}  # the rest was kept
        seen = service.view(session, member, use_case)
        assert (
            seen["state"] == "draft"
            and seen["can_edit"]
            and seen["answers"]["data_class"] == "internal"
        )
        assert (
            "impact" not in seen["answers"]
            and seen["progress"]["answered"] < seen["progress"]["required"]
        )
        assert use_case.name == "Summarize lab meeting notes"  # the record's name follows the draft
        with pytest.raises(Invalid) as caught:
            service.submit(session, member, use_case)
        assert caught.value.errors == {"impact": "Answer this question."}
    # Saving a draft is not history: only the change of name is.
    assert count(db, Event) == events_before + 1 and count(db, IntakeDraft) == 1

    with db.write(member.actor) as session:
        use_case = find(session, USE_CASE, ref)
        assistant = records.create(
            session, ME, SYSTEM, {"name": "Lumen Assistant", "kind": "vendor_product"}
        )
        service.save(
            session,
            member,
            use_case,
            {**SIMPLE, "unit": hale, "systems": [assistant.ref], "other_tool": "ignored"},
        )
        assessment = service.submit(session, member, use_case)
        assert (assessment.total, assessment.computed_tier, assessment.final_tier) == (3, 1, 1)
        assert (use_case.status, use_case.tier, use_case.tier_source) == (
            "approved_with_conditions",
            1,
            "computed",
        )
        assert (
            use_case.purpose,
            use_case.data_class,
            use_case.stage,
            use_case.affected_groups,
        ) == (
            "Turn notes into a summary.",
            "internal",
            "in_use",
            ["team"],
        )
        assert [s.ref for s in records.systems_of(session, [use_case.id])[use_case.id]] == [
            assistant.ref
        ]
        with pytest.raises(Conflict, match="has been submitted"):
            service.save(session, member, use_case, {"name": "Changed my mind"})
        with pytest.raises(Conflict):
            service.submit(session, member, use_case)
    assert (count(db, IntakeDraft), count(db, FormResponse), count(db, TierAssessment)) == (0, 1, 1)

    with db.read() as session:
        use_case = find(session, USE_CASE, ref)
        seen = service.view(session, member, use_case)
        assert seen["state"] == "submitted" and not seen["can_edit"] and seen["submitted_at"]
        why = seen["assessment"]
        assert (why["tier_label"], why["total"], why["max_total"]) == ("Minimal", 3, 18)
        assert [f["label"] for f in why["factors"]][:2] == ["Impact on people", "Decision role"]
        assert (
            why["factors"][0]["reason"] == "No effect on anyone outside the team"
        )  # level 0 is described too
        assert why["factors"][3] == {
            "key": "sensitivity",
            "label": "Data sensitivity",
            "level": 1,
            "max": 3,
            "reason": "The most sensitive data involved is Internal.",
        }
        titles = [entry["title"] for entry in history.for_record(session, USE_CASE, use_case)]
        context = session.scalars(
            select(Event.context).where(Event.subject_type == "tier_assessment")
        ).one()
    assert context == {"op": "use_case.submit"}
    assert titles[-1] == "Added this use case" and "Edited" in titles
    assert "Submitted the request" in titles and "Approved with conditions by rule" in titles
    assert "Tier worked out as Minimal" in titles
    assert titles.count("Added this use case") == 1


def test_an_old_response_keeps_the_form_it_was_answered_on(
    db: Database, people: People, program: None
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        use_case = service.start(session, member, {**SIMPLE, "unit": people.units["HALE"]})
        service.submit(session, member, use_case)
        ref = use_case.ref
    newer = copy.deepcopy(PACK)
    newer["forms"][0]["sections"][0]["questions"][0]["label"] = "What is this request for?"
    newer["scoring_model"]["tiers"][1]["min"] = 3
    with db.write(ME.actor) as session:
        packs.apply(session, ME, newer)
        seen = service.view(session, member, find(session, USE_CASE, ref))
        assert seen["form"]["version"] == 1
        assert (
            seen["form"]["schema"]["sections"][0]["questions"][0]["label"]
            == "What will you use AI for?"
        )
        assert (
            seen["assessment"]["scoring_version"] == 1
            and seen["assessment"]["tier_label"] == "Minimal"
        )
        fresh = service.start(
            session, member, {**SIMPLE, "name": "A newer request", "unit": people.units["HALE"]}
        )
        assert service.view(session, member, fresh)["form"]["version"] == 2
        assert (
            service.submit(session, member, fresh).final_tier == 2
        )  # the new bands apply to new requests


def test_a_tier_can_be_changed_with_a_reason_but_not_ones_own(
    db: Database, people: People, program: None
) -> None:
    member, governance, reviewer = (
        who(db, people, role) for role in ("member", "governance", "reviewer")
    )
    with db.write(member.actor) as session:
        use_case = service.start(session, member, {**SIMPLE, "unit": people.units["HALE"]})
        with pytest.raises(Conflict, match="no tier yet"):
            service.override_tier(session, governance, use_case, 2, "It touches more than it says.")
        service.submit(session, member, use_case)
        with pytest.raises(PermissionDenied, match="Only a reviewer or governance"):
            service.override_tier(
                session, who(db, people, "auditor"), use_case, 2, "I think it is higher."
            )
        with pytest.raises(PermissionDenied, match="Only a reviewer or governance"):
            service.override_tier(session, member, use_case, 2, "I would like it reviewed.")
        own = service.start(
            session, governance, {**SIMPLE, "name": "My own", "unit": people.units["HALE"]}
        )
        service.submit(session, governance, own)
        with pytest.raises(PermissionDenied, match="your own request"):
            service.override_tier(session, governance, own, 2, "I would like mine to be lower.")
        with pytest.raises(Invalid) as caught:
            service.override_tier(session, governance, use_case, 1, "why")
        assert set(caught.value.errors) == {"tier", "reason"}
        with pytest.raises(Invalid):
            service.override_tier(
                session, governance, use_case, 7, "There is no seventh tier here."
            )
        raised = service.override_tier(
            session, reviewer, use_case, 3, "The notes include unpublished clinical results."
        )
        assert (raised.computed_tier, raised.final_tier, use_case.tier, use_case.tier_source) == (
            1,
            3,
            3,
            "override",
        )
        why = service.assessment_view(session, raised)
        assert (why["computed_label"], why["tier_label"]) == ("Minimal", "High")
        assert why["override"] == {
            "reason": "The notes include unpublished clinical results.",
            "by": "Reviewer Person",
        }
    assert count(db, TierAssessment) == 3  # two requests, and the first assessment kept, superseded


def test_intake_through_the_api(as_role: Clients, people: People, program: None) -> None:
    member, governance, reviewer = as_role("member"), as_role("governance"), as_role("reviewer")
    hale = people.units["HALE"]
    current = member.get("/api/v1/intake").json()["data"]
    assert current["form"]["version"] == 1 and len(current["scoring"]["definition"]["factors"]) == 6

    assert (
        member.post("/api/v1/intake", json={"answers": {"name": "Only a name"}}).status_code == 422
    )
    started = member.post(
        "/api/v1/intake", json={"answers": {"name": "Summarize notes", "unit": hale}}
    )
    assert started.status_code == 201
    ref = started.json()["data"]["ref"]
    url = f"/api/v1/use-cases/{ref}"
    assert reviewer.get(f"{url}/intake").status_code == 404  # someone else's draft

    saved = member.put(
        f"{url}/intake", json={"answers": {**SIMPLE, "unit": hale, "data_class": "top secret"}}
    )
    assert saved.json()["data"] == {
        "saved": True,
        "errors": {"data_class": "Choose one of the options."},
        "name": "Summarize lab meeting notes",
    }
    refused = member.post(f"{url}/submit")
    assert refused.status_code == 422 and refused.json()["errors"][0]["location"] == ["data_class"]
    assert member.get(f"{url}/tier").json()["data"] is None

    member.put(f"{url}/intake", json={"answers": {**SIMPLE, "unit": hale, "impact": "serious"}})
    submitted = member.post(f"{url}/submit")
    assert submitted.status_code == 200
    body = submitted.json()["data"]
    assert body["record"]["status"] == "in_review" and body["record"]["tier"] == 3
    assert (
        body["assessment"]["computed_label"] == "Moderate"
        and body["assessment"]["floors"][0]["tier"] == 3
    )
    assert member.put(f"{url}/intake", json={"answers": SIMPLE}).status_code == 409

    assert (
        member.post(
            f"{url}/tier", json={"tier": 1, "reason": "It is my own and it is fine."}
        ).status_code
        == 403
    )
    assert (
        reviewer.post(
            f"{url}/tier", json={"tier": 2, "reason": "A person reviews every summary."}
        ).status_code
        == 404
    )
    lowered = governance.post(
        f"{url}/tier", json={"tier": 2, "reason": "A person reviews every summary first."}
    )
    assert (
        lowered.status_code == 200
        and lowered.json()["data"]["override"]["by"] == "Governance Person"
    )
    assert member.get(f"{url}/tier").json()["data"]["tier_label"] == "Moderate"
    assert member.get(url).json()["data"]["tier"] == 2
