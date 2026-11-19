"""Editing the program in the app, seeing what a change would have done, and asking for a
tool to be evaluated."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.core.errors import Conflict, Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import EvaluationRequest, Notification, ScoringModel, TierAssessment
from govwren.intake import service as intake
from govwren.inventory import catalog, records
from govwren.inventory.registry import SYSTEM, find
from govwren.program import editor, packs, vocab
from tests.people import People
from tests.test_intake import SIMPLE
from tests.test_review import HIGH, MODERATE, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def submit(db: Database, people: People, answers: dict[str, Any]) -> str:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        use_case = intake.start(session, member, {**answers, "unit": people.units["HALE"]})
        intake.submit(session, member, use_case)
        return use_case.ref


def test_the_program_is_shown_with_its_versions(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    with db.read() as session:
        seen = editor.state(session, governance)
        assert set(seen["program"]) == {"forms", "scoring_model", "review", "vocabularies"}
        assert (
            seen["versions"]["form"][0]["version"] == 1
            and seen["versions"]["form"][0]["status"] == "published"
        )
        assert "choice" in seen["question_types"] and seen["fields"]["name"] == ["text"]
        assert seen["authorities"][0] == "governance" and seen["responses"] == 0
        with pytest.raises(PermissionDenied):
            editor.state(session, who(db, people, "auditor"))


def test_a_change_is_checked_and_previewed_before_it_is_published(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    refs = [submit(db, people, SIMPLE), submit(db, people, MODERATE), submit(db, people, HIGH)]
    with db.read() as session:
        program = editor.state(session, governance)["program"]
        same = editor.check(session, governance, {})
        assert same["problems"] == [] and same["impact"]["requests"] == 3
        assert same["impact"]["changed"] == 0

        stricter = copy.deepcopy(program["scoring_model"])
        stricter["tiers"][1]["min"] = 2  # Moderate begins much lower
        found = editor.check(session, governance, {"scoring_model": stricter})
        assert found["problems"] == []
        impact = found["impact"]
        assert impact["changed"] == 1 and impact["counts"]["tier_up"] == 1
        assert impact["tier_moves"] == [{"from": "Minimal", "to": "Moderate", "count": 1}]
        assert impact["examples"][0]["ref"] == refs[0]
        assert "no longer approved by rule" in impact["examples"][0]["change"]

        rules = copy.deepcopy(program["review"])
        rules["rules"].append({"key": "everything-legal", "name": "Legal sees everything",
                               "when": {}, "then": {"require": ["legal"]}})  # fmt: skip
        routed = editor.check(session, governance, {"review": rules})["impact"]
        assert routed["changed"] == 3 and routed["counts"]["reviews"] == 3
        assert "adds legal review" in routed["examples"][0]["change"]

        broken = copy.deepcopy(program["scoring_model"])
        broken["contributions"][0]["when"] = {
            "field": "answers.no_such_question",
            "op": "eq",
            "value": 1,
        }
        bad = editor.check(session, governance, {"scoring_model": broken})
        assert bad["impact"] is None and "no_such_question" in bad["problems"][0]
        with pytest.raises(Invalid):
            editor.check(session, governance, {"colours": []})
    with db.write(governance.actor) as session:
        with pytest.raises(Invalid) as caught:
            editor.publish(session, governance, {"scoring_model": broken})
        assert "problem_1" in caught.value.errors
        report = editor.publish(session, governance, {"scoring_model": stricter})
        assert report["scoring_model"] == "version 2" and report["review"] == "unchanged"
        models = session.scalars(select(ScoringModel).order_by(ScoringModel.version))
        assert [m.status for m in models] == ["retired", "published"]
        assert (
            editor.publish(session, governance, {"scoring_model": stricter})["scoring_model"]
            == "unchanged"
        )
        # What was already decided keeps the tier and the version it was decided under.
        old = session.scalars(select(TierAssessment).order_by(TierAssessment.id)).first()
        assert old is not None and old.final_tier == 1
    assert submit(db, people, SIMPLE)  # and the next request is judged by the new model
    with db.read() as session:
        latest = session.scalars(select(TierAssessment).order_by(TierAssessment.id.desc())).first()
        assert latest is not None and latest.final_tier == 2


def test_the_form_can_gain_a_question_and_lose_none_that_others_rely_on(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        program = editor.state(session, governance)["program"]
        form = copy.deepcopy(program["forms"][0])
        form["sections"][0]["questions"].append(
            {"key": "funding", "type": "choice", "label": "Who pays for it?",
             "options": [{"key": "grant", "label": "A grant"},
                         {"key": "unit", "label": "The unit"}]}
        )  # fmt: skip
        assert editor.publish(session, governance, {"forms": [form]})["forms"] == {
            "use_case_intake": "version 2"
        }
        assert packs.published_form(session, "use_case_intake").version == 2
        gone = copy.deepcopy(form)
        gone["sections"][1]["questions"] = [
            q for q in gone["sections"][1]["questions"] if q["key"] != "impact"
        ]
        problems = editor.check(session, governance, {"forms": [gone]})["problems"]
        assert problems and any("impact" in text for text in problems)  # the scoring model reads it


def test_a_vocabulary_value_is_retired_not_removed(db: Database, people: People) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        domains = vocab.get(session, "domains")
        renamed = [dict(item) for item in domains]
        renamed[0]["label"] = "Research and scholarship"
        renamed.append({"key": "facilities", "label": "Facilities"})
        report = editor.publish(session, governance, {"vocabularies": {"domains": renamed}})
        assert report["vocabularies"] == ["domains"]
        assert vocab.labels(session, "domains")["research"] == "Research and scholarship"
        assert "facilities" in vocab.keys(session, "domains")
        for bad, words in (
            (renamed[1:], "cannot be removed"),
            ([*renamed, {"key": "has space", "label": "x"}], "own key"),
            ([*renamed, {"key": "blank", "label": " "}], "needs a label"),
            ([{**item, "retired": True} for item in renamed], "not retired"),
        ):
            found = editor.check(session, governance, {"vocabularies": {"domains": bad}})[
                "problems"
            ]
            assert any(words in text for text in found), words
        retired = [{**item, "retired": item["key"] == "facilities"} for item in renamed]
        editor.publish(session, governance, {"vocabularies": {"domains": retired}})
        assert "facilities" not in vocab.keys(session, "domains")
        assert "facilities" in vocab.keys(session, "domains", active_only=False)


def test_anyone_can_ask_for_a_tool_to_be_evaluated(db: Database, people: People) -> None:
    member, steward, governance = (
        who(db, people, "member"),
        who(db, people, "steward"),
        who(db, people, "governance"),
    )
    with db.write(member.actor) as session:
        with pytest.raises(Invalid) as caught:
            catalog.ask(session, member, {"name": "", "reason": "x"})
        assert set(caught.value.errors) == {"name", "reason"}
        asked = catalog.ask(session, member, {
            "name": "Paperglass Editor", "reason": "For editing our manuscripts.",
            "url": "https://paperglass.example"})  # fmt: skip
        catalog.ask(
            session,
            member,
            {"name": "paperglass editor", "reason": "Asking again changes nothing."},
        )
        assert len(session.scalars(select(EvaluationRequest)).all()) == 1
    with db.write(steward.actor) as session:
        second = catalog.ask(
            session, steward, {"name": "Paperglass editor", "reason": "Several labs want this."}
        )
        assert second["ref"] == asked["ref"]  # one tool, two voices
    with db.read() as session:
        mine = catalog.asked(session, member)
        assert [len(entry["requests"]) for entry in mine] == [1]
        everyone = catalog.asked(session, governance)
        assert everyone[0]["name"] == "Paperglass Editor" and len(everyone[0]["requests"]) == 2
        told = session.scalars(select(Notification).where(Notification.kind == "evaluation")).all()
        assert {n.account_id for n in told} == {people.accounts["governance"]} and len(told) == 2
    with db.write(governance.actor) as session:
        system = find(session, SYSTEM, asked["ref"])
        records.update(
            session,
            governance,
            SYSTEM,
            system,
            {"catalog_status": "under_evaluation"},
            version=system.version,
        )
        assert len(catalog.asked(session, governance)) == 1  # still being looked at
        records.update(
            session, governance, SYSTEM, system,
            {"catalog_status": "approved", "permitted_data_class": "internal"},
            version=system.version,
        )  # fmt: skip
        assert catalog.asked(session, governance) == []
        answers = session.scalars(
            select(Notification).where(Notification.title.contains("is now approved"))
        ).all()
        assert {n.account_id for n in answers} == {
            people.accounts["member"],
            people.accounts["steward"],
        }
    with db.write(member.actor) as session, pytest.raises(Conflict):
        catalog.ask(session, member, {"name": "Paperglass Editor", "reason": "Is it approved yet?"})


def test_over_the_api(as_role: Clients, db: Database, people: People) -> None:
    submit(db, people, SIMPLE)
    governance = as_role("governance")
    program = governance.get("/api/v1/program").json()["data"]["program"]
    model = copy.deepcopy(program["scoring_model"])
    model["tiers"][1]["min"] = 1
    looked = governance.post("/api/v1/program/check", json={"scoring_model": model}).json()["data"]
    assert looked["problems"] == [] and looked["impact"]["changed"] == 1
    done = governance.put("/api/v1/program", json={"scoring_model": model})
    assert (
        done.status_code == 200 and done.json()["data"]["published"]["scoring_model"] == "version 2"
    )
    assert (
        done.json()["data"]["versions"]["scoring_model"][0]["published_by"] == "Governance Person"
    )
    model["tiers"] = []
    assert governance.put("/api/v1/program", json={"scoring_model": model}).status_code == 422
    member = as_role("member")
    assert member.get("/api/v1/program").status_code == 403
    sent = member.post(
        "/api/v1/catalog/requests",
        json={"name": "Tidewick Autocomplete", "reason": "Faster analysis code."},
    )
    assert sent.status_code == 201
    assert (
        member.get("/api/v1/catalog/requests").json()["data"][0]["name"] == "Tidewick Autocomplete"
    )
    assert (
        governance.get("/api/v1/catalog/requests").json()["data"][0]["requests"][0]["by"]
        == "Member Person"
    )
