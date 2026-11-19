"""Models, datasets, agent profiles, links between records, references to other systems, and
vendor agreements."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Agreement, RecordLink
from govwren.inventory import agreements, catalog, history, links, records
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, USE_CASE, VENDOR, find
from tests.people import ME, People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


@dataclass
class Shelf:
    base: str  # open weights, approved in the catalog
    tuned: str  # the member's fine-tune of it
    public: str  # a public dataset
    cohort: str  # a restricted dataset
    system: str  # an app built in-house
    vendor: str


@pytest.fixture
def shelf(db: Database, people: People) -> Shelf:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(ME.actor) as session:
        vendor = records.create(session, governance, VENDOR, {"name": "Cobaltine Compute"})
        base = records.create(
            session, governance, MODEL,
            {"name": "Wrenlet 7B", "kind": "language", "origin": "open_weights",
             "provider": "Open Models Collective", "version_label": "1.2", "license": "Apache-2.0",
             "modality": ["text", "code"], "weights_format": "safetensors",
             "weights_checksum": "sha256:9f2c", "runs_on": "The research computing cluster.",
             "intended_use": "General text tasks.",
             "catalog_status": "approved", "permitted_data_class": "protected",
             "terms": "Run it on institute equipment only."},
        )  # fmt: skip
        tuned = records.create(
            session, member, MODEL,
            {"name": "Sleep-stage notes model", "kind": "language", "origin": "fine_tuned",
             "org_unit_id": people.units["HALE"], "tuning_method": "adapter"},
        )  # fmt: skip
        public = records.create(
            session, member, DATASET,
            {"name": "Published sleep corpus", "data_class": "public",
             "identifiability": "not_about_people"},
        )  # fmt: skip
        cohort = records.create(
            session, member, DATASET,
            {"name": "Sleep cohort recordings", "data_class": "restricted",
             "data_categories": ["health", "human_subjects"], "subjects": ["participants"],
             "identifiability": "coded", "restrictions": "Research use under the protocol only."},
        )  # fmt: skip
        system = records.create(
            session, member, SYSTEM, {"name": "Sleep notes app", "kind": "internal_app"}
        )
        return Shelf(base.ref, tuned.ref, public.ref, cohort.ref, system.ref, vendor.ref)


def test_a_model_records_what_it_is_and_where_it_came_from(
    db: Database, people: People, shelf: Shelf
) -> None:
    member = who(db, people, "member")
    with db.read() as session:
        seen = records.detail(session, member, MODEL, find(session, MODEL, shelf.base))
        assert seen["origin"] == "open_weights" and seen["weights_format"] == "safetensors"
        assert (
            seen["modality"] == ["text", "code"] and seen["intended_use"] == "General text tasks."
        )
        assert seen["catalog_status"] == "approved" and seen["can"]["edit"] is False
        mine = records.detail(session, member, MODEL, find(session, MODEL, shelf.tuned))
        assert mine["can"]["edit"] and mine["owners"][0]["kind"] == "accountable"
        rows, total = records.search(session, member, MODEL, {"origin": "fine_tuned"})
        assert total == 1 and records.cards(session, member, MODEL, rows)[0]["ref"] == shelf.tuned


def test_what_is_saved_is_checked(db: Database, people: People, shelf: Shelf) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        with pytest.raises(Invalid) as caught:
            records.create(session, member, MODEL, {"name": "x", "kind": "telepathy"})
        assert set(caught.value.errors) == {"kind", "origin"}
        with pytest.raises(Invalid) as caught:
            records.create(
                session, member, MODEL,
                {"name": "x", "kind": "language", "origin": "in_house", "release_date": "soon",
                 "card_url": "ftp://x", "favourite_colour": "green", "modality": ["smell"]},
            )  # fmt: skip
        assert set(caught.value.errors) == {
            "release_date",
            "card_url",
            "favourite_colour",
            "modality",
        }
        tuned = find(session, MODEL, shelf.tuned)
        with pytest.raises(Invalid) as caught:  # the catalog is governance's to keep
            records.update(session, member, MODEL, tuned, {"catalog_status": "approved"}, version=1)
        assert "catalog_status" in caught.value.errors
        with pytest.raises(Invalid):
            records.create(session, member, DATASET, {"name": "No class given"})
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        tuned = find(session, MODEL, shelf.tuned)
        with pytest.raises(Invalid) as caught:
            records.update(
                session, governance, MODEL, tuned, {"catalog_status": "approved"}, version=1
            )
        assert "permitted_data_class" in caught.value.errors


def test_a_model_is_as_sensitive_as_what_it_was_trained_on(
    db: Database, people: People, shelf: Shelf
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        links.add(session, member, shelf.tuned, "derived_from", shelf.base)
        links.add(session, member, shelf.tuned, "trained_on", shelf.public)
        tuned = find(session, MODEL, shelf.tuned)
        assert tuned.data_class == "public"
        links.add(session, member, shelf.tuned, "trained_on", shelf.cohort)
        assert tuned.data_class == "restricted"  # raised at once
        with pytest.raises(Invalid) as caught:
            records.update(
                session, member, MODEL, tuned, {"data_class": "internal"}, version=tuned.version
            )
        assert "Restricted" in caught.value.errors["data_class"]
        seen = records.detail(session, member, MODEL, tuned)
        assert seen["data_class_floor"] == "restricted"
        assert [d["ref"] for d in seen["data_class_from"]] == [shelf.cohort]
        # And so is anything derived from it, however far down.
        child = records.create(
            session,
            member,
            MODEL,
            {"name": "Distilled notes model", "kind": "language", "origin": "fine_tuned"},
        )
        links.add(session, member, child.ref, "derived_from", shelf.tuned)
        assert child.data_class == "restricted"


def test_links_join_only_what_makes_sense_and_never_loop(
    db: Database, people: People, shelf: Shelf
) -> None:
    member, steward = who(db, people, "member"), who(db, people, "auditor")
    with db.write(member.actor) as session:
        links.add(session, member, shelf.system, "built_on", shelf.tuned, note="Served by the lab")
        links.add(session, member, shelf.tuned, "derived_from", shelf.base)
        again = links.add(session, member, shelf.tuned, "derived_from", shelf.base)
        assert (
            session.scalars(select(RecordLink).where(RecordLink.relation == "derived_from")).one()
            == again
        )
        with pytest.raises(Invalid):  # a dataset is not built on a model
            links.add(session, member, shelf.cohort, "built_on", shelf.base)
        with pytest.raises(Invalid):
            links.add(session, member, shelf.tuned, "derived_from", shelf.tuned)
        with pytest.raises(PermissionDenied):  # the base model is not the member's to edit
            links.add(session, member, shelf.base, "derived_from", shelf.tuned)
        with pytest.raises(NotFound):
            links.add(session, member, shelf.tuned, "trained_on", "DS-9999")
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        with pytest.raises(Invalid) as caught:
            links.add(session, governance, shelf.base, "derived_from", shelf.tuned)
        assert "loop" in caught.value.errors["to"]
    with db.read() as session:
        seen = links.of(session, member, MODEL, find(session, MODEL, shelf.tuned))
        assert [(e["label"], e["record"]["ref"]) for e in seen["outgoing"]] == [
            ("Derived from", shelf.base)
        ]
        assert [(e["label"], e["record"]["ref"], e["note"]) for e in seen["incoming"]] == [
            ("Built into", shelf.system, "Served by the lab")
        ]
        link_id = seen["outgoing"][0]["id"]
    with db.write(steward.actor) as session, pytest.raises(PermissionDenied):
        links.remove(session, steward, link_id)  # an auditor reads and changes nothing
    with db.write(member.actor) as session:
        links.remove(session, member, link_id)
        assert links.of(session, member, MODEL, find(session, MODEL, shelf.tuned))["outgoing"] == []


def test_records_point_to_things_in_other_systems(
    db: Database, people: People, shelf: Shelf
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        cohort = find(session, DATASET, shelf.cohort)
        saved = links.set_references(session, member, DATASET, cohort, [
            {"kind": "protocol", "identifier": "ALD-HS-0412", "label": "Sleep cohort protocol"},
            {"kind": "agreement", "identifier": "ALD-AGR-0231", "url": "https://contracts.alderpoint.example/231"},
        ])  # fmt: skip
        assert [r["identifier"] for r in saved] == ["ALD-AGR-0231", "ALD-HS-0412"]
        with pytest.raises(Invalid) as caught:
            links.set_references(session, member, DATASET, cohort, [
                {"kind": "horoscope", "identifier": "x"}, {"kind": "grant", "identifier": ""},
                {"kind": "ticket", "identifier": "T-1", "url": "javascript:alert(1)"}])  # fmt: skip
        assert len(caught.value.errors) == 3
        links.set_references(
            session, member, DATASET, cohort, [{"kind": "protocol", "identifier": "ALD-HS-0412"}]
        )
        base = find(session, MODEL, shelf.base)
        with pytest.raises(PermissionDenied):
            links.set_references(session, member, MODEL, base, [])
    with db.read() as session:
        cohort = find(session, DATASET, shelf.cohort)
        assert len(records.detail(session, member, DATASET, cohort)["references"]) == 1
        titles = [
            entry["title"] for entry in history.for_record(session, DATASET, cohort, internal=True)
        ]
        assert "Added a reference: Agreement ALD-AGR-0231" in titles
        assert "Removed a reference: Agreement ALD-AGR-0231" in titles


def test_an_agent_says_what_it_may_do_and_how_it_is_stopped(
    db: Database, people: People, shelf: Shelf
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        system = find(session, SYSTEM, shelf.system)
        records.update(session, member, SYSTEM, system, {"kind": "agent", "agent_profile": {
            "autonomy_level": "within_limits", "actions": "Closes tickets on its allow-list.",
            "identity": "svc-desk-agent", "reversibility": "reversible",
            "human_override": "A switch in the console."}}, version=system.version)  # fmt: skip
        records.update(
            session,
            member,
            SYSTEM,
            system,
            {"agent_profile": {"identity": None, "limits": "50 tickets an hour"}},
            version=system.version,
        )
        with pytest.raises(Invalid) as caught:
            records.update(
                session,
                member,
                SYSTEM,
                system,
                {"agent_profile": {"autonomy_level": "godlike"}},
                version=system.version,
            )
        assert "agent_profile.autonomy_level" in caught.value.errors
    with db.read() as session:
        profile = records.detail(session, member, SYSTEM, find(session, SYSTEM, shelf.system))[
            "agent_profile"
        ]
        assert profile == {
            "autonomy_level": "within_limits", "actions": "Closes tickets on its allow-list.",
            "reversibility": "reversible", "human_override": "A switch in the console.",
            "limits": "50 tickets an hour",
        }  # fmt: skip


def test_agreements_know_when_they_end(db: Database, people: People, shelf: Shelf) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    today = date(2026, 11, 18)
    with (
        frozen_at(__import__("datetime").datetime(2026, 11, 18, 12)),
        db.write(governance.actor) as session,
    ):
        vendor = find(session, VENDOR, shelf.vendor)
        made: dict[str, Agreement] = {}
        for key, ends, notice, renews in [
            ("far", today + timedelta(days=400), 60, False),
            ("soon", today + timedelta(days=45), None, False),
            ("notice", today + timedelta(days=120), 180, False),
            ("ended", today - timedelta(days=3), None, False),
            ("rolling", today - timedelta(days=3), None, True),
            ("open", None, None, False),
        ]:
            made[key] = agreements.create(session, governance, vendor, {
                "kind": "master", "title": f"Agreement {key}", "effective_on": "2025-01-01",
                "expires_on": ends.isoformat() if ends else None, "notice_days": notice,
                "auto_renews": renews, "owner_id": people.accounts["governance"]})  # fmt: skip
        states = {key: agreements.state(row) for key, row in made.items()}
        assert states == {"far": "current", "soon": "ending", "notice": "notice", "ended": "ended",
                          "rolling": "current", "open": "current"}  # fmt: skip
        assert {a.title for a, _ in agreements.needing_attention(session)} == {
            "Agreement soon", "Agreement notice", "Agreement ended"}  # fmt: skip
        shown = records.detail(session, governance, VENDOR, vendor)["agreements"]
        assert shown[0]["title"] == "Agreement ended" and shown[0]["days_left"] == -3
        assert shown[-1]["title"] == "Agreement open"
        with pytest.raises(Invalid) as caught:
            agreements.create(session, governance, vendor, {"kind": "handshake", "title": ""})
        assert set(caught.value.errors) == {"kind", "title"}
        with pytest.raises(Invalid):
            agreements.update(session, governance, made["far"].id, {"expires_on": "2024-01-01"})
        agreements.update(session, governance, made["soon"].id, {"expires_on": "2028-01-01"})
        agreements.remove(session, governance, made["ended"].id)
        assert {a.title for a, _ in agreements.needing_attention(session)} == {"Agreement notice"}
    with db.write(member.actor) as session, pytest.raises(PermissionDenied):
        agreements.create(
            session, member, find(session, VENDOR, shelf.vendor), {"kind": "master", "title": "x"}
        )


def test_a_use_of_an_approved_model_registers_like_a_tool(
    db: Database, people: People, shelf: Shelf
) -> None:
    member = who(db, people, "member")
    values = {"name": "Summarizing our own protocols", "org_unit_id": people.units["HALE"],
              "data_class": "internal", "data_categories": [], "everyday": True}  # fmt: skip
    with db.write(member.actor) as session:
        listed = catalog.listing(session)
        assert [(row["type"], row["name"]) for row in listed] == [("model", "Wrenlet 7B")]
        assert listed[0]["vendor"] == "Open Models Collective" and listed[0]["edition"] == "1.2"
        base = catalog.find_system(session, shelf.base)
        done = catalog.register(session, member, base, values)
        assert done["registered"]
        use_case = find(session, USE_CASE, done["ref"])
        seen = links.of(session, member, USE_CASE, use_case)
        assert [(e["label"], e["record"]["ref"]) for e in seen["outgoing"]] == [
            ("Uses", shelf.base)
        ]
        assert catalog.listing(session)[0]["uses"] == 1
        beyond = catalog.register(session, member, base, {**values, "data_class": "restricted"})
        assert not beyond["registered"]
        with pytest.raises(NotFound):
            catalog.find_system(session, shelf.cohort)
        with pytest.raises(Conflict):  # what an approved use relies on is part of what was approved
            links.add(session, member, use_case.ref, "processes", shelf.public)


def test_over_the_api(as_role: Clients, people: People, shelf: Shelf) -> None:
    member = as_role("member")
    types = member.get("/api/v1/record-types").json()["data"]
    assert {f["key"] for f in types["model"]} >= {
        "kind",
        "origin",
        "weights_checksum",
        "intended_use",
    }
    assert {"relation": "trained_on", "label": "Trained on", "to": "dataset"} in types["links"][
        "model"
    ]
    made = member.post(
        "/api/v1/datasets", json={"name": "Wearable pilot data", "data_class": "protected"}
    )
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    assert ref.startswith("DS-")
    changed = member.patch(
        f"/api/v1/datasets/{ref}", json={"version": 1, "retention": "Five years"}
    )
    assert changed.json()["data"]["retention"] == "Five years"
    assert (
        member.patch(f"/api/v1/datasets/{ref}", json={"version": 1, "retention": "x"}).status_code
        == 409
    )
    linked = member.post(
        "/api/v1/links", json={"source": shelf.tuned, "relation": "trained_on", "target": ref}
    )
    assert linked.status_code == 201
    link_id = linked.json()["data"]["outgoing"][0]["id"]
    model = member.get(f"/api/v1/models/{shelf.tuned}").json()["data"]
    assert (
        model["data_class"] == "protected" and model["links"]["outgoing"][0]["record"]["ref"] == ref
    )
    listed = member.get("/api/v1/models", params={"data_class": "protected"}).json()["data"]
    assert [row["ref"] for row in listed] == [shelf.tuned]
    refs = member.put(
        f"/api/v1/records/{ref}/references",
        json={"references": [{"kind": "grant", "identifier": "ALD-GR-77"}]},
    )
    assert refs.json()["data"][0]["identifier"] == "ALD-GR-77"
    assert member.delete(f"/api/v1/links/{link_id}").status_code == 200
    events = member.get(f"/api/v1/models/{shelf.tuned}/history").json()["data"]
    assert any(e["title"].startswith("Trained on: Wearable pilot data") for e in events)
    governance = as_role("governance")
    agreed = governance.post(
        f"/api/v1/vendors/{shelf.vendor}/agreements",
        json={"kind": "data_processing", "title": "Processing terms", "expires_on": "2031-01-01"},
    )
    assert agreed.status_code == 201
    assert (
        member.patch(
            f"/api/v1/agreements/{agreed.json()['data']['id']}", json={"title": "Mine now"}
        ).status_code
        == 403
    )
    assert (
        member.get(f"/api/v1/vendors/{shelf.vendor}").json()["data"]["agreements"][0]["title"]
        == "Processing terms"
    )


def test_the_graph_walks_both_ways_and_stops_at_what_cannot_be_seen(
    db: Database, people: People, shelf: Shelf, as_role: Clients
) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(governance.actor) as session:
        base = find(session, MODEL, shelf.base)
        records.update(
            session, governance, MODEL, base, {"vendor": shelf.vendor}, version=base.version
        )
        secret = records.create(
            session, governance, DATASET,
            {"name": "Sealed data", "data_class": "restricted", "restricted": True},
        )  # fmt: skip
        links.add(session, governance, shelf.base, "evaluated_on", secret.ref)
    with db.write(member.actor) as session:
        links.add(session, member, shelf.tuned, "derived_from", shelf.base)
        links.add(session, member, shelf.tuned, "trained_on", shelf.cohort)
        links.add(session, member, shelf.system, "built_on", shelf.tuned)
    with db.read() as session:
        seen = links.graph(session, member, MODEL, find(session, MODEL, shelf.tuned))
        by_ref = {node["ref"]: node for node in seen["nodes"]}
        assert seen["centre"] == shelf.tuned and by_ref[shelf.tuned]["distance"] == 0
        assert (by_ref[shelf.base]["side"], by_ref[shelf.base]["distance"]) == ("upstream", 1)
        assert by_ref[shelf.base]["via"] == "Derived from"
        vendor = by_ref[shelf.vendor]  # two steps up: the base model's supplier
        assert (vendor["side"], vendor["distance"], vendor["via"]) == ("upstream", 2, "Supplied by")
        assert vendor["through"] == shelf.base
        assert (by_ref[shelf.system]["side"], by_ref[shelf.system]["via"]) == (
            "downstream",
            "Built into",
        )
        assert seen["hidden"] == 1 and "Sealed data" not in {n["name"] for n in seen["nodes"]}
        assert {(e["from"], e["relation"], e["to"]) for e in seen["edges"]} == {
            (shelf.tuned, "derived_from", shelf.base), (shelf.tuned, "trained_on", shelf.cohort),
            (shelf.base, "supplied_by", shelf.vendor), (shelf.system, "built_on", shelf.tuned),
        }  # fmt: skip
        near = links.graph(session, member, MODEL, find(session, MODEL, shelf.tuned), depth=1)
        assert shelf.vendor not in {node["ref"] for node in near["nodes"]}
        # From the vendor, everything that depends on it, however far down.
        down = links.graph(session, governance, VENDOR, find(session, VENDOR, shelf.vendor))
        assert {n["ref"] for n in down["nodes"] if n["side"] == "downstream"} == {
            shelf.base, shelf.tuned, shelf.system
        }  # fmt: skip
        assert (
            links.graph(session, governance, MODEL, find(session, MODEL, shelf.base))["hidden"] == 0
        )
    client = as_role("member")
    over = client.get(f"/api/v1/records/{shelf.tuned}/graph", params={"depth": 2}).json()["data"]
    assert over["depth"] == 2 and len(over["nodes"]) == 5
    assert client.get("/api/v1/records/MDL-9999/graph").status_code == 404
