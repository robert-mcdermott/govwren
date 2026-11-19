"""One search across everything, saved views, completeness, duplicates, and merging."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren import reporting
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import AISystem, RecordMerge
from govwren.evidence import service as evidence
from govwren.inventory import agreements, history, links, records, tidy
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, USE_CASE, VENDOR, find
from tests.people import People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


@pytest.fixture
def stock(db: Database, people: People) -> dict[str, str]:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    refs: dict[str, str] = {}
    with db.write(governance.actor) as session:
        refs["vendor"] = records.create(session, governance, VENDOR, {"name": "Brightfen Labs"}).ref
        refs["twin"] = records.create(
            session, governance, VENDOR, {"name": "Brightfen Labs, Inc."}
        ).ref
        refs["assistant"] = records.create(
            session, governance, SYSTEM,
            {"name": "Brightfen Assistant", "kind": "vendor_product", "vendor": refs["twin"],
             "edition": "Enterprise", "catalog_status": "approved",
             "permitted_data_class": "protected"},
        ).ref  # fmt: skip
        refs["free"] = records.create(
            session,
            governance,
            SYSTEM,
            {"name": "Brightfen Assistant", "kind": "vendor_product", "edition": "Free"},
        ).ref
        refs["secret"] = records.create(
            session,
            governance,
            DATASET,
            {"name": "Brightfen pilot transcripts", "data_class": "restricted", "restricted": True},
        ).ref
    with db.write(member.actor) as session:
        refs["again"] = records.create(
            session, member, SYSTEM,
            {"name": "brightfen assistant ", "kind": "vendor_product", "edition": "enterprise",
             "summary": "The chat assistant our lab uses."},
        ).ref  # fmt: skip
        refs["model"] = records.create(
            session,
            member,
            MODEL,
            {"name": "Sleep notes model", "kind": "language", "origin": "fine_tuned"},
        ).ref
        refs["data"] = records.create(
            session,
            member,
            DATASET,
            {"name": "Sleep cohort recordings", "data_class": "restricted"},
        ).ref
    return refs


def test_one_search_finds_every_kind_and_only_what_may_be_seen(
    db: Database, people: People, stock: dict[str, str]
) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.read() as session:
        found = tidy.everything(session, member, "brightfen")
        assert {hit["type"] for hit in found} == {"system", "vendor"}
        assert stock["secret"] not in {hit["ref"] for hit in found}
        assert stock["secret"] in {
            hit["ref"] for hit in tidy.everything(session, governance, "brightfen")
        }
        exact = tidy.everything(session, member, stock["model"].lower())
        assert exact[0]["ref"] == stock["model"] and exact[0]["exact"]
        assert exact[0]["href"] == f"/models/{stock['model']}"
        assert tidy.everything(session, member, "b") == []
        assert tidy.everything(session, member, stock["secret"]) == []
        assert [hit["type"] for hit in tidy.everything(session, member, "sleep")] == [
            "model",
            "dataset",
        ]


def test_views_are_kept_by_name_for_one_person(db: Database, people: People) -> None:
    member, other = who(db, people, "member"), who(db, people, "steward")
    with db.bookkeeping() as session:
        saved = tidy.save_view(session, member, "use_case", "  High and mine ", {
            "tier": "3", "mine": "true", "cursor": "abc", "q": "", "sort": "-updated_at",
            "<bad>": "x"})  # fmt: skip
        assert saved["name"] == "High and mine"
        assert saved["params"] == {"tier": "3", "mine": "true", "sort": "-updated_at"}
        again = tidy.save_view(session, member, "use_case", "High and mine", {"tier": "4"})
        assert again["id"] == saved["id"] and again["params"] == {"tier": "4"}
        tidy.save_view(session, member, "model", "Open weights", {"origin": "open_weights"})
        assert [v["name"] for v in tidy.views(session, member)] == ["Open weights", "High and mine"]
        assert [v["name"] for v in tidy.views(session, member, "model")] == ["Open weights"]
        assert tidy.views(session, other) == []
        for bad in (("moods", "x", {"a": "b"}), ("model", " ", {"a": "b"}), ("model", "x", {})):
            with pytest.raises(Invalid):
                tidy.save_view(session, member, *bad)
        with pytest.raises(NotFound):
            tidy.remove_view(session, other, saved["id"])
        tidy.remove_view(session, member, saved["id"])
        assert len(tidy.views(session, member)) == 1


def test_each_record_says_what_it_is_missing(
    db: Database, people: People, stock: dict[str, str]
) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(member.actor) as session:
        model = find(session, MODEL, stock["model"])
        before = tidy.completeness(session, MODEL, model)
        missing = {item["field"] for item in before["missing"]}
        assert {
            "version_label",
            "intended_use",
            "weights_checksum",
            "trained_on",
            "derived_from",
        } <= missing
        assert "owners" not in missing and "provider" not in missing and before["score"] < 50
        records.update(session, member, MODEL, model, {
            "version_label": "0.3", "intended_use": "Research in the lab.", "license": "Apache-2.0",
            "weights_source": "Trained here", "weights_checksum": "sha256:ab12",
            "weights_format": "safetensors", "runs_on": "A lab workstation."},
            version=model.version)  # fmt: skip
        links.add(session, member, stock["model"], "trained_on", stock["data"])
        after = tidy.completeness(session, MODEL, model)
        assert [item["field"] for item in after["missing"]] == ["derived_from"]
        assert after["score"] > before["score"]
        assert records.detail(session, member, MODEL, model)["completeness"] == after
    with db.write(governance.actor) as session:
        vendor = find(session, VENDOR, stock["vendor"])
        assert {i["field"] for i in tidy.completeness(session, VENDOR, vendor)["missing"]} == {
            "website",
            "contacts",
        }
        records.update(
            session, governance, VENDOR, vendor, {"status": "active"}, version=vendor.version
        )
        assert "agreements" in {
            i["field"] for i in tidy.completeness(session, VENDOR, vendor)["missing"]
        }
        agreements.create(
            session, governance, vendor, {"kind": "master", "title": "Master agreement"}
        )
        assert "agreements" not in {
            i["field"] for i in tidy.completeness(session, VENDOR, vendor)["missing"]
        }
        by_type = {row["type"]: row for row in tidy.completeness_by_type(session)}
        assert by_type["model"]["records"] == 1 and by_type["system"]["records"] == 3
        assert by_type["use_case"]["average"] is None
        assert reporting.dashboard(session)["completeness"] == tidy.completeness_by_type(session)


def test_likely_duplicates_are_found_and_editions_are_not_confused(
    db: Database, people: People, stock: dict[str, str]
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.read() as session:
        systems = tidy.duplicates(session, governance, SYSTEM)
        assert [sorted(r["ref"] for r in pair["records"]) for pair in systems] == [
            sorted([stock["assistant"], stock["again"]])
        ]  # the Free edition is a different system
        vendors = tidy.duplicates(session, governance, VENDOR)
        assert {r["ref"] for r in vendors[0]["records"]} == {stock["vendor"], stock["twin"]}
        assert vendors[0]["score"] == 1.0
        assert tidy.duplicates(session, governance, MODEL) == []
        with pytest.raises(PermissionDenied):
            tidy.duplicates(session, member, SYSTEM)
        with pytest.raises(Invalid):
            tidy.duplicates(session, governance, USE_CASE)


def test_a_merge_moves_everything_and_keeps_the_old_reference_working(
    db: Database, people: People, stock: dict[str, str]
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(member.actor) as session:
        again = find(session, SYSTEM, stock["again"])
        links.add(session, member, stock["again"], "built_on", stock["model"])
        links.set_references(
            session, member, SYSTEM, again, [{"kind": "ticket", "identifier": "T-204"}]
        )
        evidence.create(session, member, {"title": "Security checklist", "kind": "record",
                                          "description": "Completed.",
                                          "supports": [stock["again"]]})  # fmt: skip
        records.set_owners(session, member, SYSTEM, again, [
            {"account_id": people.accounts["member"], "kind": "accountable"},
            {"account_id": people.accounts["steward"], "kind": "technical"}])  # fmt: skip
        with pytest.raises(PermissionDenied):
            tidy.merge(session, member, SYSTEM, again, find(session, SYSTEM, stock["assistant"]))
    with db.write(governance.actor) as session:
        again, keep = (
            find(session, SYSTEM, stock["again"]),
            find(session, SYSTEM, stock["assistant"]),
        )
        with pytest.raises(Invalid):
            tidy.merge(session, governance, SYSTEM, keep, keep)
        tidy.merge(session, governance, SYSTEM, again, keep)
        assert again.status == "retired" and tidy.merged_into(session, SYSTEM, again) == keep.ref
        assert tidy.resolve(session, SYSTEM, stock["again"]).ref == keep.ref
        seen = records.detail(session, governance, SYSTEM, keep)
        assert [(e["label"], e["record"]["ref"]) for e in seen["links"]["outgoing"]] == [
            ("Built on", stock["model"])
        ]
        assert [r["identifier"] for r in seen["references"]] == ["T-204"]
        assert [e["title"] for e in seen["evidence"]] == ["Security checklist"]
        kinds = {(o["account_id"], o["kind"]) for o in seen["owners"]}
        assert (people.accounts["steward"], "technical") in kinds  # helpers come along
        assert (people.accounts["member"], "accountable") not in kinds  # the owner of record stays
        old = records.detail(session, governance, SYSTEM, again)
        assert old["merged_into"] == keep.ref and old["links"]["outgoing"] == []
        with pytest.raises(Conflict):
            tidy.merge(session, governance, SYSTEM, again, find(session, SYSTEM, stock["free"]))
        assert tidy.duplicates(session, governance, SYSTEM) == []
        assert tidy.everything(session, governance, stock["again"])[0]["ref"] == keep.ref
        titles = [e["title"] for e in history.for_record(session, SYSTEM, keep, internal=True)]
        assert any("Merged" in title and stock["again"] in title for title in titles)
        # A vendor's systems and agreements follow it.
        twin, vendor = find(session, VENDOR, stock["twin"]), find(session, VENDOR, stock["vendor"])
        agreements.create(session, governance, twin, {"kind": "license", "title": "License"})
        tidy.merge(session, governance, VENDOR, twin, vendor)
        assert twin.status == "former"
        assert (
            session.scalars(select(AISystem.vendor_id).where(AISystem.id == keep.id)).one()
            == vendor.id
        )
        assert [a["title"] for a in agreements.of(session, vendor)] == ["License"]
        assert session.scalars(select(RecordMerge)).all()[1].from_ref == stock["twin"]


def test_over_the_api(as_role: Clients, stock: dict[str, str]) -> None:
    member, governance = as_role("member"), as_role("governance")
    hits = member.get("/api/v1/search", params={"q": "sleep"}).json()["data"]
    assert [hit["type"] for hit in hits] == ["model", "dataset"]
    saved = member.post(
        "/api/v1/views",
        json={"list": "model", "name": "Tuned here", "params": {"origin": "fine_tuned"}},
    )
    assert saved.status_code == 201
    assert (
        member.get("/api/v1/views", params={"list": "model"}).json()["data"][0]["name"]
        == "Tuned here"
    )
    assert governance.get("/api/v1/views").json()["data"] == []
    assert member.delete(f"/api/v1/views/{saved.json()['data']['id']}").status_code == 200
    assert member.get("/api/v1/duplicates").status_code == 403
    pairs = governance.get("/api/v1/duplicates", params={"type": "vendor"}).json()["data"]
    assert len(pairs) == 1
    wrong = governance.post(
        f"/api/v1/records/{stock['twin']}/merge", json={"into": stock["assistant"]}
    )
    assert wrong.status_code == 422
    done = governance.post(f"/api/v1/records/{stock['twin']}/merge", json={"into": stock["vendor"]})
    assert done.status_code == 200 and done.json()["data"]["ref"] == stock["vendor"]
    old = member.get(f"/api/v1/vendors/{stock['twin']}").json()["data"]
    assert old["merged_into"] == stock["vendor"] and old["status"] == "former"
    assert (
        member.get(f"/api/v1/models/{stock['model']}").json()["data"]["completeness"]["score"] < 100
    )
