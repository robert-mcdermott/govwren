"""The demo organization: built by the real services, the same every time for a seed, with
something on every screen and a history that verifies."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from govwren import reporting
from govwren.api.app import create_app
from govwren.cli import main
from govwren.core.errors import GovWrenError
from govwren.db.engine import Database
from govwren.db.models import (
    Account,
    Agreement,
    AISystem,
    Condition,
    Dataset,
    Event,
    Evidence,
    Model,
    OrgUnit,
    Review,
    StoredFile,
    UseCase,
    Vendor,
)
from govwren.demo import build as demo
from govwren.demo import content
from govwren.events import chain
from govwren.evidence import service
from govwren.inventory import agreements, catalog, links, registry
from tests.conftest import Instance

TODAY = date(2026, 11, 18)
SMALL = 70  # requests: enough for every storyline and some of everything else


@pytest.fixture
def built(instance: Instance, db: Database) -> demo.Summary:
    return demo.build(db, seed=7, today=TODAY, use_cases=SMALL, files_dir=instance.home.files)


def fingerprint(db: Database) -> list[tuple[object, ...]]:
    with db.read() as session:
        rows: list[tuple[object, ...]] = []
        rows += session.execute(
            select(UseCase.ref, UseCase.name, UseCase.status, UseCase.tier)
        ).all()
        rows += session.execute(select(Review.ref, Review.status, Review.opened_at)).all()
        rows += session.execute(select(Account.email, Account.title)).all()
        rows += session.execute(select(AISystem.ref, AISystem.name, AISystem.catalog_status)).all()
        return [tuple(row) for row in rows]


def test_it_has_something_of_everything(db: Database, built: demo.Summary) -> None:
    with db.read() as session:
        count = lambda model: session.execute(select(func.count()).select_from(model)).scalar_one()  # noqa: E731
        assert count(OrgUnit) >= 60 and count(Account) >= 230 and count(Vendor) == 40
        assert count(AISystem) >= len(content.CATALOG)
        assert count(UseCase) == SMALL
        statuses = dict(
            session.execute(select(UseCase.status, func.count()).group_by(UseCase.status)).all()
        )
        assert {"draft", "in_review", "returned", "approved_with_conditions", "declined"} <= set(
            statuses
        )
        open_now = dict(
            session.execute(select(Review.status, func.count()).group_by(Review.status)).all()
        )
        assert {"triage", "in_review", "with_requester", "ready", "decided"} <= set(open_now)
        tiers = {tier for (tier,) in session.execute(select(UseCase.tier).distinct())}
        assert {1, 2, 3, 4} <= tiers
        assert count(Condition) > 100
        assert (
            session.execute(
                select(func.count())
                .select_from(Condition)
                .where(Condition.status == "open", Condition.kind == "before_use")
            ).scalar_one()
            >= 1
        )
        usable = [row for row in catalog.listing(session) if row["usable"]]
        assert len(usable) >= 25 and any(row["uses"] for row in usable)
        # Models with lineage, datasets of every class, and agreements at every stage.
        assert count(Model) >= 40 and count(Dataset) >= 40 and count(Agreement) >= 30
        origins = {origin for (origin,) in session.execute(select(Model.origin).distinct())}
        assert origins >= {"commercial_api", "open_weights", "fine_tuned", "in_house"}
        classes = {c for (c,) in session.execute(select(Dataset.data_class).distinct())}
        assert classes == {"public", "internal", "protected", "restricted"}
        classifier = session.scalars(
            select(Model).where(Model.name == "Variant effect classifier")
        ).one()
        assert classifier.data_class == "restricted"  # inherited from what it was trained on
        seen = links.of(session, demo.ME, registry.MODEL, classifier)
        assert {entry["label"] for entry in seen["outgoing"]} == {"Derived from", "Trained on"}
        assert [entry["label"] for entry in seen["incoming"]] == ["Used by"]
        states = {agreements.state(a) for a in session.scalars(select(Agreement))}
        assert states == {"current", "ending", "notice", "ended"}
        agents = [s for s in session.scalars(select(AISystem)) if s.agent_profile]
        assert len(agents) >= 3
        assert any(row["type"] == "model" and row["uses"] for row in catalog.listing(session))
        # Evidence with real files behind it, some of it out of date.
        assert count(Evidence) >= 30 and count(StoredFile) >= 20
        states = {service.state(e) for e in session.scalars(select(Evidence))}
        assert {"current", "expired"} <= states
        figures = reporting.dashboard(session)
        assert figures["reviews"]["overdue"] >= 1 and figures["decisions"]["by_people"] >= 1
        assert len(figures["by_unit"]) >= 5
        # Four levels of units.
        parents = dict(session.execute(select(OrgUnit.id, OrgUnit.parent_id)).all())
        depth = lambda unit: 1 if parents[unit] is None else 1 + depth(parents[unit])  # noqa: E731
        assert max(depth(unit) for unit in parents) == 4
        # Thirty months of history, in order.
        first, last = session.execute(select(func.min(Event.at), func.max(Event.at))).one()
        assert (last - first).days > 880


def test_the_history_verifies_and_runs_forward(db: Database, built: demo.Summary) -> None:
    with db.engine.connect() as conn:
        report = chain.verify(conn)
    assert report.ok and report.events > 1500
    with db.read() as session:
        times = [at for (at,) in session.execute(select(Event.at).order_by(Event.id))]
    assert times == sorted(times)


def test_nobody_in_the_demo_has_a_password_and_everyone_is_invented(
    db: Database, built: demo.Summary
) -> None:
    from govwren.db.models import Credential

    with db.read() as session:
        assert session.execute(select(func.count()).select_from(Credential)).scalar_one() == 0
        emails = [email for (email,) in session.execute(select(Account.email))]
    assert all(email.endswith("@alderpoint.example") for email in emails)
    assert len(emails) == len(set(emails))
    assert [person["key"] for person in built.sample_accounts] == [key for key, *_ in content.CAST]


def test_the_same_seed_gives_the_same_organization(tmp_path: Path) -> None:
    from govwren.db import migrate

    prints = []
    for name, seed in (("a", 3), ("b", 3), ("c", 4)):
        db = Database(f"sqlite:///{tmp_path / name}.db")
        migrate.upgrade(db.engine)
        demo.build(db, seed=seed, today=TODAY, use_cases=40)
        prints.append(fingerprint(db))
        db.dispose()
    assert prints[0] == prints[1]
    assert prints[0] != prints[2]


def test_it_will_not_build_over_an_organization(db: Database, built: demo.Summary) -> None:
    with pytest.raises(GovWrenError):
        demo.build(db, seed=7, today=TODAY, use_cases=5)


def test_sample_people_sign_in_with_one_click_only_on_a_demo(
    instance: Instance, db: Database, client: TestClient
) -> None:
    assert client.get("/api/v1/meta").json()["data"]["demo"] is None
    refused = client.post("/api/v1/session/demo", json={"email": "sam.reyes@alderpoint.example"})
    assert refused.status_code == 404

    demo.build(db, seed=7, today=TODAY, use_cases=20)
    shown = client.get("/api/v1/meta").json()["data"]["demo"]
    assert [person["name"] for person in shown["accounts"]][:2] == ["Dana Okafor", "Sam Reyes"]
    with db.read() as session:
        other = session.scalars(
            select(Account.email).where(
                Account.email.notin_([p["email"] for p in shown["accounts"]])
            )
        ).first()
    assert client.post("/api/v1/session/demo", json={"email": other}).status_code == 404

    done = client.post("/api/v1/session/demo", json={"email": "sam.reyes@alderpoint.example"})
    assert done.status_code == 200 and "governance" in done.json()["data"]["roles"]
    assert client.get("/api/v1/dashboard").status_code == 200
    assert client.get("/api/v1/reviews").json()["data"]

    with TestClient(create_app(instance.config), client=("203.0.113.9", 4000)) as elsewhere:
        away = elsewhere.post(
            "/api/v1/session/demo",
            json={"email": "sam.reyes@alderpoint.example"},
            headers={"origin": "http://testserver"},
        )
    assert away.status_code == 404


def test_every_sample_person_has_something_to_look_at(
    instance: Instance, db: Database, built: demo.Summary
) -> None:
    for person in built.sample_accounts:
        with TestClient(create_app(instance.config)) as client:
            signed = client.post("/api/v1/session/demo", json={"email": person["email"]})
            assert signed.status_code == 200
            assert client.get("/api/v1/use-cases").json()["data"], person["name"]
            assert client.get("/api/v1/catalog").json()["data"]
    with TestClient(create_app(instance.config)) as member:
        member.post("/api/v1/session/demo", json={"email": "tomas.lind@alderpoint.example"})
        kinds = {item["kind"] for item in member.get("/api/v1/me/work").json()["data"]}
    assert {"question", "draft", "condition"} <= kinds


@pytest.mark.sqlite_only
def test_the_command_builds_a_demo_and_refuses_to_overwrite_other_things(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        demo,
        "build",
        lambda db, **kw: demo.Builder(
            db, seed=kw["seed"], today=TODAY, files_dir=kw.get("files_dir")
        ).build(use_cases=25),
    )
    target = tmp_path / "demo"
    assert main(["demo", str(target), "--seed", "2"]) == 0
    out = capsys.readouterr().out
    assert "which verify" in out and f"--config {target / 'govwren.toml'} serve" in out
    assert main(["demo", str(target)]) != 0  # already there
    assert main(["demo", str(target), "--force"]) == 0
    other = tmp_path / "other"
    other.mkdir()
    (other / "notes.txt").write_text("keep me")
    assert main(["demo", str(other), "--force"]) != 0
    assert (other / "notes.txt").read_text() == "keep me"
    assert main(["--config", str(target / "govwren.toml"), "serve", "--host", "0.0.0.0"]) != 0
