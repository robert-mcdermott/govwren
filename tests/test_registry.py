"""Reading model details from a registry: suggestions that a person accepts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.config import ConfigError, RegistryConfig, parse_config
from govwren.core.errors import NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Event, Model, Suggestion
from govwren.integration import registry
from govwren.inventory import records
from govwren.inventory.registry import MODEL, find
from tests.conftest import Instance
from tests.people import People
from tests.test_changes import linked
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
ANSWER = {
    "version": "2.1", "license": "Apache-2.0", "released": "2026-03-04T10:00:00Z",
    "parameters": "7B", "model_card": "https://models.example.org/lumen/card",
    "description": "A general language model.", "downloads": 9000, "tags": ["text"],
}  # fmt: skip


class Registry:
    def __init__(self, answer: Any) -> None:
        self.answer = answer
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, address: str, headers: dict[str, str]) -> Any:
        self.asked.append((address, headers))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _named(db: Database, people: People) -> str:
    _use, _system, model = linked(db, people)
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        found = find(session, MODEL, model)
        records.update(
            session, governance, MODEL, found,
            {"registry_name": "lumen/lumen-large", "license": "Apache-2.0"}, version=found.version,
        )  # fmt: skip
    return model


def test_nothing_is_asked_unless_a_registry_is_named(
    instance: Instance, db: Database, people: People
) -> None:
    _named(db, people)
    far = Registry(ANSWER)
    assert instance.config.registry.enabled is False
    assert registry.sync(db, instance.config, far) == {"asked": 0, "suggested": 0}
    assert far.asked == []
    with pytest.raises(ConfigError, match="https"):
        parse_config({"registry": {"url": "http://registry.example.org"}}, base_dir=instance.path)


def test_the_registry_suggests_and_a_person_decides(
    instance: Instance, db: Database, people: People, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = _named(db, people)
    monkeypatch.setenv("GOVWREN_REGISTRY_TOKEN", "s3cret")
    config = replace(
        instance.config, registry=RegistryConfig(url="https://registry.example.org/api/models/")
    )
    far = Registry(ANSWER)
    assert registry.sync(db, config, far) == {"asked": 1, "suggested": 5, "failed": 0}
    address, headers = far.asked[0]
    assert address == "https://registry.example.org/api/models/lumen/lumen-large"
    assert headers["Authorization"] == "Bearer s3cret"
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.read() as session:
        found = find(session, MODEL, model)
        waiting = registry.for_record(session, governance, MODEL, found)
        by_field = {item["field"]: item for item in waiting}
        assert set(by_field) == {
            "version_label",
            "release_date",
            "parameters",
            "card_url",
            "summary",
        }
        assert by_field["release_date"]["proposed"] == "2026-03-04"  # a day, not a moment
        assert (
            by_field["version_label"]["label"] == "Version"
            and by_field["version_label"]["current"] is None
        )
        assert "license" not in by_field  # the record already says so
        assert found.version_label is None  # nothing has changed yet
        assert all(item["can_decide"] for item in waiting)
        events_before = session.scalars(select(Event.id).order_by(Event.id.desc())).first()
    assert (
        registry.sync(db, config, far)["suggested"] == 0
    )  # the same suggestions are not made twice

    with db.write(governance.actor) as session:
        registry.accept(session, governance, by_field["version_label"]["id"])
        registry.accept(session, governance, by_field["card_url"]["id"])
        with pytest.raises(NotFound):
            registry.accept(session, governance, by_field["version_label"]["id"])  # already done
        with pytest.raises(PermissionDenied):
            registry.accept(session, member, by_field["parameters"]["id"])
    with db.bookkeeping() as session:
        registry.dismiss(session, governance, by_field["summary"]["id"])
    with db.read() as session:
        found = find(session, MODEL, model)
        assert found.version_label == "2.1" and found.card["card_url"].endswith("/lumen/card")
        assert found.summary != "A general language model."
        edit = session.scalars(
            select(Event).where(Event.id > events_before, Event.subject_type == "model")
        ).first()
        assert edit is not None and edit.actor_id == governance.account_id  # the person's own edit
        left = {item["field"] for item in registry.for_record(session, governance, MODEL, found)}
        assert left == {"release_date", "parameters"}

    far.answer = {**ANSWER, "parameters": "8B"}  # the registry moves on
    assert registry.sync(db, config, far)["suggested"] == 1
    with db.read() as session:
        rows = session.scalars(select(Suggestion).order_by(Suggestion.id)).all()
        states = {(row.field, row.proposed): row.status for row in rows}
        assert (
            states[("parameters", "7B")] == "withdrawn"
            and states[("parameters", "8B")] == "pending"
        )
        assert states[("summary", "A general language model.")] == "dismissed"  # and stays so


def test_a_registry_that_fails_or_lies_changes_nothing(
    instance: Instance, db: Database, people: People
) -> None:
    _named(db, people)
    config = replace(instance.config, registry=RegistryConfig(url="https://registry.example.org"))
    assert registry.sync(db, config, Registry(OSError("down"))) == {
        "asked": 0, "suggested": 0, "failed": 1,
    }  # fmt: skip
    assert registry.sync(db, config, Registry(None))["suggested"] == 0  # not known there
    strange = {
        "version": {"nested": 1},
        "released": "last spring",
        "model_card": "javascript:alert(1)",
        "license": ["a", "b"],
        "description": "x" * 3000,
        "parameters": True,
    }
    assert registry.sync(db, config, Registry(strange))["suggested"] == 0
    assert registry.sync(db, config, Registry("not an object"))["suggested"] == 0
    with db.read() as session:
        assert session.scalars(select(Model.version_label)).one() is None


def test_over_the_api(as_role: Clients, instance: Instance, db: Database, people: People) -> None:
    model = _named(db, people)
    config = replace(instance.config, registry=RegistryConfig(url="https://registry.example.org"))
    registry.sync(db, config, Registry(ANSWER))
    governance = as_role("governance")
    waiting = governance.get(f"/api/v1/records/{model}/suggestions").json()["data"]
    assert len(waiting) == 5
    first = next(item for item in waiting if item["field"] == "parameters")
    assert governance.post(f"/api/v1/suggestions/{first['id']}/accept").status_code == 200
    assert governance.get(f"/api/v1/models/{model}").json()["data"]["parameters"] == "7B"
    other = next(item for item in waiting if item["field"] == "summary")
    assert as_role("member").post(f"/api/v1/suggestions/{other['id']}/accept").status_code == 403
    assert governance.post(f"/api/v1/suggestions/{other['id']}/dismiss").status_code == 200
    assert len(governance.get(f"/api/v1/records/{model}/suggestions").json()["data"]) == 3
    assert governance.post("/api/v1/suggestions/9999/accept").status_code == 404
