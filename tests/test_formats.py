"""Open formats and the transparency register."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from govwren.cli import main
from govwren.core.errors import Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.insight import formats, register
from govwren.inventory import links, records
from govwren.inventory.registry import DATASET, MODEL, USE_CASE, find
from tests.conftest import Instance
from tests.people import People
from tests.test_changes import linked
from tests.test_review import HIGH, MONDAY, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
SUM = "ab" * 32


def _described(db: Database, people: People) -> tuple[str, str, str]:
    """The linked use, with its model described and trained on a dataset."""
    use, _system, model = linked(db, people)
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        found = find(session, MODEL, model)
        records.update(
            session, governance, MODEL, found,
            {"version_label": "2.1", "license": "Apache-2.0", "provider": "Lumen Labs",
             "weights_checksum": f"sha256:{SUM}", "intended_use": "Drafting and summarizing.",
             "limitations": "It can state things that are not so.", "family": "Lumen",
             "summary": "A general language model."},
            version=found.version,
        )  # fmt: skip
        dataset = records.create(
            session, governance, DATASET, {"name": "Lab notes corpus", "data_class": "internal"}
        )
        links.add(session, governance, model, "trained_on", dataset.ref)
        return use, model, dataset.ref


def test_the_models_as_a_bill_of_materials(db: Database, people: People) -> None:
    _use, model, dataset = _described(db, people)
    with db.read() as session:
        bom = formats.bill_of_materials(session, who(db, people, "governance"))
    assert (bom["bomFormat"], bom["specVersion"]) == ("CycloneDX", "1.6")
    assert bom["serialNumber"].startswith("urn:uuid:") and bom["version"] == 1
    lumen, data = bom["components"]
    assert lumen["type"] == "machine-learning-model" and lumen["bom-ref"] == model
    assert (lumen["name"], lumen["version"]) == ("Lumen Large", "2.1")
    assert lumen["supplier"] == {"name": "Lumen Labs"}
    assert lumen["licenses"] == [{"license": {"name": "Apache-2.0"}}]
    assert lumen["hashes"] == [{"alg": "SHA-256", "content": SUM}]
    card = lumen["modelCard"]
    assert card["modelParameters"]["datasets"] == [{"ref": dataset}]
    assert card["modelParameters"]["architectureFamily"] == "Lumen"
    assert card["considerations"]["useCases"] == ["Drafting and summarizing."]
    assert data["type"] == "data" and data["bom-ref"] == dataset
    assert {"ref": model, "dependsOn": [dataset]} in bom["dependencies"]
    assert bom["dependencies"][0] == {"ref": "inventory", "dependsOn": [model]}


def test_a_model_card(db: Database, people: People) -> None:
    _use, model, dataset = _described(db, people)
    with db.read() as session:
        text = formats.model_card(
            session, who(db, people, "governance"), find(session, MODEL, model)
        )
    assert text.startswith("# Lumen Large\n\nA general language model.\n\n## Model details\n")
    assert "| License | Apache-2.0 |" in text and "| Version | 2.1 |" in text
    assert "## Intended use\n\nDrafting and summarizing.\n" in text
    assert f"- Trained on: Lab notes corpus ({dataset})" in text
    assert "## Evaluation" not in text  # nothing was written under it


def test_the_register_is_chosen_and_published(
    instance: Instance, db: Database, people: People, tmp_path: Path
) -> None:
    use, _model, _dataset = _described(db, people)
    with frozen_ok():
        waiting = request(db, people, HIGH)
    governance, auditor = who(db, people, "governance"), who(db, people, "auditor")
    words = {
        "title": "Summarizing lab meetings",
        "description": "Notes are summarized.\n\nA person checks them.",
    }
    with db.write(governance.actor) as session:
        found = find(session, USE_CASE, use)
        with pytest.raises(PermissionDenied):
            register.put(session, auditor, found, words)
        with pytest.raises(Invalid) as refused:
            register.put(session, governance, found, {"title": "", "description": ""})
        assert set(refused.value.errors) == {"title", "description"}
        from tests.test_changes import use_case_of

        with pytest.raises(Invalid) as early:  # still in review
            register.put(session, governance, use_case_of(session, waiting), words)
        assert "ref" in early.value.errors
        with pytest.raises(NotFound):
            register.remove(session, governance, found)
        register.put(session, governance, found, words)
        register.put(
            session, governance, found, {**words, "title": "Summarizing lab meeting notes"}
        )
    with db.read() as session:
        listed = register.listing(session, auditor)
        assert listed["published"] == 1 and not listed["can_change"]
        entry = listed["entries"][0]
        assert (entry["ref"], entry["title"]) == (use, "Summarizing lab meeting notes")
        assert entry["tools"] == ["Lumen Assistant"] and entry["unit"] == "Hale Lab"
        files = register.pages(session)
        assert set(files) == {"index.html", "style.css", f"{use.lower()}.html"}
        index, page = files["index.html"].decode(), files[f"{use.lower()}.html"].decode()
        assert "the one use" in index and f'href="{use.lower()}.html"' in index
        assert "<h1>Summarizing lab meeting notes</h1>" in page
        assert "<p>Notes are summarized.</p><p>A person checks them.</p>" in page
        assert "Lumen Assistant" in page and "Hale Lab" in page and "<script" not in page
        names = zipfile.ZipFile(io.BytesIO(register.archive(session))).namelist()
        assert "register/index.html" in names
    out = tmp_path / "public"
    out.mkdir()
    (out / "uc-9999.html").write_text("stale")
    assert main(["--config", str(instance.path), "register", "build", "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "index.html",
        "style.css",
        f"{use.lower()}.html",
    ]
    with db.write(governance.actor) as session:
        register.remove(session, governance, find(session, USE_CASE, use))
    with db.read() as session:
        assert b"Nothing has been published" in register.pages(session)["index.html"]


def frozen_ok():  # type: ignore[no-untyped-def]
    from govwren.core.clock import frozen_at

    return frozen_at(MONDAY)


def test_over_the_api(as_role: Clients, db: Database, people: People) -> None:
    use, model, _dataset = _described(db, people)
    governance, auditor, member = as_role("governance"), as_role("auditor"), as_role("member")
    bom = member.get("/api/v1/bill-of-materials")
    assert bom.status_code == 200 and bom.json()["bomFormat"] == "CycloneDX"
    assert bom.headers["content-type"] == "application/vnd.cyclonedx+json"
    card = member.get(f"/api/v1/models/{model}/card")
    assert card.status_code == 200 and card.text.startswith("# Lumen Large")
    assert card.headers["content-disposition"] == f'attachment; filename="{model}-model-card.md"'
    body = {"title": "Summaries", "description": "Notes are summarized.", "show_unit": False}
    assert auditor.put(f"/api/v1/use-cases/{use}/register", json=body).status_code == 403
    put = governance.put(f"/api/v1/use-cases/{use}/register", json=body)
    assert put.status_code == 200 and put.json()["data"]["published"] == 1
    assert auditor.get("/api/v1/register").json()["data"]["entries"][0]["show_unit"] is False
    pages = auditor.get("/api/v1/register/pages")
    assert pages.status_code == 200 and pages.headers["content-type"] == "application/zip"
    page = zipfile.ZipFile(io.BytesIO(pages.content)).read(f"register/{use.lower()}.html").decode()
    assert "Hale Lab" not in page and "Summaries" in page
    shown = auditor.get("/api/v1/register/preview/index.html")
    assert shown.status_code == 200 and "How we use AI" in shown.text
    assert (
        auditor.get("/api/v1/register/preview/style.css")
        .headers["content-type"]
        .startswith("text/css")
    )
    assert auditor.get("/api/v1/register/preview/nothing.html").status_code == 404
    assert member.get("/api/v1/register").status_code == 403
    gone = governance.delete(f"/api/v1/use-cases/{use}/register")
    assert gone.status_code == 200 and gone.json()["data"]["entries"] == []
