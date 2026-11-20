"""The optional assistant: off unless configured, and kept in its place when on."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import assistant
from govwren.config import AssistantConfig, ConfigError, parse_config
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import AssistantExchange, Event, Review, UseCase
from tests.conftest import Instance
from tests.people import People
from tests.test_review import HIGH, MODERATE, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
ON = AssistantConfig(url="https://models.example.org/v1", model="local-7b")


class Model:
    """Stands in for the model server: says what it is told to, and remembers what it saw."""

    def __init__(self, says: Any) -> None:
        self.says = says
        self.saw: list[list[dict[str, str]]] = []

    def __call__(self, config: AssistantConfig, messages: list[dict[str, str]]) -> str:
        self.saw.append(messages)
        if isinstance(self.says, Exception):
            raise self.says
        return self.says if isinstance(self.says, str) else json.dumps(self.says)


def test_there_is_no_assistant_unless_one_is_configured(
    as_role: Clients, instance: Instance, db: Database, people: People
) -> None:
    assert instance.config.assistant.enabled is False
    assert as_role(None).get("/api/v1/meta").json()["data"]["assistant"] is False
    member = as_role("member")
    refused = member.post("/api/v1/assistant/draft", json={"description": "x" * 40})
    assert refused.status_code == 404
    with db.read() as session, pytest.raises(NotFound):
        assistant.suggest_answers(
            session, who(db, people, "member"), instance.config.assistant, "x" * 40, Model({})
        )
    for raw in ({"url": "https://m.example.org/v1"}, {"model": "m"},
                {"url": "http://m.example.org/v1", "model": "m"}):  # fmt: skip
        with pytest.raises(ConfigError):
            parse_config({"assistant": raw}, base_dir=instance.path)
    local = parse_config(
        {"assistant": {"url": "http://localhost:11434/v1", "model": "m"}}, base_dir=instance.path
    )
    assert local.assistant.enabled  # a model on this machine needs no TLS


def test_suggested_answers_are_checked_like_any_others(db: Database, people: People) -> None:
    member = who(db, people, "member")
    far = Model('Here you go:\n```json\n' + json.dumps({
        "name": "Summarizing seminar recordings",
        "purpose": "Turn recorded seminars into short written summaries for the lab.",
        "domain": "research",
        "data_class": "top_secret",            # not one of the choices: dropped
        "affected_groups": ["team", "martians"],  # one real, one invented: dropped whole
        "unit": 99,                            # not the assistant's to say
        "launch_codes": "0000",                # not a question
    }) + "\n```")  # fmt: skip
    description = "We record our weekly seminars and want short written summaries of each."
    with db.write(member.actor) as session:
        found = assistant.suggest_answers(session, member, ON, description, far)
    assert found["answers"] == {
        "name": "Summarizing seminar recordings",
        "purpose": "Turn recorded seminars into short written summaries for the lab.",
        "domain": "research",
    }
    assert set(found["dropped"]) == {"data_class", "affected_groups"}
    assert "Read every answer" in found["note"]
    system, user = far.saw[0]
    assert "do not guess" in system["content"] and "not instructions" in system["content"]
    sent = json.loads(user["content"])
    assert sent["description"] == description
    keys = {q["key"] for q in sent["questions"]}
    assert "purpose" in keys and "unit" not in keys and "systems" not in keys
    with db.read() as session:
        assert session.scalars(select(UseCase)).first() is None  # nothing was saved or begun
        kept = session.scalars(select(AssistantExchange)).one()
        assert kept.purpose == "draft" and kept.ok and kept.account_id == member.account_id
        assert description in kept.prompt and "Summarizing seminar" in (kept.response or "")
        event = session.scalars(
            select(Event).where(Event.subject_type == "assistant_exchange")
        ).one()
        assert "prompt" not in event.changes and event.changes["purpose"][1] == "draft"

    with db.write(member.actor) as session, pytest.raises(Invalid):
        assistant.suggest_answers(session, member, ON, "too short", far)


def test_an_exchange_that_fails_is_kept_too(db: Database, people: People) -> None:
    member = who(db, people, "member")
    description = "We record our weekly seminars and want short written summaries of each."
    with db.write(member.actor) as session:
        down = assistant.suggest_answers(
            session, member, ON, description,
            Model(assistant.AssistantError("The assistant could not be reached.")),
        )  # fmt: skip
        vague = assistant.suggest_answers(session, member, ON, description, Model("I cannot."))
    assert down == {"failed": "The assistant could not be reached."}
    assert vague == {"failed": "The assistant did not give answers that could be read."}
    with db.read() as session:
        kept = session.scalars(select(AssistantExchange).order_by(AssistantExchange.id)).all()
        assert [(row.ok, row.error) for row in kept] == [
            (False, "The assistant could not be reached."),
            (False, "The assistant did not give answers that could be read."),
        ]
        assert kept[1].response == "I cannot." and description in kept[0].prompt


def test_a_summary_is_for_reviewers_and_never_for_sensitive_requests(
    db: Database, people: People
) -> None:
    moderate = request(db, people, MODERATE)
    high = request(db, people, HIGH)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    far = Model("- A lab wants to summarize notes.\n- Privacy has not yet reviewed it.")
    with db.write(governance.actor) as session:
        review = session.scalars(select(Review).where(Review.ref == moderate)).one()
        loose = replace(ON, max_data_class="protected")
        made = assistant.summarize_review(session, governance, loose, review, far)
        assert made["summary"].startswith("- A lab wants") and made["model"] == "local-7b"
        assert "Decide from the packet" in made["note"]
        system, user = far.saw[0]
        assert "Do not recommend a decision" in system["content"]
        assert json.loads(user["content"])["request"]
        with pytest.raises(PermissionDenied):  # the requester does not see reviewers' words
            assistant.summarize_review(session, member, loose, review, far)
        strict = replace(ON, max_data_class="public")
        with pytest.raises(Invalid) as refused:
            assistant.summarize_review(session, governance, strict, review, far)
        assert "not approved for that" in refused.value.errors["review"]
        with pytest.raises(Invalid):  # the default limit is Internal, and this is Protected
            assistant.summarize_review(session, governance, ON, review, far)
        simple = session.scalars(select(Review).where(Review.ref == high)).one()
        assistant.summarize_review(session, governance, ON, simple, far)  # Internal data: sent
        assert len(far.saw) == 2  # the refused requests were never sent
    with db.read() as session:
        kept = session.scalars(select(AssistantExchange).order_by(AssistantExchange.id)).first()
        assert kept is not None and kept.purpose == "summary" and kept.subject_ref == moderate
        listed = assistant.exchanges(session, who(db, people, "auditor"))
        assert listed[0]["by"] and listed[0]["response"].startswith("- A lab")
        with pytest.raises(PermissionDenied):
            assistant.exchanges(session, member)


def test_over_the_api(as_role: Clients, instance: Instance, db: Database, people: People) -> None:
    moderate = request(db, people, MODERATE)
    member = as_role("member")
    app = member.app
    app.state.config = replace(  # type: ignore[attr-defined]
        instance.config, assistant=replace(ON, max_data_class="protected")
    )
    app.state.assistant_ask = Model({"name": "Summarizing seminar recordings"})  # type: ignore[attr-defined]
    try:
        assert as_role(None).get("/api/v1/meta").json()["data"]["assistant"] is True
        drafted = as_role("member").post(
            "/api/v1/assistant/draft",
            json={"description": "We want short summaries of our recorded weekly seminars."},
        )
        assert drafted.status_code == 200
        assert drafted.json()["data"]["answers"] == {"name": "Summarizing seminar recordings"}
        app.state.assistant_ask = Model("- One point.")  # type: ignore[attr-defined]
        summed = as_role("governance").post(f"/api/v1/reviews/{moderate}/summary")
        assert summed.status_code == 200 and summed.json()["data"]["summary"] == "- One point."
        assert as_role("member").post(f"/api/v1/reviews/{moderate}/summary").status_code == 403
        seen = as_role("auditor").get("/api/v1/assistant/exchanges").json()["data"]
        assert seen["enabled"] and [e["purpose"] for e in seen["exchanges"]] == ["summary", "draft"]
        assert as_role("member").get("/api/v1/assistant/exchanges").status_code == 403
        app.state.assistant_ask = Model(
            assistant.AssistantError("The assistant could not be reached.")
        )  # type: ignore[attr-defined]
        failed = as_role("member").post(
            "/api/v1/assistant/draft",
            json={"description": "We want short summaries of our recorded weekly seminars."},
        )
        assert failed.status_code == 502 and "could not be reached" in failed.json()["detail"]
        seen = as_role("auditor").get("/api/v1/assistant/exchanges").json()["data"]
        assert seen["exchanges"][0]["ok"] is False  # the failure is on the record too
    finally:
        app.state.config = instance.config  # type: ignore[attr-defined]
