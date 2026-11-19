"""The dossier: one record's whole story as a package that can be checked."""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from govwren.cli import main
from govwren.core.errors import NotFound
from govwren.db.engine import Database
from govwren.evidence import files
from govwren.evidence import service as evidence
from govwren.insight import dossier
from govwren.inventory.registry import find_any
from tests.conftest import Instance
from tests.people import People
from tests.test_changes import linked
from tests.test_evidence import PDF
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")


def _with_evidence(instance: Instance, db: Database, people: People) -> str:
    use, _system, _model = linked(db, people)
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        stored = files.store(
            session, instance.home.files, PDF, "approval letter.pdf", member.account_id
        )
        evidence.create(session, member, {
            "title": "Approval letter", "kind": "approval", "file_id": stored.id,
            "file_name": "approval letter.pdf", "supports": [use]})  # fmt: skip
    return use


def _rezip(data: bytes, change: Callable[[dict[str, bytes]], None]) -> bytes:
    archive = zipfile.ZipFile(io.BytesIO(data))
    members = {name: archive.read(name) for name in archive.namelist()}
    change(members)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as again:
        for name, content in members.items():
            again.writestr(name, content)
    return out.getvalue()


def test_a_dossier_holds_the_whole_story(instance: Instance, db: Database, people: People) -> None:
    use = _with_evidence(instance, db, people)
    member, reviewer = who(db, people, "member"), who(db, people, "reviewer")
    with db.read() as session:
        document = dossier.build(session, member, *find_any(session, use))
        assert document["format"] == dossier.FORMAT and document["record"]["ref"] == use
        assert "can" not in document["record"]
        asked = [q["label"] for s in document["answers"]["sections"] for q in s["questions"]]
        assert "What will you use AI for?" in asked
        assert [r["kind"] for r in document["reviews"]] == ["initial"]
        assert document["reviews"][0]["decisions"][0]["by_rule"]
        assert [e["title"] for e in document["evidence"]] == ["Approval letter"]
        stamps = [entry["at"] for entry in document["history"]]
        assert stamps == sorted(stamps) and document["history"][0]["action"] == "created"
        assert document["history_head"]["events"] > 0
        json.dumps(document)  # nothing in it needs more than JSON
        page = dossier.page(document)
        assert "<h1>" in page and "Approval letter" in page and "<script" not in page
        with pytest.raises(NotFound):  # a summary of a record is not enough to take its dossier
            dossier.build(session, reviewer, *find_any(session, use))


def test_the_package_verifies_and_notices_tampering(
    instance: Instance, db: Database, people: People
) -> None:
    use = _with_evidence(instance, db, people)
    member = who(db, people, "member")
    with db.read() as session:
        document = dossier.build(session, member, *find_any(session, use))
        data = dossier.package(session, instance.home.files, document)
        assert data == dossier.package(session, instance.home.files, document)
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        letter = next(name for name in names if name.startswith("evidence/"))
        assert names == {"dossier.json", "dossier.html", "manifest.json", letter}
        assert archive.read(letter) == PDF and letter.endswith("approval letter.pdf")
        assert json.loads(archive.read("dossier.json"))["record"]["ref"] == use
        ok, lines = dossier.check(data, session)
        assert ok and "3 files match" in lines[0] and "matches" in lines[1]

        def alter(members: dict[str, bytes]) -> None:
            members[letter] = PDF + b" "

        def add(members: dict[str, bytes]) -> None:
            members["evidence/extra.txt"] = b"slipped in"

        def remove(members: dict[str, bytes]) -> None:
            del members["dossier.html"]

        def relist(members: dict[str, bytes]) -> None:  # change a file and its entry to match
            manifest = json.loads(members["manifest.json"])
            members["dossier.html"] = b"<p>Approved, honest.</p>"
            import hashlib

            for entry in manifest["files"]:
                if entry["path"] == "dossier.html":
                    entry["sha256"] = hashlib.sha256(members["dossier.html"]).hexdigest()
            members["manifest.json"] = json.dumps(manifest).encode()

        def elsewhere(members: dict[str, bytes]) -> None:
            manifest = json.loads(members["manifest.json"])
            manifest["history_head"]["hash"] = "0" * 64
            members["manifest.json"] = json.dumps(manifest).encode()

        for change, words in (
            (alter, "has been altered"),
            (add, "not in the manifest"),
            (remove, "not in the package"),
            (relist, "seal does not hold"),
            (elsewhere, "seal does not hold"),
        ):
            ok, lines = dossier.check(_rezip(data, change), session)
            assert not ok and any(words in line for line in lines), (change.__name__, lines)
        assert dossier.check(b"not a zip") == (
            False,
            ["This is not a dossier package: it has no manifest that can be read."],
        )


def test_a_file_missing_from_the_store_is_named_not_hidden(
    instance: Instance, db: Database, people: People
) -> None:
    use = _with_evidence(instance, db, people)
    for path in Path(instance.home.files).rglob("*"):
        if path.is_file():
            path.unlink()
    with db.read() as session:
        document = dossier.build(session, who(db, people, "member"), *find_any(session, use))
        data = dossier.package(session, instance.home.files, document)
        manifest = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("manifest.json"))
        assert [gone["path"] for gone in manifest["missing"]] == [
            "evidence/EV-0001-approval letter.pdf"
        ]
        ok, lines = dossier.check(data)
        assert ok and "was not in the file store" in lines[-1]


def test_over_the_api_and_from_the_command_line(
    as_role: Clients, instance: Instance, db: Database, people: People, tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:  # fmt: skip
    use = _with_evidence(instance, db, people)
    member = as_role("member")
    shown = member.get(f"/api/v1/records/{use}/dossier")
    assert shown.status_code == 200 and shown.json()["data"]["record"]["ref"] == use
    got = member.get(f"/api/v1/records/{use}/dossier/package")
    assert got.status_code == 200 and got.headers["content-type"] == "application/zip"
    assert got.headers["content-disposition"] == f'attachment; filename="{use}-dossier.zip"'
    assert dossier.check(got.content)[0]
    assert as_role("reviewer").get(f"/api/v1/records/{use}/dossier").status_code == 404
    assert as_role("auditor").get(f"/api/v1/records/{use}/dossier/package").status_code == 200

    out = tmp_path / "taken.zip"
    config = ["--config", str(instance.path)]
    assert main([*config, "dossier", "make", use, "--out", str(out)]) == 0
    assert "1 pieces of evidence" in capsys.readouterr().out
    assert main(["dossier", "verify", str(out)]) == 0
    assert main([*config, "dossier", "verify", str(out), "--history"]) == 0
    assert "history matches" in capsys.readouterr().out
    out.write_bytes(_rezip(out.read_bytes(), lambda members: members.pop("dossier.json")))
    assert main(["dossier", "verify", str(out)]) == 1
    assert "not in the package" in capsys.readouterr().err
