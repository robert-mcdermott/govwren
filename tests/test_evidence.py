"""Evidence: files kept once by their content, and what each piece of evidence supports."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from govwren.core.clock import frozen_at
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Evidence, StoredFile
from govwren.evidence import files, service
from govwren.inventory import history, records
from govwren.inventory.registry import DATASET, find
from tests.conftest import Instance
from tests.people import People
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
NOW = datetime(2026, 11, 18, 12, tzinfo=UTC)


@pytest.fixture
def dataset(db: Database, people: People) -> str:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        made = records.create(
            session, member, DATASET,
            {"name": "Sleep cohort recordings", "data_class": "restricted",
             "org_unit_id": people.units["HALE"]},
        )  # fmt: skip
        return made.ref


@pytest.mark.parametrize(
    ("name", "data", "expected"),
    [
        ("approval.pdf", PDF, "application/pdf"),
        ("renamed.txt", PDF, "application/pdf"),  # judged by its content, not its name
        ("scan.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png"),
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"0" * 20, "image/jpeg"),
        ("plan.docx", b"PK\x03\x04" + b"0" * 20, files.OFFICE["docx"]),
        ("notes.md", b"Checked on the 4th.\n", "text/plain"),
        ("results.csv", b"id,score\n1,0.9\n", "text/csv"),
        ("page.html", b"<!doctype html><script>alert(1)</script>", None),
        ("page.txt", b"  <HTML><body>hello</body></html>", None),
        ("drawing.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", None),
        ("tool.exe", b"MZ\x90\x00" + b"0" * 20, None),
        ("run.txt", b"#!/bin/sh\nrm -rf /\n", None),
        ("archive.docx", b"\x00\x01binary", None),
        ("unknown", b"just words", None),
    ],
)
def test_a_file_is_judged_by_what_is_in_it(name: str, data: bytes, expected: str | None) -> None:
    assert files.sniff(data, name) == expected


def test_the_same_content_is_kept_once(instance: Instance, db: Database, people: People) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        first = files.store(session, instance.home.files, PDF, "approval.pdf")
        second = files.store(session, instance.home.files, PDF, "the same thing.pdf")
        assert first.id == second.id and first.sha256 == hashlib.sha256(PDF).hexdigest()
        assert session.execute(select(func.count()).select_from(StoredFile)).scalar_one() == 1
        kept = files.path_of(instance.home.files, first.sha256)
        assert kept.read_bytes() == PDF and len(list(instance.home.files.rglob("*"))) == 3
        assert files.read(instance.home.files, first) == PDF
        kept.write_bytes(PDF + b"tampered")
        with pytest.raises(Invalid):  # what comes back is checked against its name
            files.read(instance.home.files, first)
        for bad in (b"", b"<html>", b"x" * (files.MAX_BYTES + 1)):
            with pytest.raises(Invalid):
                files.store(session, instance.home.files, bad, "notes.txt")
    assert files.clean_name("../../etc/pass\x00wd") == "passwd"
    assert files.clean_name('C:\\Users\\me\\"report".pdf') == "report.pdf"


def test_evidence_says_what_it_is_and_what_it_supports(
    instance: Instance, db: Database, people: People, dataset: str
) -> None:
    member, other = who(db, people, "member"), who(db, people, "steward")
    with frozen_at(NOW), db.write(member.actor) as session:
        stored = files.store(session, instance.home.files, PDF, "agreement.pdf")
        made = service.create(session, member, {
            "title": "Data use agreement, signed", "kind": "agreement", "file_id": stored.id,
            "file_name": "../agreement.pdf", "dated_on": "2026-01-10", "expires_on": "2026-12-20",
            "supports": [dataset]})  # fmt: skip
        assert made.ref == "EV-0001" and made.file_name == "agreement.pdf"
        assert made.file_sha256 == stored.sha256 and made.owner_id == member.account_id
        seen = service.view(session, member, made)
        assert seen["state"] == "expiring" and seen["days_left"] == 32
        assert seen["supports"] == [
            {"type": "dataset", "ref": dataset, "name": "Sleep cohort recordings"}
        ]
        assert seen["file"]["href"] == "/api/v1/evidence/EV-0001/file" and seen["can"]["edit"]
        record = find(session, DATASET, dataset)
        assert [e["ref"] for e in records.detail(session, member, DATASET, record)["evidence"]] == [
            "EV-0001"
        ]
        note = service.create(session, member, {
            "title": "Checked with the data office", "kind": "record",
            "description": "They confirmed it matches.", "supports": [dataset]})  # fmt: skip
        assert service.view(session, member, note)["state"] == "current"
        for bad, field in [
            ({"title": "", "kind": "record", "description": "x", "supports": [dataset]}, "title"),
            ({"title": "x", "kind": "vibes", "description": "x", "supports": [dataset]}, "kind"),
            ({"title": "x", "kind": "record", "supports": [dataset]}, "file"),
            ({"title": "x", "kind": "record", "url": "ftp://x", "supports": [dataset]}, "url"),
            ({"title": "x", "kind": "record", "description": "x"}, "supports"),
            ({"title": "x", "kind": "record", "description": "x", "dated_on": "2026-05-01",
              "expires_on": "2026-04-01", "supports": [dataset]}, "expires_on"),
        ]:  # fmt: skip
            with pytest.raises(Invalid) as caught:
                service.create(session, member, bad)
            assert field in caught.value.errors
        with pytest.raises(NotFound):
            service.create(
                session,
                member,
                {"title": "x", "kind": "record", "description": "x", "supports": ["DS-9999"]},
            )
        service.update(session, member, made, {"expires_on": "2026-11-01"})
        assert service.state(made) == "expired"
        assert service.needing_attention(session) == 1
        service.update(session, member, made, {"status": "withdrawn"})
        assert service.state(made) == "withdrawn" and service.needing_attention(session) == 0
        titles = [e["title"] for e in history.for_record(session, DATASET, record, internal=True)]
        assert titles.count("Evidence attached: Data use agreement, signed (EV-0001)") == 1
    with db.write(other.actor) as session:  # a steward of the unit sees it and cannot change it
        found = service.find(session, other, "EV-0001")
        with pytest.raises(PermissionDenied):
            service.update(session, other, found, {"title": "Mine"})
    stranger = who(db, people, "reviewer")
    with db.write(stranger.actor) as session, pytest.raises(PermissionDenied):
        service.create(
            session,
            stranger,
            {"title": "x", "kind": "record", "description": "x", "supports": [dataset]},
        )


def test_who_lists_what(db: Database, people: People, dataset: str) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        for title in ("First note", "Second note"):
            service.create(
                session,
                member,
                {"title": title, "kind": "record", "description": "x", "supports": [dataset]},
            )
    with db.read() as session:
        mine, total = service.search(session, member, {})
        assert total == 2 and {e.title for e in mine} == {"First note", "Second note"}
        assert service.search(session, who(db, people, "reviewer"), {})[1] == 0
        assert service.search(session, who(db, people, "auditor"), {"q": "second"})[1] == 1
        assert service.search(session, member, {"state": "expired"})[1] == 0


def test_over_the_api_a_file_goes_up_and_comes_back_as_a_download(
    as_role: Clients, instance: Instance, dataset: str
) -> None:
    member = as_role("member")
    sent = member.post(
        "/api/v1/evidence/files", params={"name": "ethics approval.pdf"}, content=PDF
    )
    assert sent.status_code == 201
    stored = sent.json()["data"]
    assert stored["media_type"] == "application/pdf" and stored["size"] == len(PDF)
    refused = member.post("/api/v1/evidence/files", params={"name": "page.html"}, content=b"<html>")
    assert refused.status_code == 422
    assert [error["location"] for error in refused.json()["errors"]] == [["file"]]
    made = member.post("/api/v1/evidence", json={
        "title": "Ethics approval letter", "kind": "approval", "file_id": stored["file_id"],
        "file_name": stored["name"], "supports": [dataset]})  # fmt: skip
    assert made.status_code == 201
    ref = made.json()["data"]["ref"]
    got = member.get(f"/api/v1/evidence/{ref}/file")
    assert got.status_code == 200 and got.content == PDF
    assert got.headers["content-type"] == "application/pdf"
    assert got.headers["content-disposition"].startswith(
        'attachment; filename="ethics approval.pdf"'
    )
    assert (
        got.headers["x-content-type-options"] == "nosniff"
        and "sandbox" in got.headers["content-security-policy"]
    )
    assert member.get(f"/api/v1/datasets/{dataset}").json()["data"]["evidence"][0]["ref"] == ref
    assert member.get("/api/v1/evidence").json()["meta"]["total"] == 1
    reviewer = as_role(
        "reviewer"
    )  # not an owner, not in the unit, and the data is not theirs to read
    assert reviewer.get(f"/api/v1/evidence/{ref}").status_code == 200  # datasets are reference data
    assert reviewer.patch(f"/api/v1/evidence/{ref}", json={"title": "Mine"}).status_code == 403
    changed = member.patch(f"/api/v1/evidence/{ref}", json={"expires_on": "2030-01-01"})
    assert changed.json()["data"]["state"] == "current"
    assert len(list(Path(instance.home.files).rglob("*"))) == 3  # two directories and one file


def test_evidence_can_be_attached_when_a_condition_is_met(db: Database, people: People) -> None:
    from govwren.intake import service as intake
    from govwren.review import service as review
    from govwren.review import views
    from tests.test_review import MODERATE

    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(member.actor) as session:
        use_case = intake.start(session, member, {**MODERATE, "unit": people.units["HALE"]})
        intake.submit(session, member, use_case)
        ref = use_case.ref
    with db.write(governance.actor) as session:
        use_case = find(session, records.USE_CASE, ref)
        opened = review.latest_review(session, use_case)
        review.triage(session, governance, opened)
        review.decide(
            session, governance, opened, outcome="approved", rationale="Fine as described.",
            conditions=[{"template_key": "deidentify_first"}],
        )  # fmt: skip
        condition = review.conditions_of(session, use_case)[0]
        condition_id = condition.id
    with db.write(member.actor) as session:
        service.create(session, member, {"title": "De-identification procedure", "kind": "document",
                                         "description": "Section 4 of the lab manual.",
                                         "supports": [f"condition:{condition_id}"]})  # fmt: skip
        review.close_condition(
            session, member, condition_id, status="met", note="Procedure written and in use."
        )
    with db.read() as session:
        use_case = find(session, records.USE_CASE, ref)
        shown = views.review_summary(session, member, use_case)
        attached = shown["all_conditions"][0]["evidence"]
        assert [e["title"] for e in attached] == ["De-identification procedure"]
        assert attached[0]["supports"][0] == {
            "type": "condition", "id": condition_id, "ref": ref,
            "name": session.get(type(condition), condition_id).text[:120],
        }  # fmt: skip
        stranger = who(db, people, "reviewer")
        with pytest.raises(NotFound):
            service.find(session, stranger, attached[0]["ref"])
    _ = Evidence
