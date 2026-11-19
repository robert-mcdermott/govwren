"""Fields an organization adds to a kind of record."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from govwren.core.errors import Invalid, PermissionDenied
from govwren.db.engine import Database
from govwren.inventory import custom, records
from govwren.inventory.registry import USE_CASE, VENDOR, find
from tests.people import People
from tests.test_changes import linked
from tests.test_review import who

Clients = Callable[[str | None], TestClient]
pytestmark = pytest.mark.usefixtures("program")
FIELDS = [
    {"label": "Cost center", "help": "Six digits."},
    {"label": "Funding", "kind": "choice", "options": ["Grant", "Core budget", "Gift"]},
    {"label": "Go-live date", "kind": "date"},
    {"label": "Uses a GPU", "kind": "yes_no", "key": "gpu"},
    {"label": "Seats", "kind": "number"},
    {"label": "Notes for finance", "kind": "long"},
]


def test_fields_are_defined_and_answered(db: Database, people: People) -> None:
    use, _system, _model = linked(db, people)
    governance, member = who(db, people, "governance"), who(db, people, "member")
    with db.write(governance.actor) as session:
        defined = custom.save(session, governance, USE_CASE, FIELDS)
        assert [f["key"] for f in defined["use_case"]] == [
            "cost_center", "funding", "go_live_date", "gpu", "seats", "notes_for_finance",
        ]  # fmt: skip
        assert defined["vendor"] == [] and defined["use_case"][0]["help"] == "Six digits."
        with pytest.raises(PermissionDenied):
            custom.save(session, member, USE_CASE, [])
    with db.write(member.actor) as session:  # an owner answers them, even after approval
        record = find(session, USE_CASE, use)
        answers = {
            "cost_center": " 440120 ", "funding": "Grant", "go_live_date": "2026-03-01",
            "gpu": True, "seats": 12, "unknown": "dropped",
        }  # fmt: skip
        records.update(
            session, member, USE_CASE, record, {"custom": answers}, version=record.version
        )
        assert record.custom == {
            "cost_center": "440120", "funding": "Grant", "go_live_date": "2026-03-01",
            "gpu": True, "seats": 12,
        }  # fmt: skip
        shown = records.detail(session, member, USE_CASE, record)
        assert shown["custom"]["funding"] == "Grant"
        records.update(  # one answer changes, one is cleared, the rest stay
            session, member, USE_CASE, record, {"custom": {"seats": 15, "funding": ""}},
            version=record.version,
        )  # fmt: skip
        assert record.custom["seats"] == 15 and "funding" not in record.custom
        assert record.custom["cost_center"] == "440120"
        for bad, key in (
            ({"funding": "Lottery"}, "custom.funding"),
            ({"go_live_date": "soon"}, "custom.go_live_date"),
            ({"gpu": "yes"}, "custom.gpu"),
            ({"seats": "twelve"}, "custom.seats"),
            ({"cost_center": "x" * 301}, "custom.cost_center"),
        ):
            with pytest.raises(Invalid) as refused:
                records.update(
                    session, member, USE_CASE, record, {"custom": bad}, version=record.version
                )
            assert key in refused.value.errors
    with db.write(governance.actor) as session:  # a field taken away keeps what was answered
        custom.save(session, governance, USE_CASE, FIELDS[:1])
        assert find(session, USE_CASE, use).custom["seats"] == 15
        vendor = records.create(
            session, governance, VENDOR, {"name": "Lumen Labs", "custom": {"cost_center": "1"}}
        )
        assert vendor.custom == {}  # vendors have no such field


@pytest.mark.parametrize(
    "fields",
    [
        [{"label": ""}],
        [{"label": "A", "key": "Bad Key"}],
        [{"label": "Same"}, {"label": "Same"}],
        [{"label": "Kind", "kind": "color"}],
        [{"label": "Pick", "kind": "choice", "options": ["Only one"]}],
        [{"label": f"Field {n}"} for n in range(21)],
    ],
)
def test_definitions_that_cannot_be_used(
    db: Database, people: People, fields: list[dict[str, object]]
) -> None:
    governance = who(db, people, "governance")
    with db.write(governance.actor) as session, pytest.raises(Invalid):
        custom.save(session, governance, USE_CASE, fields)


def test_over_the_api(as_role: Clients) -> None:
    governance, member = as_role("governance"), as_role("member")
    saved = governance.put(
        "/api/v1/record-types/dataset/custom-fields", json={"fields": FIELDS[:2]}
    )
    assert saved.status_code == 200 and len(saved.json()["data"]["dataset"]) == 2
    assert (
        member.put("/api/v1/record-types/dataset/custom-fields", json={"fields": []}).status_code
        == 403
    )
    assert (
        governance.put("/api/v1/record-types/robot/custom-fields", json={"fields": []}).status_code
        == 404
    )
    types = member.get("/api/v1/record-types").json()["data"]
    assert types["custom"]["dataset"][1]["options"] == ["Grant", "Core budget", "Gift"]
    assert types["custom_kinds"]["yes_no"] == "Yes or no"
    made = member.post(
        "/api/v1/datasets",
        json={"name": "Lab notes", "data_class": "internal", "custom": {"funding": "Gift"}},
    )
    assert made.status_code == 201 and made.json()["data"]["custom"] == {"funding": "Gift"}
    ref, version = made.json()["data"]["ref"], made.json()["data"]["version"]
    bad = member.patch(
        f"/api/v1/datasets/{ref}", json={"version": version, "custom": {"funding": "No"}}
    )
    assert bad.status_code == 422 and bad.json()["errors"][0]["location"] == ["custom.funding"]
