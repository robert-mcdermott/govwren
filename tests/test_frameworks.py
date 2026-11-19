"""Frameworks: optional packs of requirements with a crosswalk from the control library,
readiness worked out from how the controls stand, and the statement of applicability."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from govwren.assurance import controls, frameworks
from govwren.core.clock import frozen_at
from govwren.core.errors import Conflict, Invalid, NotFound, PermissionDenied
from govwren.db.engine import Database
from govwren.db.models import ControlImplementation
from govwren.evidence import service as evidence
from govwren.inventory.registry import USE_CASE, find
from tests.people import People
from tests.test_changes import linked
from tests.test_review import MONDAY, who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
SMALL: dict[str, Any] = {
    "pack": {"key": "house-rules", "kind": "framework", "title": "House rules", "version": "3"},
    "requirements": [
        {
            "code": "A",
            "title": "Accountability",
            "children": [
                {"code": "A.1", "text": "Someone answers for every use."},
                {"code": "A.2", "text": "The inventory is kept."},
                {"code": "A.3", "text": "Something nothing here covers."},
            ],
        },
    ],
    "crosswalk": {"A.1": ["named-owner"], "A.2": ["inventory-kept"]},
}


def states(tree: dict[str, Any]) -> dict[str, str]:
    return {
        leaf["code"]: leaf["state"] for group in tree["requirements"] for leaf in group["children"]
    }


def test_nothing_needs_a_framework_and_a_bad_pack_is_refused_whole(
    db: Database, people: People
) -> None:
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(governance.actor) as session:
        seen = frameworks.listing(session, governance)
        assert seen["loaded"] == [] and [f["key"] for f in seen["available"]] == [
            "nist-ai-rmf", "iso-iec-42001", "hipaa",
        ]  # fmt: skip
        assert len(frameworks.statement_of_applicability(session, governance)) >= 30  # needs none
        with pytest.raises(PermissionDenied):
            frameworks.load(session, member, SMALL)
        bad = {**SMALL, "crosswalk": {"A.1": ["no-such-control"], "Z.9": ["named-owner"]}}
        with pytest.raises(Invalid) as refused:
            frameworks.load(session, governance, bad)
        assert (
            "no-such-control" in refused.value.errors["pack"]
            and "Z.9" in refused.value.errors["pack"]
        )
        assert frameworks.problems(session, {"pack": {"kind": "risk_library"}}) == [
            "This is not a framework pack."
        ]
        assert frameworks.listing(session, governance)["loaded"] == []
        with pytest.raises(NotFound):
            frameworks.find(session, "house-rules")


def test_readiness_follows_the_controls_and_is_never_typed_in(db: Database, people: People) -> None:
    use_ref, _, _ = linked(db, people)
    governance = who(db, people, "governance")
    with frozen_at(MONDAY), db.write(governance.actor) as session:
        framework = frameworks.load(session, governance, SMALL)
        ready = frameworks.readiness(session, governance, framework)
        assert states(ready) == {"A.1": "gap", "A.2": "gap", "A.3": "not_mapped"}
        assert ready["counts"] == {
            "covered": 0,
            "partly": 0,
            "gap": 2,
            "not_mapped": 1,
            "not_applicable": 0,
        }
        # A record control counts by the share of the records it applies to.
        use_case = find(session, USE_CASE, use_ref)
        controls.set_standing(
            session,
            governance,
            controls.find(session, "named-owner"),
            {"status": "implemented"},
            record=(USE_CASE, use_case),
        )
        # A program control in place with no evidence is only partly there.
        controls.set_standing(
            session, governance, controls.find(session, "inventory-kept"), {"status": "implemented"}
        )
        ready = frameworks.readiness(session, governance, framework)
        assert states(ready) == {"A.1": "covered", "A.2": "partly", "A.3": "not_mapped"}
        row = session.scalars(
            select(ControlImplementation).where(ControlImplementation.subject_type.is_(None))
        ).one()
        evidence.create(
            session,
            governance,
            {
                "title": "Export of the inventory",
                "kind": "record",
                "description": "The inventory, exported.",
                "supports": [f"control:{row.id}"],
            },
        )
        ready = frameworks.readiness(session, governance, framework)
        assert states(ready)["A.2"] == "covered"
        behind = ready["requirements"][0]["children"][1]["controls"]
        assert behind == [
            {
                "key": "inventory-kept",
                "title": "An inventory of AI in use is kept",
                "scope": "program",
                "level": "full",
                "detail": "In place, with evidence",
            }
        ]
        with pytest.raises(Invalid):
            frameworks.set_applicability(
                session, governance, framework, "A.3", applies=False, justification="no"
            )
        frameworks.set_applicability(
            session,
            governance,
            framework,
            "A.3",
            applies=False,
            justification="We have no such activity.",
        )
        ready = frameworks.readiness(session, governance, framework)
        assert states(ready)["A.3"] == "not_applicable" and ready["counts"]["not_mapped"] == 0
        frameworks.set_applicability(session, governance, framework, "A.3", applies=True)
        with pytest.raises(Conflict):
            frameworks.set_applicability(session, governance, framework, "A.3", applies=True)
        with pytest.raises(NotFound):
            frameworks.set_applicability(
                session,
                governance,
                framework,
                "B.7",
                applies=False,
                justification="There is no such requirement.",
            )


def test_loading_again_updates_and_unloading_leaves_the_controls_alone(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        frameworks.load(session, governance, SMALL)
        controls.set_standing(
            session, governance, controls.find(session, "inventory-kept"), {"status": "implemented"}
        )
        newer = {**SMALL, "crosswalk": {**SMALL["crosswalk"], "A.3": ["roles-assigned"]}}
        framework = frameworks.load(session, governance, newer)
        assert states(frameworks.readiness(session, governance, framework))["A.3"] == "gap"
        assert len(frameworks.listing(session, governance)["loaded"]) == 1
        frameworks.unload(session, governance, framework)
        assert frameworks.listing(session, governance)["loaded"] == []
        listed = {c["key"]: c for c in controls.library(session, governance)}
        assert listed["inventory-kept"]["status"] == "implemented"


def test_the_built_in_framework_loads_and_maps_to_controls_that_exist(
    db: Database, people: People
) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        pack = frameworks.builtin("nist-ai-rmf")
        assert frameworks.problems(session, pack) == []
        assert pack["pack"]["text_policy"] == "summary"
        framework = frameworks.load(session, governance, pack)
        ready = frameworks.readiness(session, governance, framework)
        assert [group["code"] for group in ready["requirements"]] == [
            "GOVERN",
            "MAP",
            "MEASURE",
            "MANAGE",
        ]
        assert (
            ready["total"] == 19 and ready["counts"]["not_mapped"] == 1
        )  # one category nothing here covers
        assert ready["publisher"] == "National Institute of Standards and Technology"


def test_frameworks_and_the_statement_over_the_api(
    db: Database, people: People, as_role: Clients
) -> None:
    governance, auditor, member = as_role("governance"), as_role("auditor"), as_role("member")
    assert member.get("/api/v1/frameworks").status_code == 403
    assert auditor.post("/api/v1/frameworks", json={"key": "nist-ai-rmf"}).status_code == 403
    assert governance.post("/api/v1/frameworks", json={"key": "nothing"}).status_code == 404
    loaded = governance.post("/api/v1/frameworks", json={"key": "nist-ai-rmf"})
    assert loaded.status_code == 201 and loaded.json()["data"]["total"] == 19
    assert governance.post("/api/v1/frameworks", json={"pack": SMALL}).status_code == 201
    assert (
        governance.post(
            "/api/v1/frameworks", json={"pack": {"pack": {"kind": "framework"}}}
        ).status_code
        == 422
    )
    listed = auditor.get("/api/v1/frameworks").json()["data"]
    assert {f["key"] for f in listed["loaded"]} == {"nist-ai-rmf", "house-rules"}
    assert [f["key"] for f in listed["available"]] == ["iso-iec-42001", "hipaa"]
    off = governance.put(
        "/api/v1/frameworks/nist-ai-rmf/applicability",
        json={"code": "GOVERN 3", "applies": False, "justification": "Handled by people services."},
    )
    assert off.json()["data"]["counts"]["not_applicable"] == 1
    sheet = auditor.get("/api/v1/statement-of-applicability")
    assert sheet.headers["content-type"].startswith("text/csv")
    lines = sheet.text.splitlines()
    assert lines[0].startswith("Key,Group,Control,Statement,Scope,Applies") and len(lines) >= 31
    as_json = auditor.get("/api/v1/statement-of-applicability", params={"format": "json"}).json()[
        "data"
    ]
    assert {"key", "applies", "justification", "status", "owner", "evidence"} <= set(as_json[0])
    assert governance.delete("/api/v1/frameworks/house-rules").status_code == 200
    assert auditor.get("/api/v1/frameworks/house-rules").status_code == 404


@pytest.mark.parametrize(
    ("key", "requirements", "mapped_at_least"),
    [("nist-ai-rmf", 19, 18), ("iso-iec-42001", 64, 50), ("hipaa", 25, 22)],
)
def test_every_built_in_framework_loads_and_is_mostly_answered(
    db: Database, people: People, key: str, requirements: int, mapped_at_least: int
) -> None:
    governance = who(db, people, "governance")
    pack = frameworks.builtin(key)
    assert pack["pack"]["text_policy"] in ("summary", "identifiers", "verbatim")
    with db.write(governance.actor) as session:
        assert frameworks.problems(session, pack) == []
        loaded = frameworks.load(session, governance, pack)
        counts = frameworks.readiness(session, governance, loaded)["counts"]
    assert sum(counts.values()) == requirements
    assert requirements - counts["not_mapped"] >= mapped_at_least


def test_the_iso_pack_carries_numbers_and_our_own_words() -> None:
    """The standard is copyrighted: its pack must say so and must not quote it."""
    pack = frameworks.builtin("iso-iec-42001")
    assert pack["pack"]["text_policy"] == "identifiers"
    assert "wording is reproduced" in pack["pack"]["attribution"]
    text = json.dumps(pack["requirements"])
    for quoted in ("The organization shall", "shall determine", "shall establish"):
        assert quoted not in text


def test_an_upgrade_gains_new_controls_and_touches_nothing_else(
    db: Database, people: People
) -> None:
    from sqlalchemy import select

    from govwren.assurance import controls, library
    from govwren.db.models import Control, RiskStatement

    governance = who(db, people, "governance")
    with db.write(governance.actor) as session:
        # As an installation stood before the release: without two controls, and with one
        # control and one risk that it had retired on purpose.
        for row in session.scalars(
            select(Control).where(Control.key.in_(("policy-approved", "impact-assessed")))
        ):
            session.delete(row)
        retired = session.scalars(select(Control).where(Control.key == "units-attest")).one()
        retired.retired, retired.title = True, "Our own wording"
        gone = session.scalars(
            select(RiskStatement).where(RiskStatement.key == "skills-fade")
        ).one()
        session.delete(gone)
        session.flush()
        assert controls.ensure(session) is True and library.ensure(session) is True
        keys = set(session.scalars(select(Control.key)))
        assert {"policy-approved", "impact-assessed"} <= keys
        kept = session.scalars(select(Control).where(Control.key == "units-attest")).one()
        assert kept.retired is True and kept.title == "Our own wording"
        assert session.scalars(
            select(RiskStatement).where(RiskStatement.key == "skills-fade")
        ).one()
        assert controls.ensure(session) is False and library.ensure(session) is False
