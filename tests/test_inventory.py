"""The inventory: records, owners, links, who sees what, and the readable history."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.access.principal import Principal
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import Event
from govwren.inventory import access, history, records
from govwren.inventory.registry import SYSTEM, USE_CASE, VENDOR, find
from govwren.people import accounts
from govwren.program import settings, vocab
from tests.people import ME, ROLES, People

Clients = Callable[[str | None], TestClient]


def who(db: Database, people: People, role: str) -> Principal:
    with db.read() as session:
        return accounts.principal_for(session, accounts.get(session, people.accounts[role]))


@dataclass
class Stock:
    vendor: str
    assistant: str  # an approved catalog system
    notebook: str  # a system a member added, not in the catalog
    draft: str  # the member's draft, in the Hale Lab
    hale: str  # approved, in the Hale Lab
    cancer: str  # approved, in Cancer Biology
    pending: str  # submitted, in Cancer Biology
    secret: str  # approved and restricted, in Cancer Biology


@pytest.fixture
def stock(db: Database, people: People) -> Stock:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(ME.actor) as session:
        vendor = records.create(
            session, governance, VENDOR, {"name": "Lumen Labs", "website": "https://lumen.example"}
        )
        assistant = records.create(
            session,
            governance,
            SYSTEM,
            {
                "name": "Lumen Assistant",
                "kind": "vendor_product",
                "vendor": vendor.ref,
                "edition": "Enterprise",
                "catalog_status": "approved",
                "permitted_data_class": "protected",
            },
        )
        notebook = records.create(
            session, member, SYSTEM, {"name": "Scribe Notebook", "kind": "open_source"}
        )

        def use_case(by: Principal, name: str, unit: str, status: str, **more: object) -> str:
            record = records.create(
                session, by, USE_CASE, {"name": name, "org_unit_id": people.units[unit], **more}
            )
            record.status = status  # the workflow that sets this arrives with intake and review
            return record.ref

        return Stock(
            vendor=vendor.ref,
            assistant=assistant.ref,
            notebook=notebook.ref,
            draft=use_case(member, "Summarize lab meeting notes", "HALE", "draft"),
            hale=use_case(
                member,
                "Draft methods sections",
                "HALE",
                "approved",
                purpose="Drafting",
                data_class="internal",
            ),
            cancer=use_case(
                governance,
                "Screen abstracts",
                "CANCER",
                "approved",
                purpose="Screening",
                data_class="protected",
                human_oversight="A person reads every result",
            ),
            pending=use_case(governance, "Triage imaging requests", "CANCER", "submitted"),
            secret=use_case(governance, "Sensitive pilot", "CANCER", "approved", restricted=True),
        )


def test_vocabularies_have_defaults_and_keep_their_order(db: Database) -> None:
    with db.write(ME.actor) as session:
        assert vocab.keys(session, "data_classes") == [
            "public",
            "internal",
            "protected",
            "restricted",
        ]
        assert vocab.rank(session, "data_classes", "restricted") > vocab.rank(
            session, "data_classes", "internal"
        )
        assert vocab.rank(session, "data_classes", "secret") == -1
        protected = vocab.get(session, "data_classes")[2]
        assert set(protected["examples"]) == {
            "Personal",
            "Research",
            "Health",
            "Financial",
            "Administrative",
        }
        assert set(vocab.all_(session)) == set(vocab.NAMES)
        domains = vocab.get(session, "domains")
        domains[0]["label"] = "Scientific research"
        domains.append({"key": "fundraising", "label": "Fundraising"})
        vocab.put(session, "domains", domains)
        assert vocab.labels(session, "domains")["research"] == "Scientific research"
        with pytest.raises(Invalid, match="not valid") as caught:
            vocab.put(session, "domains", domains[1:])  # dropping a value in use
        assert "Retire it instead" in caught.value.errors["items"]
        retired = [{**item, "retired": item["key"] == "fundraising"} for item in domains]
        vocab.put(session, "domains", retired)
        assert "fundraising" not in vocab.keys(session, "domains")
        assert "fundraising" in vocab.keys(session, "domains", active_only=False)


def test_adding_records_gives_them_references_and_owners(
    db: Database, people: People, stock: Stock
) -> None:
    assert (stock.vendor, stock.assistant, stock.notebook) == ("VND-0001", "SYS-0001", "SYS-0002")
    assert [stock.draft, stock.hale, stock.cancer] == ["UC-0001", "UC-0002", "UC-0003"]
    with db.read() as session:
        draft = find(session, USE_CASE, stock.draft)
        [owner] = records.owners_of(session, USE_CASE, [draft.id])[draft.id]
        assert (owner["account_id"], owner["kind"]) == (people.accounts["member"], "accountable")
        assert (draft.status, draft.stage, draft.version) == ("draft", "proposed", 1)
        assert find(session, USE_CASE, " uc-0001 ") is draft
        for bad in ("UC-9999", "SYS-0001", "nonsense"):
            with pytest.raises(NotFound):
                find(session, USE_CASE, bad)


def test_what_is_entered_is_checked(db: Database, people: People) -> None:
    member = who(db, people, "member")
    with db.write(ME.actor) as session:
        with pytest.raises(Invalid) as caught:
            records.create(
                session,
                member,
                USE_CASE,
                {"name": " ", "domain": "astrology", "data_categories": ["x"]},
            )
        assert set(caught.value.errors) == {"name", "org_unit_id", "domain", "data_categories"}
        with pytest.raises(Invalid) as caught:
            records.create(
                session,
                member,
                USE_CASE,
                {"name": "Elsewhere", "org_unit_id": people.units["CANCER"]},
            )
        assert "your own units" in caught.value.errors["org_unit_id"]
        with pytest.raises(Invalid) as caught:
            records.create(session, member, SYSTEM, {"name": "Tool", "url": "javascript:alert(1)"})
        assert set(caught.value.errors) == {"kind", "url"}
        with pytest.raises(Invalid) as caught:
            records.create(session, member, VENDOR, {"name": "V", "website": "lumen.example"})
        assert "https://" in caught.value.errors["website"]
    with db.read() as session:
        assert records.search(session, who(db, people, "admin"), USE_CASE, {})[1] == 0


def test_an_edit_against_an_old_version_is_refused(
    db: Database, people: People, stock: Stock
) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        draft = find(session, USE_CASE, stock.draft)
        records.update(
            session, member, USE_CASE, draft, {"purpose": "Notes into actions"}, version=1
        )
        assert draft.version == 2
        with pytest.raises(Conflict, match="changed by someone else"):
            records.update(session, member, USE_CASE, draft, {"purpose": "Overwrite"}, version=1)
        records.update(
            session, member, USE_CASE, draft, {"purpose": "Notes into actions"}, version=2
        )
        assert draft.version == 2  # saving what is already there changes nothing
        with pytest.raises(Invalid):
            records.update(
                session, member, USE_CASE, draft, {"name": "", "purpose": "lost"}, version=2
            )
        assert (draft.name, draft.purpose, draft.version) == (
            "Summarize lab meeting notes",
            "Notes into actions",
            2,
        )


def test_only_governance_sets_catalog_standing(db: Database, people: People, stock: Stock) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(ME.actor) as session:
        notebook = find(session, SYSTEM, stock.notebook)
        records.update(session, member, SYSTEM, notebook, {"edition": "Community"}, version=1)
        with pytest.raises(PermissionDenied, match="standing in the catalog"):
            records.update(
                session, member, SYSTEM, notebook, {"catalog_status": "approved"}, version=2
            )
        with pytest.raises(Invalid) as caught:
            records.update(
                session, governance, SYSTEM, notebook, {"catalog_status": "approved"}, version=2
            )
        assert "permitted_data_class" in caught.value.errors
        records.update(
            session,
            governance,
            SYSTEM,
            notebook,
            {
                "catalog_status": "approved_with_restrictions",
                "permitted_data_class": "internal",
                "excluded_data_categories": ["health"],
                "terms": "Not for participant data.",
            },
            version=2,
        )
        # Once governance has taken it up, whoever added it no longer edits it as its creator,
        # though as its accountable owner they still can.
        assert access.can_edit(session, member, SYSTEM, notebook)
        vendor = find(session, VENDOR, stock.vendor)
        with pytest.raises(PermissionDenied):
            records.update(session, member, VENDOR, vendor, {"notes": "mine now"}, version=1)
        with pytest.raises(PermissionDenied, match="vendor's standing"):
            records.create(session, member, VENDOR, {"name": "Self-approved", "status": "active"})


# What each person sees of each use case, under each setting. F: all of it, S: a summary.
SIGHT = {
    #             draft  hale  cancer pending secret
    "admin": "FFFFF",
    "governance": "FFFFF",
    "auditor": "FFFFF",
    "member": {"open": "FFF--", "summary": "FFS--", "unit": "FF---"},  # works in the Hale Lab
    "steward": {"open": "FFF--", "summary": "FFS--", "unit": "FF---"},  # steward of Neuroscience
    "reviewer": {
        "open": "-FF--",
        "summary": "-SS--",
        "unit": "-----",
    },  # works nowhere in particular
}


@pytest.mark.parametrize("setting", ["open", "summary", "unit"])
def test_who_sees_what(db: Database, people: People, stock: Stock, setting: str) -> None:
    refs = [stock.draft, stock.hale, stock.cancer, stock.pending, stock.secret]
    with db.write(ME.actor) as session:
        settings.put(session, access.VISIBILITY_SETTING, setting)
    for role in ROLES:
        principal = who(db, people, role)
        expected = SIGHT[role] if isinstance(SIGHT[role], str) else SIGHT[role][setting]
        with db.read() as session:
            seen = ""
            for ref in refs:
                sight = access.sight(session, principal, USE_CASE, find(session, USE_CASE, ref))
                seen += {access.FULL: "F", access.SUMMARY: "S", None: "-"}[sight]
            assert seen == expected, f"{role} under {setting}"
            listed, total = records.search(session, principal, USE_CASE, {}, sort="ref")
            assert [row.ref for row in listed] == [
                r for r, s in zip(refs, expected, strict=True) if s != "-"
            ]
            assert total == len(listed)


def test_a_summary_shows_enough_to_find_a_colleague_and_no_more(
    db: Database, people: People, stock: Stock
) -> None:
    reviewer = who(db, people, "reviewer")
    with db.read() as session:
        seen = records.detail(session, reviewer, USE_CASE, find(session, USE_CASE, stock.cancer))
        assert seen["sight"] == "summary" and seen["purpose"] == "Screening" and seen["owners"]
        assert not {"human_oversight", "data_class", "version", "can", "tags"} & set(seen)
        [card] = [
            c
            for c in records.cards(
                session, reviewer, USE_CASE, records.search(session, reviewer, USE_CASE, {})[0]
            )
            if c["ref"] == stock.cancer
        ]
        assert card["sight"] == "summary" and card["data_class"] is None
        with pytest.raises(NotFound):
            records.detail(session, reviewer, USE_CASE, find(session, USE_CASE, stock.secret))


def test_owners(db: Database, people: People, stock: Stock) -> None:
    member, reviewer = who(db, people, "member"), who(db, people, "reviewer")
    ids = people.accounts
    with db.write(ME.actor) as session:
        hale = find(session, USE_CASE, stock.hale)
        with pytest.raises(Invalid, match="not saved") as caught:
            records.set_owners(
                session,
                member,
                USE_CASE,
                hale,
                [{"account_id": ids["reviewer"], "kind": "technical"}],
            )
        assert "accountable owner" in caught.value.errors["owners"]
        with pytest.raises(Invalid):
            records.set_owners(
                session, member, USE_CASE, hale, [{"account_id": ids["member"], "kind": "boss"}]
            )
        records.set_owners(
            session,
            member,
            USE_CASE,
            hale,
            [
                {"account_id": ids["member"], "kind": "accountable"},
                {"account_id": ids["reviewer"], "kind": "contact"},
            ],
        )
        assert not access.can_edit(session, reviewer, USE_CASE, hale)  # a contact can see, not edit
        assert access.sight(session, reviewer, USE_CASE, hale) == access.FULL
        with pytest.raises(PermissionDenied):
            records.set_owners(
                session,
                reviewer,
                USE_CASE,
                hale,
                [{"account_id": ids["reviewer"], "kind": "accountable"}],
            )
        records.set_owners(
            session,
            member,
            USE_CASE,
            hale,
            [
                {"account_id": ids["member"], "kind": "accountable"},
                {"account_id": ids["reviewer"], "kind": "technical"},
            ],
        )
        assert access.can_edit(session, reviewer, USE_CASE, hale)
        accounts.set_status(session, ME, accounts.get(session, ids["member"]), "disabled")
        assert records.detail(session, who(db, people, "admin"), USE_CASE, hale)["orphaned"] is True
        with pytest.raises(Invalid):
            records.set_owners(session, ME, VENDOR, find(session, VENDOR, stock.vendor), [])


def test_what_a_use_case_uses_and_what_uses_a_system(
    db: Database, people: People, stock: Stock
) -> None:
    member, governance, reviewer = (
        who(db, people, "member"),
        who(db, people, "governance"),
        who(db, people, "reviewer"),
    )
    with db.write(ME.actor) as session:
        records.set_systems(
            session, member, find(session, USE_CASE, stock.hale), [stock.assistant, stock.notebook]
        )
        records.set_systems(
            session, governance, find(session, USE_CASE, stock.secret), [stock.assistant]
        )
        records.set_systems(session, member, find(session, USE_CASE, stock.hale), [stock.assistant])
        with pytest.raises(Invalid):
            records.set_systems(session, member, find(session, USE_CASE, stock.hale), ["SYS-0999"])
        assistant = find(session, SYSTEM, stock.assistant)
        assert [
            s["ref"]
            for s in records.detail(session, member, USE_CASE, find(session, USE_CASE, stock.hale))[
                "systems"
            ]
        ] == [stock.assistant]
        for principal, refs, hidden in [
            (governance, [stock.hale, stock.secret], 0),
            (reviewer, [stock.hale], 1),
        ]:
            seen = records.detail(session, principal, SYSTEM, assistant)
            assert ([u["ref"] for u in seen["used_by"]], seen["used_by_hidden"]) == (refs, hidden)
        vendor = records.detail(session, member, VENDOR, find(session, VENDOR, stock.vendor))
        assert [s["ref"] for s in vendor["systems"]] == [stock.assistant]


def test_the_history_reads_like_a_story(db: Database, people: People, stock: Stock) -> None:
    member = who(db, people, "member")
    with db.write(member.actor) as session:
        hale = find(session, USE_CASE, stock.hale)
        records.update(
            session,
            who(
                db, people, "governance"
            ),  # an approved record's substance is governance's to change
            USE_CASE,
            hale,
            {"data_class": "protected", "domain": "research", "stage": "pilot"},
            version=1,
        )
        records.set_systems(session, member, hale, [stock.assistant])
        records.set_owners(
            session,
            member,
            USE_CASE,
            hale,
            [
                {"account_id": people.accounts["member"], "kind": "accountable"},
                {"account_id": people.accounts["reviewer"], "kind": "technical"},
            ],
        )
    with db.read() as session:
        entries = history.for_record(session, USE_CASE, find(session, USE_CASE, stock.hale))
    titles = [entry["title"] for entry in entries]
    assert titles[0] == "Added Reviewer Person as technical owner"
    assert titles[1] == "Now uses Lumen Assistant"
    edit = entries[2]
    assert edit["title"] == "Edited" and edit["actor"] == "Member Person"
    assert {(line["label"], line["before"], line["after"]) for line in edit["lines"]} == {
        ("Data class", "Internal", "Protected"),
        ("Domain", None, "Research"),
        ("Stage", "Proposed", "Pilot"),
    }
    assert (
        titles[-1] == "Added this use case"
        and titles[-2] == "Added Member Person as accountable owner"
    )
    assert not any(
        line["field"] in ("version", "updated_at") for entry in entries for line in entry["lines"]
    )
    with db.read() as session:
        context = session.scalars(
            select(Event.context).where(Event.subject_type == "use_case", Event.action == "updated")
        ).all()
    assert {"op": "use_case.edit"} in context


def test_the_inventory_through_the_api(as_role: Clients, people: People, stock: Stock) -> None:
    member, governance, reviewer = as_role("member"), as_role("governance"), as_role("reviewer")
    vocabularies = member.get("/api/v1/vocabularies").json()["data"]
    assert vocabularies["data_classes"][3]["key"] == "restricted"

    created = member.post(
        "/api/v1/use-cases", json={"name": "Code review help", "org_unit_id": people.units["HALE"]}
    )
    assert created.status_code == 201
    made = created.json()["data"]
    assert made["ref"] == "UC-0006" and made["can"] == {"edit": True, "edit_catalog": False}
    assert member.post("/api/v1/use-cases", json={"name": ""}).status_code == 422

    url = f"/api/v1/use-cases/{made['ref']}"
    assert member.patch(url, json={"purpose": "x"}).status_code == 422  # no version
    assert (
        member.patch(url, json={"version": 1, "purpose": "Reviewing pull requests"}).json()["data"][
            "version"
        ]
        == 2
    )
    assert member.patch(url, json={"version": 1, "purpose": "stale"}).status_code == 409
    assert reviewer.get(url).status_code == 404  # someone else's draft does not exist
    assert reviewer.patch(url, json={"version": 2, "purpose": "x"}).status_code == 404
    assert governance.get("/api/v1/use-cases/UC-9999").status_code == 404
    assert governance.get("/api/v1/use-cases/not-a-ref").status_code == 404

    linked = member.put(f"{url}/systems", json={"systems": [stock.assistant]}).json()["data"]
    assert linked["systems"][0]["name"] == "Lumen Assistant"
    owners = [{"account_id": people.accounts["member"], "kind": "accountable"}]
    assert member.put(f"{url}/owners", json={"owners": owners}).status_code == 200
    latest = member.get(f"{url}/history").json()["data"][0]
    assert latest["title"] == "Now uses Lumen Assistant"
    assert (
        reviewer.get(f"/api/v1/use-cases/{stock.cancer}/history").status_code == 403
    )  # a summary only

    listing = governance.get("/api/v1/use-cases", params={"sort": "name", "limit": 2})
    body = listing.json()
    assert body["meta"]["total"] == 6 and len(body["data"]) == 2 and body["meta"]["next_cursor"]
    names = [row["name"] for row in body["data"]]
    following = governance.get(
        "/api/v1/use-cases",
        params={"sort": "name", "limit": 2, "cursor": body["meta"]["next_cursor"]},
    )
    names += [row["name"] for row in following.json()["data"]]
    assert names == sorted(names) and len(set(names)) == 4

    def found(client: TestClient, **params: object) -> list[str]:
        return [
            row["ref"]
            for row in client.get("/api/v1/use-cases", params={"sort": "ref", **params}).json()[
                "data"
            ]
        ]

    assert found(governance, q="abstracts") == [stock.cancer]
    assert found(governance, status="approved") == [stock.hale, stock.cancer, stock.secret]
    assert found(governance, unit=people.units["NEURO"]) == [stock.draft, stock.hale, made["ref"]]
    assert found(governance, data_class="protected") == [stock.cancer]
    assert found(member, mine="true") == [stock.draft, stock.hale, made["ref"]]
    assert governance.get("/api/v1/use-cases", params={"sort": "password"}).status_code == 422
    assert governance.get("/api/v1/use-cases", params={"cursor": "garbage!"}).status_code == 422

    systems = member.get("/api/v1/systems", params={"catalog_status": "approved"}).json()["data"]
    assert [s["name"] for s in systems] == ["Lumen Assistant"] and systems[0]["vendor"][
        "name"
    ] == "Lumen Labs"
    assert (
        member.get("/api/v1/systems", params={"vendor": stock.vendor}).json()["meta"]["total"] == 1
    )
    assert (
        member.patch(
            f"/api/v1/systems/{stock.assistant}", json={"version": 1, "terms": "x"}
        ).status_code
        == 403
    )
    assert (
        member.get(f"/api/v1/vendors/{stock.vendor}").json()["data"]["systems"][0]["ref"]
        == stock.assistant
    )

    assert member.get("/api/v1/admin/inventory").status_code == 403
    assert governance.put("/api/v1/admin/inventory", json={"visibility": "unit"}).status_code == 200
    assert (
        governance.put("/api/v1/admin/inventory", json={"visibility": "everything"}).status_code
        == 422
    )
    assert (
        reviewer.get(f"/api/v1/use-cases/{stock.cancer}").status_code == 404
    )  # no longer even a summary


def test_what_was_approved_cannot_be_quietly_changed_by_its_owner(
    db: Database, people: People, stock: Stock
) -> None:
    member, governance = who(db, people, "member"), who(db, people, "governance")
    with db.write(member.actor) as session:
        hale = find(session, USE_CASE, stock.hale)  # approved, and the member's own
        with pytest.raises(Conflict, match="only its summary, tags, and stage"):
            records.update(session, member, USE_CASE, hale, {"data_class": "restricted"}, version=1)
        records.update(
            session, member, USE_CASE, hale, {"stage": "in_use", "tags": ["notes"]}, version=1
        )
        records.update(session, governance, USE_CASE, hale, {"data_class": "protected"}, version=2)
        assert (hale.stage, hale.data_class, hale.version) == ("in_use", "protected", 3)
