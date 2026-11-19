"""Importing records from a spreadsheet, and exporting lists."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import AISystem, Event, Vendor
from govwren.inventory import imports, records
from govwren.inventory.registry import DATASET, MODEL, SYSTEM, USE_CASE, VENDOR, find
from tests.people import People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")

VENDORS = """Supplier,Web site,Standing
Brightfen Labs,https://brightfen.example,Active
Quillstream,https://quillstream.example,prospective
"""
SYSTEMS = """Tool,Supplier,Plan,Type,Hosting,Data classification,Not for,Trains on inputs,Owner email,Department,Notes
Brightfen Assistant,Brightfen Labs,Enterprise,Vendor product,Hosted by the vendor,Protected,Health information; credentials,no,member@alderpoint.example,HALE,ignored
Brightfen Assistant,brightfen labs,Free,vendor_product,vendor,,,yes,,,
Scribe Notebook,,,Open-source tool,On a person's own device,,,,,Hale Lab,
"""


def test_columns_are_matched_by_name_and_the_guess_can_be_corrected() -> None:
    headers = next(csv.reader(io.StringIO(SYSTEMS)))
    guess = imports.suggest(headers, imports.columns(SYSTEM))
    assert guess == {
        "Tool": "", "Supplier": "vendor", "Plan": "edition", "Type": "kind", "Hosting": "hosting",
        "Data classification": "", "Not for": "", "Trains on inputs": "trains_on_inputs",
        "Owner email": "owner",
        "Department": "unit", "Notes": "",
    }  # fmt: skip
    assert {c.key for c in imports.columns(MODEL)} >= {
        "origin",
        "weights_checksum",
        "vendor",
        "owner",
    }
    assert "vendor" not in {c.key for c in imports.columns(DATASET)}
    with pytest.raises(Invalid):
        imports.columns(USE_CASE)


MAPPING = {
    "Tool": "name", "Supplier": "vendor", "Plan": "edition", "Type": "kind", "Hosting": "hosting",
    "Data classification": "permitted_data_class", "Not for": "excluded_data_categories",
    "Trains on inputs": "trains_on_inputs", "Owner email": "owner", "Department": "unit", "Notes": "",
}  # fmt: skip


def test_a_dry_run_reports_and_changes_nothing_then_the_import_does_it(
    db: Database, people: People
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(member.actor) as session, pytest.raises(PermissionDenied):
        imports.run(session, member, VENDOR, VENDORS)
    with db.write(governance.actor) as session:
        first = imports.run(session, governance, VENDOR, VENDORS, dry_run=True)
        assert first.mapping == {"Supplier": "", "Web site": "", "Standing": "status"}
        assert [p["message"] for p in first.problems] == [
            "No column is mapped to Name. Every record needs a name."
        ]
        session.rollback()
    names = {"Supplier": "name", "Web site": "website", "Standing": "status"}
    with db.write(governance.actor) as session:
        dry = imports.run(session, governance, VENDOR, VENDORS, mapping=names, dry_run=True)
        assert (dry.rows, dry.created, dry.problems) == (2, 2, []) and not dry.applied
        session.rollback()
    with db.read() as session:
        assert session.execute(select(func.count()).select_from(Vendor)).scalar_one() == 0
        events = session.execute(select(func.count()).select_from(Event)).scalar_one()
    with db.write(governance.actor) as session:
        done = imports.run(session, governance, VENDOR, VENDORS, mapping=names, dry_run=False)
        assert done.applied and done.created == 2
    with db.write(governance.actor) as session:
        missing = imports.run(session, governance, SYSTEM, SYSTEMS, mapping=MAPPING, dry_run=False)
        assert missing.applied and (missing.created, missing.updated) == (3, 0)
    with db.read() as session:
        assert session.execute(select(func.count()).select_from(Event)).scalar_one() > events
        assistant = session.scalars(
            select(AISystem).where(
                AISystem.name == "Brightfen Assistant", AISystem.edition == "Enterprise"
            )
        ).one()
        seen = records.detail(session, governance, SYSTEM, assistant)
        assert seen["vendor"]["name"] == "Brightfen Labs" and seen["hosting"] == "vendor"
        assert seen["permitted_data_class"] == "protected"
        assert seen["excluded_data_categories"] == ["health", "credentials"]
        assert seen["data_handling"]["trains_on_inputs"] == "no"
        assert seen["org_unit_id"] == people.units["HALE"]
        assert [o["account_id"] for o in seen["owners"]] == [people.accounts["member"]]
        notebook = session.scalars(select(AISystem).where(AISystem.name == "Scribe Notebook")).one()
        assert notebook.kind == "open_source" and notebook.org_unit_id == people.units["HALE"]
    # Running it again changes nothing, and a changed cell changes one record.
    with db.write(governance.actor) as session:
        again = imports.run(session, governance, SYSTEM, SYSTEMS, mapping=MAPPING, dry_run=False)
        assert (again.created, again.updated, again.unchanged) == (0, 0, 3)
        edited = SYSTEMS.replace("Hosted by the vendor,Protected", "Hosted by the vendor,Internal")
        changed = imports.run(session, governance, SYSTEM, edited, mapping=MAPPING, dry_run=False)
        assert (changed.created, changed.updated, changed.unchanged) == (0, 1, 2)


def test_every_problem_is_reported_with_its_row_and_nothing_is_kept(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    bad = """name,kind,vendor,hosting,permitted_data_class,catalog_status,owner,unit,url
Good Tool,internal_app,,,,,,,
Good Tool,internal_app,,,,,,,
,agent,,,,,,,
Odd Kind,spaceship,,,,,,,
No Vendor,vendor_product,Nobody Inc,,,,,,
No Owner,internal_app,,,,,ghost@alderpoint.example,Mars,
Approved With Nothing,internal_app,,,,approved,,,
Bad Address,internal_app,,,,,,,not-a-url
"""
    with db.write(governance.actor) as session:
        report = imports.run(session, governance, SYSTEM, bad, dry_run=False)
        found = {(p["row"], p["message"]) for p in report.problems}
        assert (3, "This is the same record as row 2.") in found
        assert (4, "This row has no name.") in found
        assert (5, "Kind: 'spaceship' is not one of the choices.") in found
        assert (6, "There is no vendor called Nobody Inc. Import vendors first.") in found
        assert (7, "There is no account for ghost@alderpoint.example.") in found
        assert (7, "There is no unit called Mars.") in found
        assert any(row == 8 and "May be used with" in message for row, message in found)
        assert any(row == 9 and "https://" in message for row, message in found)
        assert not report.applied and report.created == 1
        session.rollback()
    with db.read() as session:
        assert session.execute(select(func.count()).select_from(AISystem)).scalar_one() == 0
    with db.write(governance.actor) as session:
        for text, mapping in (
            ("", None),
            ("a,b\n1,2\n", {"a": "name", "b": "name"}),
            ("a\n1\n", {"a": "colour"}),
        ):
            with pytest.raises(Invalid):
                imports.run(session, governance, SYSTEM, text, mapping=mapping)
        empty = imports.run(session, governance, SYSTEM, "name,kind\n")
        assert empty.problems[0]["message"] == "The file has a header and no rows."


def test_a_list_exports_what_the_person_may_see_and_comes_back_in(
    db: Database, people: People, as_role: Clients
) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        imports.run(session, governance, VENDOR, VENDORS, dry_run=False,
                    mapping={"Supplier": "name", "Web site": "website", "Standing": "status"})  # fmt: skip
        imports.run(session, governance, SYSTEM, SYSTEMS, mapping=MAPPING, dry_run=False)
        records.create(
            session,
            governance,
            SYSTEM,
            {"name": "=HYPERLINK(1)", "kind": "agent", "restricted": True},
        )
    member = as_role("member")
    got = member.get("/api/v1/exports/systems", params={"q": "brightfen", "format": "csv"})
    assert got.status_code == 200 and got.headers["content-type"].startswith("text/csv")
    assert 'filename="govwren-systems-' in got.headers["content-disposition"]
    lines = got.text.splitlines()
    assert (
        lines[0].startswith("# GovWren export: 2 AI systems") and "filters: q=brightfen" in lines[0]
    )
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[1:]))))
    rows.sort(key=lambda row: row["edition"])
    assert [row["edition"] for row in rows] == ["Enterprise", "Free"]
    assert rows[0]["vendor"].startswith("Brightfen Labs (VND-") and rows[0]["unit"] == "Hale Lab"
    assert rows[0]["owners"] == "Member Person <member@alderpoint.example>"
    assert rows[0]["excluded_data_categories"] == "health; credentials"
    everything = member.get("/api/v1/exports/systems", params={"format": "json"}).json()
    assert (
        len(everything["records"]) == 3 and everything["filters"] == {}
    )  # the restricted one is not theirs
    with_formula = as_role("governance").get("/api/v1/exports/systems").text
    assert "'=HYPERLINK(1)" in with_formula  # never handed to a spreadsheet as a formula
    assert member.get("/api/v1/exports/systems", params={"format": "xml"}).status_code == 422
    assert member.get("/api/v1/exports/moods").status_code == 404
    # What was exported can be imported again, comment line and all.
    with db.write(governance.actor) as session:
        back = imports.run(session, governance, SYSTEM, got.text, dry_run=True, mapping={
            "ref": "ref", "name": "name", "edition": "edition", "kind": "kind", "hosting": "hosting"})  # fmt: skip
        assert (back.rows, back.problems, back.unchanged) == (2, [], 2)
        session.rollback()
    _ = (json, find)


def test_import_over_the_api(as_role: Clients) -> None:
    governance = as_role("governance")
    look = governance.post("/api/v1/imports/records/vendors", content=VENDORS)
    assert look.status_code == 200
    data = look.json()["data"]
    assert data["headers"] == ["Supplier", "Web site", "Standing"] and data["dry_run"]
    assert {"key": "name", "label": "Name", "required": True} in data["fields"]
    mapping = json.dumps({"Supplier": "name", "Web site": "website", "Standing": "status"})
    done = governance.post(
        "/api/v1/imports/records/vendors",
        params={"dry_run": "false", "mapping": mapping},
        content=VENDORS,
    )
    assert done.json()["data"]["applied"] and done.json()["data"]["created"] == 2
    assert governance.get("/api/v1/vendors").json()["meta"]["total"] == 2
    assert (
        governance.post("/api/v1/imports/records/use-cases", content="name\nx\n").status_code == 422
    )
    assert (
        governance.post(
            "/api/v1/imports/records/vendors", params={"mapping": "{"}, content=VENDORS
        ).status_code
        == 422
    )
    assert (
        as_role("member").post("/api/v1/imports/records/vendors", content=VENDORS).status_code
        == 403
    )
