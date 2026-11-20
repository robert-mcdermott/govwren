"""Agreements that cover named AI systems, and the rule that health information needs one."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid
from govwren.db.engine import Database
from govwren.integration import checkpoint
from govwren.inventory import agreements, catalog, records
from govwren.inventory.registry import MODEL, SYSTEM, USE_CASE, VENDOR, find
from govwren.oversight import exceptions
from govwren.program import settings
from govwren.review import service
from tests.people import ME, People
from tests.test_review import MONDAY, SIMPLE, get, request, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
HEALTH = {**SIMPLE, "data_categories": ["health"], "deidentified": False, "minimum_necessary": True}


@pytest.fixture
def tools(db: Database, people: People) -> dict[str, str]:
    """A vendor with two hosted products, and an app that runs on the organization's own
    equipment."""
    governance = who(db, people, "governance")
    with db.write(ME.actor) as session:
        vendor = records.create(session, governance, VENDOR, {"name": "Cobaltine"})
        made = {"vendor": vendor.ref}
        for key, name, hosting in [
            ("notes", "Cobaltine Notes", "vendor"),
            ("chat", "Cobaltine Chat", "vendor"),
            ("local", "Ward summaries app", "on_premises"),
        ]:
            system = records.create(
                session, governance, SYSTEM,
                {"name": name, "kind": "vendor_product", "hosting": hosting,
                 "vendor": vendor.ref if hosting == "vendor" else None,
                 "catalog_status": "approved", "permitted_data_class": "restricted"},
            )  # fmt: skip
            made[key] = system.ref
        return made


def _agree(session, governance, tools, covers, **more):  # type: ignore[no-untyped-def]
    vendor = find(session, VENDOR, tools["vendor"])
    values = {"kind": "health_information", "title": "Health information agreement",
              "effective_on": "2026-01-01", "covers": covers, **more}  # fmt: skip
    return agreements.create(session, governance, vendor, values)


def test_an_agreement_covers_the_systems_it_names_and_no_others(
    db: Database, people: People, tools: dict[str, str]
) -> None:
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        notes, chat, local = (find(session, SYSTEM, tools[k]) for k in ("notes", "chat", "local"))
        vendor = find(session, VENDOR, tools["vendor"])
        assert agreements.health_standing(session, notes) == "unknown"
        assert agreements.health_standing(session, local) == "not_needed"
        records.update(
            session,
            governance,
            VENDOR,
            vendor,
            {"signs_health_agreement": "yes"},
            version=vendor.version,
        )
        assert agreements.health_standing(session, notes) == "available"
        records.update(
            session,
            governance,
            VENDOR,
            vendor,
            {"signs_health_agreement": "no"},
            version=vendor.version,
        )
        assert agreements.health_standing(session, notes) == "not_offered"
        with pytest.raises(Invalid) as caught:
            _agree(session, governance, tools, [tools["local"]])  # not this vendor's system
        assert set(caught.value.errors) == {"covers"}
        made = _agree(session, governance, tools, [tools["notes"]], scope_note="Enterprise plan")
        shown = agreements.view(session, made)
        assert shown["covers"] == [
            {"type": "system", "ref": tools["notes"], "name": "Cobaltine Notes"}
        ]
        assert shown["scope_note"] == "Enterprise plan"
        assert agreements.health_standing(session, notes) == "in_place"
        assert agreements.health_standing(session, chat) == "not_offered"  # same vendor, not named
        detail = records.detail(session, governance, SYSTEM, notes)
        assert detail["health_agreement"]["ok"] and detail["health_agreement"]["words"]
        assert (
            checkpoint.check(session, governance, tools["notes"])["health_agreement"] == "in_place"
        )
        listed = {row["ref"]: row["health_agreement"] for row in catalog.listing(session)}
        assert listed[tools["notes"]] == "in_place" and listed[tools["local"]] == "not_needed"
        # A master agreement that names the system says nothing about health information.
        agreements.update(session, governance, made.id, {"kind": "master"})
        assert agreements.health_standing(session, notes) == "not_offered"
        yesterday = (date(2026, 11, 2) - timedelta(days=1)).isoformat()
        agreements.update(
            session, governance, made.id, {"kind": "health_information", "expires_on": yesterday}
        )
        assert agreements.health_standing(session, notes) == "ended"


def test_health_information_is_not_approved_for_a_tool_without_an_agreement(
    db: Database, people: People, tools: dict[str, str]
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY):
        ref = request(db, people, {**HEALTH, "systems": [tools["chat"]]})
        own = request(db, people, {**HEALTH, "name": "On our own", "systems": [tools["local"]]})
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        for each in (ref, own):
            review = get(session, each)
            waived = [task.review_function for task in service.tasks_of(session, review)]
            if waived:
                service.triage(session, governance, review, remove=waived, reason="Seen already.")
            elif review.status == "triage":
                service.triage(session, governance, review)
        service.decide(
            session,
            governance,
            get(session, own),
            outcome="approved",
            rationale="Runs on our own equipment.",
        )
        review = get(session, ref)
        use_case = service.subject_of(session, review)
        with pytest.raises(Conflict) as blocked:
            service.decide(
                session, governance, review, outcome="approved", rationale="Approved by committee."
            )
        assert "Cobaltine Chat" in str(blocked.value) and "health information" in str(blocked.value)
    with frozen_at(MONDAY), db.write(member.actor) as session:
        use_case = service.subject_of(session, get(session, ref))
        # An exception granted for some other requirement does not set this rule aside.
        other = exceptions.request(
            session, member, USE_CASE, use_case, title="Training not finished",
            requirement="Everyone using it has finished the AI training.",
            justification="The course opens next month.",
            measures="A short briefing is given in its place.",
            ends_on=date(2027, 2, 1),
        )  # fmt: skip
        asked = exceptions.request(
            session, member, USE_CASE, use_case, title="No agreement yet",
            requirement="A covering agreement before health information is used.",
            justification="The agreement is with the vendor for signature.",
            measures="Only a limited data set is used until it is signed.",
            ends_on=date(2027, 2, 1), rule="health_agreement",
        )  # fmt: skip
        with pytest.raises(Invalid):
            exceptions.request(
                session, member, USE_CASE, use_case, title="Something else",
                requirement="A requirement that is not one of ours.",
                justification="It is a test of the rule key.", measures="Nothing needed here.",
                ends_on=date(2027, 2, 1), rule="no_such_rule",
            )  # fmt: skip
        number, other_number = asked.id, other.id
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        review = get(session, ref)
        use_case = service.subject_of(session, review)
        answers = service.latest_answers(session, use_case)
        exceptions.decide(
            session, governance, session.get(type(asked), other_number), outcome="approved",
            note="Training follows.",
        )  # fmt: skip
        assert agreements.health_gap(session, use_case, answers) is not None
        exception = session.get(type(asked), number)
        exceptions.decide(session, governance, exception, outcome="approved", note="Until signed.")
        assert exceptions.view(session, governance, exception)["rule"] == "health_agreement"
        assert agreements.health_gap(session, use_case, answers) is None
        assert agreements.health_gap(
            session, use_case, answers, exceptions=False
        )  # rules still stop
        service.decide(
            session, governance, review, outcome="approved", rationale="Approved with an exception."
        )


def test_an_agreement_or_deidentified_data_lifts_the_rule_and_it_can_be_turned_off(
    db: Database, people: People, tools: dict[str, str]
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    values = {"name": "Drafting discharge letters", "org_unit_id": people.units["HALE"],
              "data_class": "restricted", "data_categories": ["health"],
              "everyday": True}  # fmt: skip
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        chat = find(session, SYSTEM, tools["chat"])
        assert "health information" in (catalog.fits(session, chat, "restricted", ["health"]) or "")
        assert catalog.fits(session, chat, "restricted", []) is None
        sent = catalog.register(session, member, chat, values)
        assert not sent["registered"] and "health information" in sent["reason"]
        _agree(session, governance, tools, [tools["chat"]])
        assert catalog.fits(session, chat, "restricted", ["health"]) is None
        notes = find(session, SYSTEM, tools["notes"])
        assert catalog.fits(session, notes, "restricted", ["health"]) is not None
        settings.put(session, agreements.RULE_SETTING, False)
        assert catalog.fits(session, notes, "restricted", ["health"]) is None
        settings.put(session, agreements.RULE_SETTING, True)
    with frozen_at(MONDAY):
        ref = request(db, people, {**HEALTH, "deidentified": True, "systems": [tools["notes"]]})
    with db.read() as session:
        use_case = service.subject_of(session, get(session, ref))
        assert (
            agreements.health_gap(session, use_case, service.latest_answers(session, use_case))
            is None
        )
        assert agreements.health_gap(session, use_case, {}) is not None


def test_the_rule_is_a_setting_over_the_api(as_role: Clients, tools: dict[str, str]) -> None:
    admin = as_role("admin")
    assert admin.get("/api/v1/admin/inventory").json()["data"]["health_agreement_rule"] is True
    saved = admin.put("/api/v1/admin/inventory", json={"health_agreement_rule": False})
    assert saved.status_code == 200 and saved.json()["data"]["health_agreement_rule"] is False
    assert saved.json()["data"]["visibility"] == "summary"
    governance = as_role("governance")
    made = governance.post(
        f"/api/v1/vendors/{tools['vendor']}/agreements",
        json={"kind": "health_information", "title": "Health agreement",
              "covers": [tools["notes"]], "scope_note": "Enterprise plan only"},
    )  # fmt: skip
    assert made.status_code == 201 and made.json()["data"]["covers"][0]["ref"] == tools["notes"]
    seen = governance.get(f"/api/v1/systems/{tools['notes']}").json()["data"]
    assert seen["health_agreement"]["standing"] == "in_place"
    version = governance.get(f"/api/v1/vendors/{tools['vendor']}").json()["data"]["version"]
    patched = governance.patch(
        f"/api/v1/vendors/{tools['vendor']}",
        json={"signs_health_agreement": "yes", "version": version},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["data"]["signs_health_agreement"] == "yes"


def test_what_the_rule_rests_on_is_governance_s_to_change(
    db: Database, people: People, tools: dict[str, str]
) -> None:
    """The second security review: the rule could be undone by people it was meant to bind."""
    from govwren.core.errors import PermissionDenied
    from govwren.db.models import Model

    governance, member = who(db, people, "governance"), who(db, people, "member")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        vendor = find(session, VENDOR, tools["vendor"])
        chat = find(session, SYSTEM, tools["chat"])
        records.set_owners(session, governance, SYSTEM, chat, [
            {"account_id": people.accounts["member"], "kind": "accountable"}])  # fmt: skip
        api = records.create(
            session, governance, MODEL,
            {"name": "Cobaltine Large", "kind": "language", "origin": "commercial_api",
             "vendor": vendor.ref, "catalog_status": "approved",
             "permitted_data_class": "restricted"},
        )  # fmt: skip
        mine = records.create(
            session, governance, MODEL,
            {"name": "Our own weights", "kind": "language", "origin": "open_weights",
             "catalog_status": "approved", "permitted_data_class": "restricted"},
        )  # fmt: skip
        assert agreements.health_standing(session, api) == "unknown"
        assert agreements.health_standing(session, mine) == "not_needed"
        api_ref = api.ref
    with frozen_at(MONDAY), db.write(member.actor) as session:
        chat = find(session, SYSTEM, tools["chat"])
        # An owner cannot move a listed tool onto their own equipment to clear the rule.
        with pytest.raises(PermissionDenied):
            records.update(session, member, SYSTEM, chat, {"hosting": "on_premises"},
                           version=chat.version)  # fmt: skip
        records.update(session, member, SYSTEM, chat, {"summary": "Still editable."},
                       version=chat.version)  # fmt: skip
        # A supplier's model is held to the rule too.
        api = find(session, MODEL, api_ref)
        values = {"name": "Notes from clinic letters", "org_unit_id": people.units["HALE"],
                  "data_class": "restricted", "data_categories": ["health"],
                  "everyday": True}  # fmt: skip
        sent = catalog.register(session, member, api, values)
        assert not sent["registered"] and "health information" in sent["reason"]
        assert isinstance(api, Model)
    with frozen_at(MONDAY), db.write(member.actor) as session:
        vendor = find(session, VENDOR, tools["vendor"])
        # Only governance records an agreement covering health information.
        with pytest.raises(PermissionDenied):
            mine = {"kind": "health_information", "title": "Mine", "covers": [tools["chat"]]}
            agreements.create(session, member, vendor, mine)
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        made = _agree(session, governance, tools, [api_ref])
        assert agreements.view(session, made)["covers"] == [
            {"type": "model", "ref": api_ref, "name": "Cobaltine Large"}]  # fmt: skip
        assert agreements.health_standing(session, find(session, MODEL, api_ref)) == "in_place"
        assert checkpoint.check(session, governance, api_ref)["health_agreement"] == "in_place"


def test_what_a_decided_use_relies_on_changes_only_by_declaring_it(
    db: Database, people: People, tools: dict[str, str]
) -> None:
    member = who(db, people, "member")
    with frozen_at(MONDAY):
        ref = request(db, people, {**SIMPLE, "systems": [tools["notes"]]})
    with db.write(member.actor) as session:
        use_case = service.subject_of(session, get(session, ref))
        assert use_case.status in ("approved", "approved_with_conditions")
        with pytest.raises(Conflict):
            records.set_systems(session, member, use_case, [tools["chat"]])
        records.set_systems(session, member, use_case, [tools["chat"]], declared=True)
